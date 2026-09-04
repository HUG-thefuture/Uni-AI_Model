"""WP06 本地自测:API Key 鉴权中间件 + OpenAI 兼容开放接口(仅本地验证用,不进仓库)。

覆盖:无 Key 401 / 伪造 Key 401 / 禁用与过期 401 / 限流 429 / 模型停用 409 /
非流式成功扣费 / 流式成功扣费 / 生成失败退费(不扣费)。
"""
import asyncio
from datetime import datetime
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.api_key_auth import generate_api_key
from app.core.db import Base, get_db
from app.core.response import register_exception_handlers
from app.models.ai_task import AiTask
from app.models.model import Model
from app.models.support import ApiKey, ApiUsageLog, User, Wallet
from app.routers import open_api
from app.services.rate_limiter import rate_limiter


@pytest.fixture()
def env(monkeypatch):
    """sqlite 内存库 + TestClient:只覆盖 get_db,require_api_key 走真实逻辑。"""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(open_api.router, prefix="/api")

    def _override_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_db
    # SSE 生成器内自建会话:同样绑定到测试库
    monkeypatch.setattr(open_api, "SessionLocal", TestingSession)

    # 基础数据:User / Wallet(100) / Model(mock-chat) / ApiKey
    db = TestingSession()
    user = User(username="opener", password_hash="x", status=1)
    db.add(user)
    db.commit()
    db.add(Wallet(user_id=user.id, balance=100, total_recharged=100))
    model = Model(
        name="Mock 对话", model_code="mock-chat", provider_type="online",
        model_type="text", vendor="mock", price_per_call=1, status="enabled",
    )
    db.add(model)
    db.commit()
    plain, prefix, digest = generate_api_key()
    key = ApiKey(user_id=user.id, name="test-key", key_prefix=prefix, key_hash=digest)
    db.add(key)
    db.commit()
    key_id, model_id, user_id = key.id, model.id, user.id
    db.close()

    client = TestClient(app, raise_server_exceptions=False)
    yield SimpleNamespace(
        client=client, Session=TestingSession, key_id=key_id, model_id=model_id,
        user_id=user_id, plain=plain,
    )
    asyncio.run(rate_limiter.reset(key_id))  # 清理单例限流计数,避免串扰
    engine.dispose()


def _headers(env, plain=None):
    return {"Authorization": f"Bearer {plain or env.plain}"}


def _body(model="mock-chat", stream=False):
    return {
        "model": model,
        "messages": [{"role": "user", "content": "你好,开放接口"}],
        "stream": stream,
    }


def _wallet(env):
    db = env.Session()
    try:
        db.expire_all()
        return db.get(Wallet, env.user_id)
    finally:
        db.close()


def _task(env):
    db = env.Session()
    try:
        db.expire_all()
        return db.query(AiTask).order_by(AiTask.id.desc()).first()
    finally:
        db.close()


# ---------- 1. 鉴权拦截 ----------

def test_missing_key_401(env):
    resp = env.client.post("/api/chat/completions", json=_body())
    assert resp.status_code == 401
    data = resp.json()
    assert data["code"] != 0 and data["data"] is None
    assert data["message"] == "缺少API Key"
    assert data["request_id"]


def test_fake_key_401(env):
    resp = env.client.post(
        "/api/chat/completions", json=_body(),
        headers=_headers(env, plain="sk-" + "0" * 32),
    )
    assert resp.status_code == 401
    assert resp.json()["message"] == "API Key 无效或已禁用"


def test_bad_format_key_401(env):
    resp = env.client.post(
        "/api/chat/completions", json=_body(), headers={"Authorization": "Bearer abc123"}
    )
    assert resp.status_code == 401
    assert resp.json()["message"] == "缺少API Key"


def test_disabled_key_401_immediately(env):
    db = env.Session()
    key = db.get(ApiKey, env.key_id)
    key.status = "disabled"
    db.commit()
    db.close()

    resp = env.client.post("/api/chat/completions", json=_body(), headers=_headers(env))
    assert resp.status_code == 401
    assert resp.json()["message"] == "API Key 无效或已禁用"


def test_expired_key_401(env):
    db = env.Session()
    key = db.get(ApiKey, env.key_id)
    key.expires_at = datetime(2000, 1, 1)
    db.commit()
    db.close()

    resp = env.client.post("/api/chat/completions", json=_body(), headers=_headers(env))
    assert resp.status_code == 401
    assert resp.json()["message"] == "API Key 无效或已禁用"


# ---------- 2. 限流 ----------

def test_rate_limit_429(env, monkeypatch):
    from app.services import rate_limiter as rl_mod

    # 上限压到 1,先灌满窗口,再调用应 429(不触发 Provider)
    monkeypatch.setattr(
        rl_mod, "get_settings",
        lambda: SimpleNamespace(openapi_rate_limit_per_min=1),
    )
    asyncio.run(rl_mod.rate_limiter.check(env.key_id))  # 灌满(1/1)
    resp = env.client.post("/api/chat/completions", json=_body(), headers=_headers(env))
    assert resp.status_code == 429
    assert resp.json()["message"] == "请求过于频繁,请稍后重试"
    asyncio.run(rl_mod.rate_limiter.reset(env.key_id))
    # 清零后恢复
    db = env.Session()
    key = db.get(ApiKey, env.key_id)
    key.status = "enabled"
    db.commit()
    db.close()


# ---------- 3. 模型状态 ----------

def test_model_disabled_409(env):
    db = env.Session()
    model = db.get(Model, env.model_id)
    model.status = "disabled"
    db.commit()
    db.close()

    resp = env.client.post("/api/chat/completions", json=_body(), headers=_headers(env))
    assert resp.status_code == 409
    assert resp.json()["message"] == "模型维护中,暂不可调用"


def test_model_not_found_404(env):
    resp = env.client.post(
        "/api/chat/completions", json=_body(model="no-such-model"), headers=_headers(env)
    )
    assert resp.status_code == 404
    assert resp.json()["message"] == "模型不存在"


# ---------- 4. 非流式成功 ----------

def test_non_stream_success_bills_once(env):
    resp = env.client.post(
        "/api/chat/completions", json=_body(stream=False), headers=_headers(env)
    )
    assert resp.status_code == 200
    data = resp.json()
    # OpenAI 兼容结构
    assert data["object"] == "chat.completion"
    assert data["id"].startswith("chatcmpl-")
    assert data["model"] == "mock-chat"
    assert data["choices"][0]["message"]["role"] == "assistant"
    assert data["choices"][0]["message"]["content"]
    assert data["choices"][0]["finish_reason"] == "stop"
    assert data["usage"]["total_tokens"] > 0
    assert data["usage"]["total_tokens"] == (
        data["usage"]["prompt_tokens"] + data["usage"]["completion_tokens"]
    )

    # 扣费:balance 99 / total_consumed 1
    wallet = _wallet(env)
    assert wallet.balance == 99
    assert wallet.total_consumed == 1

    # 任务:成功 + 已结算
    task = _task(env)
    assert task.status == "succeeded"
    assert task.cost_status == "settled"
    assert task.cost == 1
    assert task.result_text

    # 统计:api_usage_logs 200
    db = env.Session()
    usage = db.query(ApiUsageLog).order_by(ApiUsageLog.id.desc()).first()
    assert usage is not None and usage.status_code == 200
    assert usage.key_id == env.key_id and usage.user_id == env.user_id
    assert usage.path == "/api/chat/completions"
    db.close()

    # use_count 累加
    db = env.Session()
    db.expire_all()
    assert db.get(ApiKey, env.key_id).use_count == 1
    db.close()


# ---------- 5. 流式成功(别名路径 /api/v1/chat/completions) ----------

def test_stream_success_via_alias_path(env):
    resp = env.client.post(
        "/api/v1/chat/completions", json=_body(stream=True), headers=_headers(env)
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")
    text = resp.text
    assert "chat.completion.chunk" in text
    assert '"finish_reason":"stop"' in text.replace(" ", "")
    assert "[DONE]" in text
    assert '"error"' not in text

    # 扣费正确
    wallet = _wallet(env)
    assert wallet.balance == 99
    assert wallet.total_consumed == 1
    task = _task(env)
    assert task.status == "succeeded"
    assert task.cost_status == "settled"


# ---------- 6. 失败不扣费 ----------

def test_provider_failure_refunds(env, monkeypatch):
    from app.providers.exceptions import ProviderError

    class BoomProvider:
        vendor = "mock"

        async def generate_text_once(self, model, messages, params=None):
            raise ProviderError("provider_timeout", "模型服务响应超时,请稍后重试")

    monkeypatch.setattr(open_api, "get_provider", lambda model: BoomProvider())

    resp = env.client.post(
        "/api/chat/completions", json=_body(stream=False), headers=_headers(env)
    )
    assert resp.status_code == 502
    data = resp.json()
    assert data["message"] == "生成失败,本次不扣费"

    # 失败释放:balance 回到 100,total_consumed 0
    wallet = _wallet(env)
    assert wallet.balance == 100
    assert wallet.total_consumed == 0
    task = _task(env)
    assert task.status == "failed"
    assert task.cost == 0
    assert task.cost_status == "refunded"

    db = env.Session()
    usage = db.query(ApiUsageLog).order_by(ApiUsageLog.id.desc()).first()
    assert usage is not None and usage.status_code == 502
    db.close()


def test_insufficient_balance_409(env):
    db = env.Session()
    wallet = db.get(Wallet, env.user_id)
    wallet.balance = 0
    db.commit()
    db.close()

    resp = env.client.post(
        "/api/chat/completions", json=_body(stream=False), headers=_headers(env)
    )
    assert resp.status_code == 409
    assert resp.json()["message"] == "积分不足,请先充值"
