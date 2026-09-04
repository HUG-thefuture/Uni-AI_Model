"""WP07 本地自测(不进仓库,pytest 直接跑;参考 test_chat_tasks.py 的 sqlite 环境):
- POST /uploads:png 魔数成功、exe 内容 400、超 10MB 400、非法扩展名 400;
- 声音克隆:提交 pending → succeeded,result_url 以 /static/ 开头,钱包扣 2;
- 语音识别:asr 成功 result_text 非空;
- 视频:Mock 轮询后 succeeded result_url 非空,钱包扣 5;
- 校验:模型类型不符 409、时长超上限 400、文本超长 400、余额不足 409、
  同 request_id 幂等 409、他人任务 403、线上视频接口未就绪失败不扣费。
"""
import json
import random
import time
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings
from app.core.db import Base, get_db
from app.core.request_id import RequestIdMiddleware
from app.core.response import register_exception_handlers
from app.core.security import create_access_token
from app.models import Model, User, Wallet
from app.models.ai_task import AiTask
from app.routers import tasks as tasks_router
from app.routers import uploads as uploads_router
from app.services import task_service

PRICE_AUDIO = 2
PRICE_VIDEO = 5


@pytest.fixture()
def env(monkeypatch):
    """sqlite 内存库 + dependency_overrides + 压缩 Mock 延迟与视频轮询间隔。"""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(task_service, "SessionLocal", Session)
    # Mock 的 3-8s 模拟延迟压缩到毫秒级(random.uniform 同时覆盖 query_video 内部延迟)
    monkeypatch.setattr(random, "uniform", lambda a, b: 0.01)
    # 视频轮询间隔/上限压缩,避免测试等待真实 5s
    real_settings = get_settings()
    fast_settings = real_settings.model_copy(
        update={"video_poll_interval_sec": 0.05, "video_poll_max_sec": 5}
    )
    monkeypatch.setattr(task_service, "get_settings", lambda: fast_settings)

    db = Session()
    user = User(username="alice", password_hash="x")
    other = User(username="bob", password_hash="x")
    db.add_all([user, other])
    db.commit()
    db.refresh(user)
    db.refresh(other)
    db.add_all([
        Wallet(user_id=user.id, balance=100),
        Wallet(user_id=other.id, balance=100),
    ])
    audio_model = Model(name="Mock 声音", model_code="mock-tts", provider_type="online",
                        model_type="audio", vendor="mock", price_per_call=PRICE_AUDIO,
                        max_duration_sec=60, status="enabled")
    video_model = Model(name="Mock 视频", model_code="mock-video", provider_type="online",
                        model_type="video", vendor="mock", price_per_call=PRICE_VIDEO,
                        max_duration_sec=120, status="enabled")
    sf_video = Model(name="硅基视频", model_code="Wan/Wan2.1-T2V", provider_type="online",
                     model_type="video", vendor="siliconflow", price_per_call=PRICE_VIDEO,
                     status="enabled")
    db.add_all([audio_model, video_model, sf_video])
    db.commit()
    for m in (audio_model, video_model, sf_video):
        db.refresh(m)
    db.close()

    app = FastAPI()
    register_exception_handlers(app)
    app.add_middleware(RequestIdMiddleware)
    app.include_router(tasks_router.router, prefix="/api")
    app.include_router(uploads_router.router, prefix="/api")

    def _override_db():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = _override_db

    return SimpleNamespace(app=app, Session=Session, user=user, other=other,
                           audio_model=audio_model, video_model=video_model, sf_video=sf_video)


def _auth(user) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role)}"}


def _client(env) -> TestClient:
    return TestClient(env.app, raise_server_exceptions=False)


def _poll_task(client, task_id: int, user, timeout: float = 8.0) -> dict:
    deadline = time.monotonic() + timeout
    detail = {}
    while time.monotonic() < deadline:
        detail = client.get(f"/api/tasks/{task_id}", headers=_auth(user)).json()["data"]
        if detail["status"] in ("succeeded", "failed"):
            return detail
        time.sleep(0.05)
    return detail


# ---------- POST /uploads ----------

def test_upload_png_ok(env):
    client = _client(env)
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
    resp = client.post("/api/uploads", files={"file": ("校徽.png", png, "image/png")},
                       headers=_auth(env.user))
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["url"].startswith("/static/") and data["url"].endswith(".png")
    assert data["size"] == len(png) and data["filename"]


def test_upload_magic_mismatch_400(env):
    client = _client(env)
    resp = client.post("/api/uploads", files={"file": ("fake.png", b"MZfake-exe-content", "image/png")},
                       headers=_auth(env.user))
    assert resp.status_code == 400
    assert resp.json()["message"] == "文件内容与类型不符"


def test_upload_too_large_400(env):
    client = _client(env)
    big = b"\x89PNG\r\n\x1a\n" + b"\x00" * (10 * 1024 * 1024)
    resp = client.post("/api/uploads", files={"file": ("big.png", big, "image/png")},
                       headers=_auth(env.user))
    assert resp.status_code == 400
    assert resp.json()["message"] == "文件超过 10MB 限制"


def test_upload_bad_extension_400(env):
    client = _client(env)
    resp = client.post("/api/uploads", files={"file": ("virus.exe", b"MZ\x90\x00", "application/x-msdownload")},
                       headers=_auth(env.user))
    assert resp.status_code == 400
    assert resp.json()["message"] == "不支持的文件类型"


def test_upload_requires_auth(env):
    client = _client(env)
    resp = client.post("/api/uploads", files={"file": ("a.png", b"\x89PNG\r\n\x1a\n", "image/png")})
    assert resp.status_code == 401


# ---------- 声音克隆 ----------

def test_audio_clone_flow(env):
    with TestClient(env.app) as client:  # 上下文模式:后台任务在请求间持续执行
        resp = client.post("/api/tasks/audio/clone",
                           json={"model_id": env.audio_model.id, "voice_name": "alloy",
                                 "text": "欢迎来到四川高校 AI 大模型门户"},
                           headers=_auth(env.user))
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["status"] == "pending"
        detail = _poll_task(client, data["task_id"], env.user)
        assert detail["status"] == "succeeded", detail
        assert detail["result_url"] and detail["result_url"].startswith("/static/")
        db = env.Session()
        task = db.get(AiTask, data["task_id"])
        assert task.task_type == "audio_clone" and task.cost_status == "settled"
        assert task.cost == PRICE_AUDIO
        params = json.loads(task.params_json)
        assert params["voice_name"] == "alloy" and "text" in params
        wallet = db.get(Wallet, env.user.id)
        assert wallet.balance == 100 - PRICE_AUDIO and wallet.total_consumed == PRICE_AUDIO
        db.close()


def test_audio_clone_model_type_mismatch_409(env):
    client = _client(env)
    resp = client.post("/api/tasks/audio/clone",
                       json={"model_id": env.video_model.id, "voice_name": "alloy", "text": "hi"},
                       headers=_auth(env.user))
    assert resp.status_code == 409
    assert resp.json()["message"] == "该模型不支持声音任务"


def test_audio_clone_duration_over_limit_400(env):
    client = _client(env)
    resp = client.post("/api/tasks/audio/clone",
                       json={"model_id": env.audio_model.id, "voice_name": "alloy",
                             "text": "hi", "duration_sec": 999},
                       headers=_auth(env.user))
    assert resp.status_code == 400
    assert resp.json()["message"] == "音频时长超过模型上限"


def test_audio_clone_duplicate_request_id_409(env, monkeypatch):
    monkeypatch.setattr(task_service, "start_background_task", lambda task_id: None)
    client = _client(env)
    headers = {**_auth(env.user), "X-Request-Id": "dup-av-1"}
    body = {"model_id": env.audio_model.id, "voice_name": "alloy", "text": "hi"}
    assert client.post("/api/tasks/audio/clone", json=body, headers=headers).status_code == 200
    second = client.post("/api/tasks/audio/clone", json=body, headers=headers)
    assert second.status_code == 409
    assert second.json()["message"] == "请勿重复提交"


def test_audio_clone_distinct_request_ids_are_not_duplicates(env, monkeypatch):
    """路由在线程池提交时仍须保留每个 HTTP 请求自己的幂等键。"""
    monkeypatch.setattr(task_service, "start_background_task", lambda task_id: None)
    client = _client(env)
    body = {"model_id": env.audio_model.id, "voice_name": "alloy", "text": "hi"}
    first = client.post("/api/tasks/audio/clone", json=body,
                        headers={**_auth(env.user), "X-Request-Id": "audio-request-1"})
    second = client.post("/api/tasks/audio/clone", json=body,
                         headers={**_auth(env.user), "X-Request-Id": "audio-request-2"})
    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert first.json()["data"]["task_id"] != second.json()["data"]["task_id"]


def test_audio_clone_insufficient_balance_409(env):
    client = _client(env)
    db = env.Session()
    db.get(Wallet, env.user.id).balance = 1
    db.commit()
    db.close()
    resp = client.post("/api/tasks/audio/clone",
                       json={"model_id": env.audio_model.id, "voice_name": "alloy", "text": "hi"},
                       headers=_auth(env.user))
    assert resp.status_code == 409
    assert resp.json()["message"] == "积分不足,请先充值"
    db = env.Session()
    assert db.query(AiTask).count() == 0
    assert db.get(Wallet, env.user.id).balance == 1
    db.close()


# ---------- 语音识别 ----------

def test_asr_flow(env):
    with TestClient(env.app) as client:
        resp = client.post("/api/tasks/audio/asr",
                           json={"model_id": env.audio_model.id, "audio_url": "/static/sample.mp3"},
                           headers=_auth(env.user))
        assert resp.status_code == 200, resp.text
        task_id = resp.json()["data"]["task_id"]
        detail = _poll_task(client, task_id, env.user)
        assert detail["status"] == "succeeded", detail
        assert detail["result_text"]
        db = env.Session()
        task = db.get(AiTask, task_id)
        assert task.task_type == "asr" and task.cost_status == "settled"
        assert task.cost == PRICE_AUDIO
        assert db.get(Wallet, env.user.id).balance == 100 - PRICE_AUDIO
        db.close()


# ---------- 视频 ----------

def test_video_mock_flow(env):
    with TestClient(env.app) as client:
        resp = client.post("/api/tasks/video",
                           json={"model_id": env.video_model.id,
                                 "text": "把这段长文本转成校园宣传片:" + "四川高校" * 100,
                                 "params": {"resolution": "1280x720", "duration_sec": 60}},
                           headers=_auth(env.user))
        assert resp.status_code == 200, resp.text
        task_id = resp.json()["data"]["task_id"]
        detail = _poll_task(client, task_id, env.user)
        assert detail["status"] == "succeeded", detail
        assert detail["result_url"]  # Mock 轮询后拿到样例视频 URL
        assert detail["result_urls"] == ["https://interactive-examples.mdn.mozilla.net/media/cc0-videos/flower.mp4"]
        db = env.Session()
        task = db.get(AiTask, task_id)
        assert task.task_type == "video" and task.cost_status == "settled"
        assert task.cost == PRICE_VIDEO and task.result_url == detail["result_url"]
        assert json.loads(task.params_json)["resolution"] == "1280x720"
        wallet = db.get(Wallet, env.user.id)
        assert wallet.balance == 100 - PRICE_VIDEO and wallet.total_consumed == PRICE_VIDEO
        db.close()


def test_video_text_over_2000_400(env):
    client = _client(env)
    resp = client.post("/api/tasks/video",
                       json={"model_id": env.video_model.id, "text": "长" * 2001},
                       headers=_auth(env.user))
    assert resp.status_code == 400


def test_video_online_not_ready_fails_without_charge(env):
    """线上视频接口未定:提交后 failed 不扣费(密钥缺失即失败,冻结全额退回)。"""
    with TestClient(env.app) as client:
        resp = client.post("/api/tasks/video",
                           json={"model_id": env.sf_video.id, "text": "宣传片"},
                           headers=_auth(env.user))
        assert resp.status_code == 200
        task_id = resp.json()["data"]["task_id"]
        detail = _poll_task(client, task_id, env.user)
        assert detail["status"] == "failed", detail
        assert detail["error_message"]
        db = env.Session()
        task = db.get(AiTask, task_id)
        assert task.cost == 0 and task.cost_status == "refunded"
        assert db.get(Wallet, env.user.id).balance == 100  # 失败一分不扣
        db.close()


def test_video_model_type_mismatch_409(env):
    client = _client(env)
    resp = client.post("/api/tasks/video",
                       json={"model_id": env.audio_model.id, "text": "hi"},
                       headers=_auth(env.user))
    assert resp.status_code == 409
    assert resp.json()["message"] == "该模型不支持视频任务"


# ---------- 任务中心兼容 ----------

def test_task_center_filter_and_403(env):
    with TestClient(env.app) as client:
        resp = client.post("/api/tasks/audio/clone",
                           json={"model_id": env.audio_model.id, "voice_name": "alloy", "text": "hi"},
                           headers=_auth(env.user))
        task_id = resp.json()["data"]["task_id"]
        detail = _poll_task(client, task_id, env.user)
        assert detail["status"] == "succeeded"
        # task_type 筛选命中
        body = client.get("/api/tasks?task_type=audio_clone", headers=_auth(env.user)).json()["data"]
        assert body["total"] == 1 and body["items"][0]["id"] == task_id
        body = client.get("/api/tasks?task_type=video", headers=_auth(env.user)).json()["data"]
        assert body["total"] == 0
        # 他人任务 403
        assert client.get(f"/api/tasks/{task_id}", headers=_auth(env.other)).status_code == 403
        # succeeded 任务不可 retry
        assert client.post(f"/api/tasks/{task_id}/retry", headers=_auth(env.user)).status_code == 409


def test_failed_task_retry_succeeds(env, monkeypatch):
    from app.providers.mock import MockProvider

    calls = {"n": 0}
    original = MockProvider.generate_asr

    async def flaky(self, model, audio_url, params=None):
        calls["n"] += 1
        if calls["n"] == 1:
            raise Exception("模拟偶发故障")
        return await original(self, model, audio_url, params)

    monkeypatch.setattr(MockProvider, "generate_asr", flaky)
    with TestClient(env.app) as client:
        resp = client.post("/api/tasks/audio/asr",
                           json={"model_id": env.audio_model.id, "audio_url": "/static/a.mp3"},
                           headers=_auth(env.user))
        task_id = resp.json()["data"]["task_id"]
        detail = _poll_task(client, task_id, env.user)
        assert detail["status"] == "failed" and detail["error_message"] == "任务执行失败,本次不扣费"
        db = env.Session()
        assert db.get(Wallet, env.user.id).balance == 100  # 失败退费
        db.close()

        r2 = client.post(f"/api/tasks/{task_id}/retry", headers=_auth(env.user))
        assert r2.status_code == 200
        detail = _poll_task(client, task_id, env.user)
        assert detail["status"] == "succeeded" and detail["result_text"]
        assert calls["n"] == 2
        db = env.Session()
        wallet = db.get(Wallet, env.user.id)
        assert wallet.balance == 100 - PRICE_AUDIO and wallet.total_consumed == PRICE_AUDIO
        db.close()
