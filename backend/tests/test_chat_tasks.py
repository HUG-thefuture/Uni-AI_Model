"""WP04+WP05 本地自测(不进仓库验收,pytest 直接跑):
- SSE 流式对话:delta 序列、末帧 task_id/cost、会话与消息落库、余额扣减正确;
- 失败退费:中途异常 → error 帧 + 任务 failed + 余额还原;
- 校验:模型 404/409、余额不足 409、会话 403;
- 图像四态:提交 pending → 后台执行 → succeeded(轮询详情)、重复 request_id 409;
- 任务中心:分页/筛选/elapsed_sec、failed 任务 retry 后成功、文本任务 retry 409。
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

from app.core.db import Base, get_db
from app.core.request_id import RequestIdMiddleware
from app.core.response import register_exception_handlers
from app.core.security import create_access_token
from app.models import ChatMessage, Model, User, Wallet
from app.models.ai_task import AiTask
from app.routers import chat as chat_router
from app.routers import tasks as tasks_router
from app.services import chat_service, task_service

PRICE_TEXT = 5
PRICE_IMAGE = 10


@pytest.fixture()
def env(monkeypatch):
    """sqlite 内存库 + dependency_overrides + 压缩 Mock 延迟的完整测试环境。"""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    # 服务内部新开的 Session 全部指向测试库
    monkeypatch.setattr(chat_service, "SessionLocal", Session)
    monkeypatch.setattr(task_service, "SessionLocal", Session)
    # Mock 的 2-5s 模拟延迟压缩到毫秒级
    monkeypatch.setattr(random, "uniform", lambda a, b: 0.01)

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
    text_model = Model(name="Mock 对话", model_code="mock-chat", provider_type="online",
                       model_type="text", vendor="mock", price_per_call=PRICE_TEXT,
                       status="enabled")
    image_model = Model(name="Mock 生图", model_code="mock-image", provider_type="online",
                        model_type="image", vendor="mock", price_per_call=PRICE_IMAGE,
                        status="enabled")
    disabled = Model(name="维护中", model_code="mock-x", provider_type="online",
                     model_type="text", vendor="mock", price_per_call=1, status="disabled")
    sf_image = Model(name="硅基生图", model_code="Kwai-Kolors/Kolors", provider_type="online",
                     model_type="image", vendor="siliconflow", price_per_call=PRICE_IMAGE,
                     status="enabled")
    db.add_all([text_model, image_model, disabled, sf_image])
    db.commit()
    for m in (text_model, image_model, disabled, sf_image):
        db.refresh(m)
    db.close()

    app = FastAPI()
    register_exception_handlers(app)
    app.add_middleware(RequestIdMiddleware)
    app.include_router(chat_router.router, prefix="/api")
    app.include_router(tasks_router.router, prefix="/api")

    def _override_db():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = _override_db

    return SimpleNamespace(app=app, Session=Session, user=user, other=other,
                           text_model=text_model, image_model=image_model,
                           disabled=disabled, sf_image=sf_image)


def _auth(user) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role)}"}


def _client(env) -> TestClient:
    return TestClient(env.app, raise_server_exceptions=False)


def _sse_frames(raw: str) -> list[dict]:
    frames = []
    for part in raw.split("\n\n"):
        part = part.strip()
        if part.startswith("data:"):
            frames.append(json.loads(part[5:].strip()))
    return frames


def _create_session(client, env, model_id: int, user=None) -> int:
    resp = client.post("/api/chat/sessions", json={"model_id": model_id},
                       headers=_auth(user or env.user))
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]["session_id"]


def _poll_task(client, task_id: int, user, timeout: float = 5.0) -> dict:
    deadline = time.monotonic() + timeout
    detail = {}
    while time.monotonic() < deadline:
        detail = client.get(f"/api/tasks/{task_id}", headers=_auth(user)).json()["data"]
        if detail["status"] in ("succeeded", "failed"):
            return detail
        time.sleep(0.05)
    return detail


# ---------- 会话 ----------

def test_create_and_list_sessions(env):
    client = _client(env)
    sid1 = _create_session(client, env, env.text_model.id)
    sid2 = _create_session(client, env, env.text_model.id)
    body = client.get("/api/chat/sessions", headers=_auth(env.user)).json()["data"]
    assert body["total"] == 2 and len(body["items"]) == 2
    assert {i["session_id"] for i in body["items"]} == {sid1, sid2}
    assert all(i["title"] == "新会话" for i in body["items"])
    # 未登录 401
    assert client.post("/api/chat/sessions", json={"model_id": env.text_model.id}).status_code == 401


def test_session_messages_order_and_403(env):
    client = _client(env)
    sid = _create_session(client, env, env.text_model.id)
    message = "帮我写一段大学社团招新宣传语,要押韵一点"
    with client.stream("POST", "/api/tasks/text",
                       json={"session_id": sid, "model_id": env.text_model.id, "message": message},
                       headers=_auth(env.user)) as resp:
        assert resp.status_code == 200
        "".join(resp.iter_text())
    body = client.get(f"/api/chat/sessions/{sid}/messages", headers=_auth(env.user)).json()["data"]
    roles = [m["role"] for m in body["items"]]
    assert roles == ["user", "assistant"]
    assert body["items"][0]["content"] == message
    assert body["title"] == message[:20]  # 首条消息前 20 字
    # 他人会话 403
    assert client.get(f"/api/chat/sessions/{sid}/messages",
                      headers=_auth(env.other)).status_code == 403
    # 不存在 404
    assert client.get("/api/chat/sessions/99999/messages",
                      headers=_auth(env.user)).status_code == 404


# ---------- 文本 SSE 流式 ----------

def test_text_stream_success(env):
    client = _client(env)
    sid = _create_session(client, env, env.text_model.id)
    message = "用一句话介绍四川高校 AI 大模型门户"
    with client.stream("POST", "/api/tasks/text",
                       json={"session_id": sid, "model_id": env.text_model.id, "message": message},
                       headers=_auth(env.user)) as resp:
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        assert resp.headers["cache-control"] == "no-cache"
        assert resp.headers["x-accel-buffering"] == "no"
        raw = "".join(resp.iter_text())
    frames = _sse_frames(raw)
    deltas = [f["delta"] for f in frames if "delta" in f]
    assert deltas and all(isinstance(d, str) and d for d in deltas)  # 逐段 delta 序列
    last = frames[-1]
    assert last["done"] is True and last["cost"] == PRICE_TEXT  # 末帧含 task_id/cost
    task_id = last["task_id"]

    db = env.Session()
    task = db.get(AiTask, task_id)
    assert task.status == "succeeded" and task.cost_status == "settled"
    assert task.cost == PRICE_TEXT and task.latency_ms is not None
    reply = task.result_text
    assert reply == "".join(deltas) and reply
    msgs = db.query(ChatMessage).filter_by(session_id=sid).order_by(ChatMessage.id).all()
    assert [m.role for m in msgs] == ["user", "assistant"]
    assert msgs[1].tokens_used > 0
    wallet = db.get(Wallet, env.user.id)
    assert wallet.balance == 100 - PRICE_TEXT and wallet.total_consumed == PRICE_TEXT
    db.close()


def test_text_stream_failure_refunds(env, monkeypatch):
    from app.providers.exceptions import ProviderError
    from app.providers.mock import MockProvider

    async def boom(self, model, messages, params=None):
        yield {"delta": "部分"}
        raise ProviderError("provider_upstream", "上游返回错误", "raw")

    monkeypatch.setattr(MockProvider, "generate_text", boom)
    client = _client(env)
    sid = _create_session(client, env, env.text_model.id)
    with client.stream("POST", "/api/tasks/text",
                       json={"session_id": sid, "model_id": env.text_model.id, "message": "hi"},
                       headers=_auth(env.user)) as resp:
        assert resp.status_code == 200
        raw = "".join(resp.iter_text())
    frames = _sse_frames(raw)
    assert frames[-1]["error"]["code"] == "provider_upstream"
    msg = frames[-1]["error"]["message"]
    assert "本次不扣费" in msg  # 铁律文案必须保留
    assert "上游返回错误" in msg  # 上游详情透传给用户可排查
    db = env.Session()
    task = db.get(AiTask, frames[-1].get("task_id") or _latest_task(db, env.user.id))
    assert task.status == "failed" and task.cost == 0 and task.cost_status == "refunded"
    assert task.error_message
    assert db.get(Wallet, env.user.id).balance == 100  # 退费,一分不扣
    db.close()


def _latest_task(db, user_id: int) -> int:
    return db.query(AiTask).filter_by(user_id=user_id).order_by(AiTask.id.desc()).first().id


def test_text_insufficient_balance_409(env):
    client = _client(env)
    sid = _create_session(client, env, env.text_model.id)
    db = env.Session()
    db.get(Wallet, env.user.id).balance = 1
    db.commit()
    db.close()
    resp = client.post("/api/tasks/text",
                       json={"session_id": sid, "model_id": env.text_model.id, "message": "hi"},
                       headers=_auth(env.user))
    assert resp.status_code == 409
    assert resp.json()["message"] == "积分不足,请先充值"
    db = env.Session()
    assert db.query(AiTask).count() == 0  # 未建任务
    assert db.get(Wallet, env.user.id).balance == 1
    db.close()


def test_disabled_and_missing_model(env):
    client = _client(env)
    # 不存在 404
    assert client.post("/api/chat/sessions", json={"model_id": 99999},
                       headers=_auth(env.user)).status_code == 404
    # 停用 409「模型维护中,暂不可调用」
    resp = client.post("/api/chat/sessions", json={"model_id": env.disabled.id},
                       headers=_auth(env.user))
    assert resp.status_code == 409
    assert resp.json()["message"] == "模型维护中,暂不可调用"
    sid = _create_session(client, env, env.text_model.id)
    resp = client.post("/api/tasks/text",
                       json={"session_id": sid, "model_id": env.disabled.id, "message": "hi"},
                       headers=_auth(env.user))
    assert resp.status_code == 409
    assert resp.json()["message"] == "模型维护中,暂不可调用"


# ---------- 图像四态任务 ----------

def test_image_task_flow_to_succeeded(env):
    client = _client(env)
    with TestClient(env.app) as ctx_client:  # 上下文模式:后台 create_task 在请求间持续执行
        resp = ctx_client.post(
            "/api/tasks/image",
            json={"model_id": env.image_model.id, "prompt": "一只熊猫",
                  "params": {"num": 2, "image_size": "1024x1024"}},
            headers=_auth(env.user),
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["status"] == "pending"
        detail = _poll_task(ctx_client, data["task_id"], env.user)
        assert detail["status"] == "succeeded", detail
        assert isinstance(detail["result_urls"], list) and len(detail["result_urls"]) == 2
        assert all(u.startswith("http") for u in detail["result_urls"])
        db = env.Session()
        task = db.get(AiTask, data["task_id"])
        assert task.cost_status == "settled" and task.cost == PRICE_IMAGE
        assert json.loads(task.result_url) == detail["result_urls"]
        wallet = db.get(Wallet, env.user.id)
        assert wallet.balance == 100 - PRICE_IMAGE and wallet.total_consumed == PRICE_IMAGE
        db.close()
        # succeeded 任务不可 retry
        assert ctx_client.post(f"/api/tasks/{data['task_id']}/retry",
                               headers=_auth(env.user)).status_code == 409


def test_image_duplicate_request_id_409(env, monkeypatch):
    monkeypatch.setattr(task_service, "start_background_task", lambda task_id: None)
    client = _client(env)
    headers = {**_auth(env.user), "X-Request-Id": "dup-req-1"}
    first = client.post("/api/tasks/image",
                        json={"model_id": env.image_model.id, "prompt": "a"}, headers=headers)
    assert first.status_code == 200
    second = client.post("/api/tasks/image",
                         json={"model_id": env.image_model.id, "prompt": "b"}, headers=headers)
    assert second.status_code == 409
    assert second.json()["message"] == "请勿重复提交"


def test_image_params_validation_400(env):
    client = _client(env)
    resp = client.post("/api/tasks/image",
                       json={"model_id": env.image_model.id, "prompt": "a", "params": {"num": 5}},
                       headers=_auth(env.user))
    assert resp.status_code == 400
    resp = client.post("/api/tasks/image",
                       json={"model_id": env.image_model.id, "prompt": "a",
                             "params": {"num": 0}},
                       headers=_auth(env.user))
    assert resp.status_code == 400


def test_image_model_type_mismatch(env):
    client = _client(env)
    resp = client.post("/api/tasks/image",
                       json={"model_id": env.text_model.id, "prompt": "a"},
                       headers=_auth(env.user))
    assert resp.status_code == 409


def test_image_fail_then_retry_succeeds(env, monkeypatch):
    from app.providers.exceptions import ProviderError
    from app.providers.online import OnlineProvider

    calls = {"n": 0}

    async def flaky(self, model, prompt, params=None):
        calls["n"] += 1
        if calls["n"] == 1:
            raise ProviderError("provider_upstream", "上游服务开小差", "raw")
        return {"image_urls": ["https://dummyimage.com/1.png", "https://dummyimage.com/2.png"],
                "raw": {"flaky": True}}

    monkeypatch.setattr(OnlineProvider, "generate_image", flaky)
    with TestClient(env.app) as client:
        resp = client.post("/api/tasks/image",
                           json={"model_id": env.sf_image.id, "prompt": "校园晚霞"},
                           headers=_auth(env.user))
        task_id = resp.json()["data"]["task_id"]
        detail = _poll_task(client, task_id, env.user)
        assert detail["status"] == "failed", detail
        assert detail["error_message"] == "上游服务开小差"
        db = env.Session()
        assert db.get(Wallet, env.user.id).balance == 100  # 失败退费
        task = db.get(AiTask, task_id)
        assert task.cost == 0 and task.cost_status == "refunded"
        db.close()

        # retry → pending → succeeded
        r2 = client.post(f"/api/tasks/{task_id}/retry", headers=_auth(env.user))
        assert r2.status_code == 200
        assert r2.json()["data"] == {"task_id": task_id, "status": "pending"}
        detail = _poll_task(client, task_id, env.user)
        assert detail["status"] == "succeeded", detail
        assert calls["n"] == 2
        db = env.Session()
        wallet = db.get(Wallet, env.user.id)
        assert wallet.balance == 100 - PRICE_IMAGE and wallet.total_consumed == PRICE_IMAGE
        db.close()


def test_text_task_retry_409(env):
    client = _client(env)
    sid = _create_session(client, env, env.text_model.id)
    with client.stream("POST", "/api/tasks/text",
                       json={"session_id": sid, "model_id": env.text_model.id, "message": "hi"},
                       headers=_auth(env.user)) as resp:
        "".join(resp.iter_text())
    db = env.Session()
    task_id = _latest_task(db, env.user.id)
    db.close()
    resp = client.post(f"/api/tasks/{task_id}/retry", headers=_auth(env.user))
    assert resp.status_code == 409
    assert resp.json()["message"] == "请在会话中重新发送"


# ---------- 任务中心 ----------

def test_task_list_filter_and_elapsed(env):
    client = _client(env)
    db = env.Session()
    t = AiTask(request_id="r-proc", user_id=env.user.id, model_id=env.text_model.id,
               task_type="text", prompt="处理中", status="processing",
               cost_status="frozen", cost=PRICE_TEXT)
    db.add(t)
    db.commit()
    db.refresh(t)
    proc_id = t.id
    db.close()
    body = client.get("/api/tasks?task_type=image", headers=_auth(env.user)).json()["data"]
    assert body["total"] == 0
    body = client.get("/api/tasks?task_type=text&page=1&page_size=10",
                      headers=_auth(env.user)).json()["data"]
    assert body["total"] == 1 and body["page_size"] == 10
    item = body["items"][0]
    assert item["id"] == proc_id and item["status"] == "processing"
    assert "elapsed_sec" in item and item["elapsed_sec"] >= 0
    for key in ("task_type", "prompt", "result_text", "result_url",
                "error_message", "cost", "latency_ms", "created_at"):
        assert key in item


def test_task_detail_403_and_404(env):
    client = _client(env)
    db = env.Session()
    t = AiTask(request_id="r-403", user_id=env.user.id, model_id=env.image_model.id,
               task_type="image", prompt="p", status="succeeded",
               result_url='["/static/a.png","/static/b.png"]',
               cost_status="settled", cost=PRICE_IMAGE)
    db.add(t)
    db.commit()
    db.refresh(t)
    task_id = t.id
    db.close()
    body = client.get(f"/api/tasks/{task_id}", headers=_auth(env.user)).json()["data"]
    assert body["result_urls"] == ["/static/a.png", "/static/b.png"]
    assert client.get(f"/api/tasks/{task_id}", headers=_auth(env.other)).status_code == 403
    assert client.get("/api/tasks/99999", headers=_auth(env.user)).status_code == 404
