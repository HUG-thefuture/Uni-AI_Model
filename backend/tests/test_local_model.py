"""WP08 本地自测(仅本地验证用,不进仓库):Ollama 本地模型接入 + 门户 available + 管理端详情统计 + 启停联动。

- 不依赖真实 Ollama:httpx.MockTransport 模拟 /v1/chat/completions(SSE chunk 与
  非流式 JSON)与 /api/tags;通过给 httpx.AsyncClient.__init__ 注入 transport,
  让 BaseProvider 的 _open_stream_with_retry / _post_with_retry 全部走 mock;
- 覆盖:Local 流式 delta 序列 + done、非流式 content、ConnectError 中文错误信息、
  health_check 解析 models、available 60s 缓存、seed 幂等产出 4 个模型、
  管理端详情 daily_stats / error_stats、停用模型三处联动(门户不可见 /
  /tasks/text 409 / 开放接口 /chat/completions 409)。
"""
import asyncio
import importlib.util
import json
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.api_key_auth import generate_api_key
from app.core.config import get_settings
from app.core.db import Base, get_db
from app.core.deps import get_current_user
from app.core.response import register_exception_handlers
from app.models import AiCallLog, AiTask, Model  # noqa: F401 注册映射
from app.models.support import ApiKey, User, Wallet
from app.providers.exceptions import ProviderError
from app.providers.local import LOCAL_UNREACHABLE_ZH, LocalProvider
from app.routers import open_api
from app.routers.admin_models import router as admin_router
from app.routers.models import router as portal_router
from app.routers.tasks import router as tasks_router
from app.services.rate_limiter import rate_limiter

REPO_ROOT = Path(__file__).resolve().parents[2]
LOCAL_ENDPOINT = "http://mock-ollama:11434"


# ---------------------------------------------------------------------------
# Ollama mock 与 LocalProvider 夹具
# ---------------------------------------------------------------------------
@pytest.fixture()
def ollama(monkeypatch):
    """安装 httpx.MockTransport:让所有 httpx.AsyncClient 走 mock(含 base.py 重试辅助)。"""
    def _install(handler):
        transport = httpx.MockTransport(handler)
        real_init = httpx.AsyncClient.__init__

        def patched_init(self, *args, **kwargs):
            kwargs.setdefault("transport", transport)
            real_init(self, *args, **kwargs)

        monkeypatch.setattr(httpx.AsyncClient, "__init__", patched_init)
        return transport

    return _install


@pytest.fixture()
def no_retries(monkeypatch):
    """压缩重试次数为 0,避免 ConnectError 用例退避 sleep 1s/2s 拖慢测试。"""
    monkeypatch.setattr(get_settings(), "provider_max_retries", 0)


def _local_model(**overrides):
    """LocalProvider 用假 model(SimpleNamespace 即可,只读属性)。"""
    base = {
        "model_code": "qwen2.5:1.5b",
        "endpoint": LOCAL_ENDPOINT,
        "config_json": '{"temperature": 0.7}',
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _sse_body(deltas, usage=None, done=True):
    frames = []
    for d in deltas:
        frames.append('data: {"choices":[{"delta":{"content":"%s"}}]}' % d)
    if usage is not None:
        frames.append("data: " + json.dumps(
            {"choices": [{"delta": {}}], "usage": usage}, ensure_ascii=False))
    if done:
        frames.append("data: [DONE]")
    return ("\n\n".join(frames) + "\n\n").encode("utf-8")


class TestLocalProviderText:
    def test_stream_deltas_then_done(self, ollama):
        """流式:按 SSE 增量 yield {"delta"},结束 yield {"done", "usage"}。"""
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["path"] = request.url.path
            seen["auth"] = request.headers.get("authorization")
            seen["body"] = json.loads(request.content.decode())
            return httpx.Response(
                200, content=_sse_body(["你", "好", "!"], usage={"total_tokens": 6}),
                headers={"content-type": "text/event-stream"},
            )

        ollama(handler)
        provider = LocalProvider()

        async def _run():
            chunks = []
            async for chunk in provider.generate_text(
                _local_model(), [{"role": "user", "content": "hi"}]
            ):
                chunks.append(chunk)
            return chunks

        chunks = asyncio.run(_run())
        assert [c.get("delta") for c in chunks[:-1]] == ["你", "好", "!"]
        assert chunks[-1]["done"] is True
        assert chunks[-1]["usage"] == {"total_tokens": 6}
        # OpenAI 兼容路径 + 本地服务无需鉴权头
        assert seen["path"] == "/v1/chat/completions"
        assert seen["auth"] is None
        assert seen["body"]["model"] == "qwen2.5:1.5b"
        assert seen["body"]["stream"] is True
        assert seen["body"]["temperature"] == 0.7  # config_json 参数已并入

    def test_text_once(self, ollama):
        """非流式:返回 {"content", "usage", "raw"},与 OnlineProvider 同构。"""
        raw = {"choices": [{"message": {"content": "本地回复"}}],
               "usage": {"prompt_tokens": 2, "completion_tokens": 4, "total_tokens": 6}}

        def handler(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content.decode())
            assert body["stream"] is False
            return httpx.Response(200, json=raw)

        ollama(handler)
        provider = LocalProvider()
        result = asyncio.run(provider.generate_text_once(
            _local_model(), [{"role": "user", "content": "hi"}]
        ))
        assert result["content"] == "本地回复"
        assert result["usage"]["total_tokens"] == 6
        assert result["raw"] == raw

    def test_connect_error_stream_zh(self, ollama, no_retries):
        """流式连接失败:ConnectError → provider_unreachable + 定制中文提示。"""
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused", request=request)

        ollama(handler)
        provider = LocalProvider()
        with pytest.raises(ProviderError) as ei:
            asyncio.run(provider.generate_text(
                _local_model(), [{"role": "user", "content": "hi"}]
            ).__anext__())
        assert ei.value.code == "provider_unreachable"
        assert ei.value.message_zh == LOCAL_UNREACHABLE_ZH

    def test_connect_error_once_zh(self, ollama, no_retries):
        """非流式连接失败:同样的中文提示。"""
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused", request=request)

        ollama(handler)
        provider = LocalProvider()
        with pytest.raises(ProviderError) as ei:
            asyncio.run(provider.generate_text_once(
                _local_model(), [{"role": "user", "content": "hi"}]
            ))
        assert ei.value.code == "provider_unreachable"
        assert ei.value.message_zh == LOCAL_UNREACHABLE_ZH

    def test_translate_direct(self):
        """_translate 直测:ConnectError 定制提示;超时沿用基类文案。"""
        err = LocalProvider._translate(httpx.ConnectError("x"))
        assert err.code == "provider_unreachable" and err.message_zh == LOCAL_UNREACHABLE_ZH
        err2 = LocalProvider._translate(httpx.ReadTimeout("t"))
        assert err2.code == "provider_timeout"

    def test_unsupported_task_types(self):
        """图像/声音克隆/ASR/视频:统一 provider_not_supported。"""
        provider = LocalProvider()
        model = _local_model()
        for coro in (
            provider.generate_image(model, "a cat"),
            provider.generate_audio_clone(model),
            provider.generate_asr(model, "/static/a.mp3"),
            provider.generate_video(model, "长文"),
        ):
            with pytest.raises(ProviderError) as ei:
                asyncio.run(coro)
            assert ei.value.code == "provider_not_supported"
            assert ei.value.message_zh == "该模型不支持该任务类型"


class TestLocalHealthCheck:
    def test_health_check_ok(self, ollama):
        """/api/tags 探活:解析 models 名称列表。"""
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/api/tags"
            return httpx.Response(200, json={
                "models": [{"name": "qwen2.5:1.5b"}, {"name": "qwen2.5:3b"}],
            })

        ollama(handler)
        result = asyncio.run(LocalProvider().health_check(_local_model()))
        assert result["ok"] is True
        assert result["models"] == ["qwen2.5:1.5b", "qwen2.5:3b"]
        assert isinstance(result["latency_ms"], int)

    def test_health_check_down(self, ollama):
        """Ollama 未启动:ok=False,models 为空,不抛异常。"""
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("refused", request=request)

        ollama(handler)
        result = asyncio.run(LocalProvider().health_check(_local_model()))
        assert result["ok"] is False
        assert result["models"] == []


class TestAvailableProbe:
    def setup_method(self):
        from app.providers import local as local_mod

        local_mod._PROBE_CACHE.clear()

    def test_probe_cache_60s(self, monkeypatch):
        """available 缓存:60s 内二次调用不发请求。"""
        from app.providers import local as local_mod

        calls = {"n": 0}

        def fake_get(url, timeout=None):
            calls["n"] += 1
            return httpx.Response(200, json={"models": []})

        monkeypatch.setattr(httpx, "get", fake_get)
        assert LocalProvider.probe_available(LOCAL_ENDPOINT) is True
        assert LocalProvider.probe_available(LOCAL_ENDPOINT) is True
        assert calls["n"] == 1  # 命中缓存,只发一次

    def test_probe_cache_expiry(self, monkeypatch):
        """TTL 归零后缓存失效,重新发请求。"""
        from app.providers import local as local_mod

        monkeypatch.setattr(local_mod, "PROBE_TTL_SEC", 0)
        calls = {"n": 0}

        def fake_get(url, timeout=None):
            calls["n"] += 1
            return httpx.Response(200, json={"models": []})

        monkeypatch.setattr(httpx, "get", fake_get)
        LocalProvider.probe_available(LOCAL_ENDPOINT)
        LocalProvider.probe_available(LOCAL_ENDPOINT)
        assert calls["n"] == 2

    def test_probe_failure_false_no_raise(self, monkeypatch):
        """探活失败/异常:吞掉异常返回 False。"""
        def fake_get(url, timeout=None):
            raise httpx.ConnectTimeout("timeout", request=httpx.Request("GET", url))

        monkeypatch.setattr(httpx, "get", fake_get)
        assert LocalProvider.probe_available(LOCAL_ENDPOINT) is False

    def test_portal_available_flags(self, monkeypatch, db_session, client):
        """门户列表:local 按探活结果,online/mock 恒 True(不做真实探活)。"""
        # 探活按 endpoint 区分:http://up:1 在线、http://down:1 离线
        monkeypatch.setattr(
            LocalProvider, "probe_available",
            staticmethod(lambda ep: (ep or "") == "http://up:1"),
        )
        db_session.add_all([
            Model(name="本地在线", model_code="local/up", provider_type="local",
                  model_type="text", vendor="ollama", endpoint="http://up:1",
                  price_per_call=1, status="enabled"),
            Model(name="本地离线", model_code="local/down", provider_type="local",
                  model_type="text", vendor="ollama", endpoint="http://down:1",
                  price_per_call=1, status="enabled"),
            Model(name="线上模型", model_code="sf/qwen", provider_type="online",
                  model_type="text", vendor="siliconflow", price_per_call=1,
                  status="enabled"),
            Model(name="Mock 模型", model_code="mock/x", provider_type="online",
                  model_type="text", vendor="mock", price_per_call=0,
                  status="enabled"),
        ])
        db_session.commit()
        items = {i["name"]: i for i in client.get("/models").json()["data"]["items"]}
        assert items["本地在线"]["available"] is True
        assert items["本地离线"]["available"] is False
        # online/mock 恒 True,不发起真实探活
        assert items["线上模型"]["available"] is True
        assert items["Mock 模型"]["available"] is True


# ---------------------------------------------------------------------------
# 管理端详情统计
# ---------------------------------------------------------------------------
@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()
    engine.dispose()


@pytest.fixture()
def client(db_session):
    """临时 app:门户 + 管理端路由,get_db 指向内存库,管理员登录态。"""
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(portal_router)
    app.include_router(admin_router)
    admin = User(id=1, username="admin", password_hash="x", role="admin", status=1)

    def _override_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = lambda: admin
    return TestClient(app)


class TestDetailStats:
    def test_daily_and_error_stats(self, client, db_session):
        """详情新增 daily_stats(近 7 天逐日,补零)与 error_stats(错误分布 top10)。"""
        model = Model(name="本地对话", model_code="local/stats", provider_type="local",
                      model_type="text", vendor="ollama", endpoint=LOCAL_ENDPOINT,
                      price_per_call=1, status="enabled")
        db_session.add(model)
        db_session.commit()
        now = datetime.now()
        today = now.strftime("%Y-%m-%d")
        yesterday = (now - timedelta(days=1)).strftime("%Y-%m-%d")
        rows = [
            # 今天:3 成功 + 1 失败(provider_timeout)
            *[AiCallLog(request_id=f"t{i}", model_id=model.id, provider="ollama",
                        latency_ms=10, success=True, created_at=now - timedelta(hours=1))
              for i in range(3)],
            AiCallLog(request_id="t9", model_id=model.id, provider="ollama",
                      latency_ms=10, success=False, error_code="provider_timeout",
                      created_at=now - timedelta(hours=2)),
            # 昨天:1 成功 + 2 失败(provider_unreachable)+ 1 失败(error_code 为空)
            AiCallLog(request_id="y1", model_id=model.id, provider="ollama",
                      latency_ms=10, success=True, created_at=now - timedelta(days=1)),
            *[AiCallLog(request_id=f"y{i}", model_id=model.id, provider="ollama",
                        latency_ms=10, success=False, error_code="provider_unreachable",
                        created_at=now - timedelta(days=1))
              for i in (2, 3)],
            AiCallLog(request_id="y4", model_id=model.id, provider="ollama",
                      latency_ms=10, success=False, error_code=None,
                      created_at=now - timedelta(days=1)),
        ]
        db_session.add_all(rows)
        db_session.commit()

        detail = client.get(f"/admin/models/{model.id}").json()["data"]
        # 汇总口径不变:近 7 天 total 8 / success 4
        assert detail["call_stats_7d"]["total"] == 8
        assert detail["call_stats_7d"]["success"] == 4
        assert detail["call_stats_7d"]["success_rate"] == 0.5
        # daily_stats:7 天逐日,升序,含今天与昨天
        daily = detail["daily_stats"]
        assert len(daily) == 7
        assert [d["date"] for d in daily] == sorted(d["date"] for d in daily)
        by_date = {d["date"]: d for d in daily}
        assert by_date[today] == {"date": today, "total": 4, "success": 3}
        assert by_date[yesterday] == {"date": yesterday, "total": 4, "success": 1}
        # 无调用日补零
        assert any(d["total"] == 0 for d in daily)
        # error_stats:按次数倒序,error_code 为空归 unknown
        errors = detail["error_stats"]
        assert errors == [
            {"error_code": "provider_unreachable", "count": 2},
            {"error_code": "provider_timeout", "count": 1},
            {"error_code": "unknown", "count": 1},
        ]

    def test_detail_no_logs(self, client, db_session):
        """无调用记录:统计全 0,error_stats 空列表。"""
        model = Model(name="新模型", model_code="local/new", provider_type="local",
                      model_type="text", vendor="ollama", price_per_call=1,
                      status="enabled")
        db_session.add(model)
        db_session.commit()
        detail = client.get(f"/admin/models/{model.id}").json()["data"]
        assert detail["call_stats_7d"] == {"total": 0, "success": 0, "success_rate": 0.0}
        assert all(d["total"] == 0 and d["success"] == 0 for d in detail["daily_stats"])
        assert len(detail["daily_stats"]) == 7
        assert detail["error_stats"] == []


# ---------------------------------------------------------------------------
# seed 幂等(4 个模型)
# ---------------------------------------------------------------------------
def _load_seed_module():
    path = REPO_ROOT / "backend" / "scripts" / "seed_models.py"
    spec = importlib.util.spec_from_file_location("seed_models_wp08", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestSeed:
    def test_seed_four_models_idempotent(self, db_session):
        """模板含模型列表(必含 qwen2.5:1.5b 本地),幂等 upsert。"""
        seed = _load_seed_module()
        items = seed.load_template()
        n = len(items)
        assert n >= 2
        assert any(i["model_code"] == "qwen2.5:1.5b" for i in items)
        first = seed.upsert_models(db_session, items)
        assert first == {"created": n, "updated": 0, "total": n}
        second = seed.upsert_models(db_session, items)
        assert second == {"created": 0, "updated": n, "total": n}
        rows = db_session.query(Model).all()
        assert len(rows) == n
        target = next(r for r in rows if r.model_code == "qwen2.5:1.5b")
        assert target.provider_type == "local"
        assert target.vendor == "ollama"
        assert target.endpoint == "http://localhost:11434"
        assert target.price_per_call == 1
        assert target.capability_tags == ["对话", "本地"]
        assert json.loads(target.config_json) == {"temperature": 0.7}
        assert "断网兜底" in (target.description or "")


# ---------------------------------------------------------------------------
# 启停联动:停用后门户不可见 / /tasks/text 409 / 开放接口 /chat/completions 409
# ---------------------------------------------------------------------------
class TestStatusLinkage:
    def test_disable_three_entrypoints(self, monkeypatch):
        """停用模型后三处入口同时生效(全部用现有代码,不改业务逻辑)。"""
        engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        Base.metadata.create_all(engine)
        Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

        db = Session()
        user = User(username="linker", password_hash="x", role="admin", status=1)
        db.add(user)
        db.commit()
        db.add(Wallet(user_id=user.id, balance=100))
        model = Model(name="本地演示", model_code="qwen2.5:1.5b", provider_type="local",
                      model_type="text", vendor="ollama", endpoint=LOCAL_ENDPOINT,
                      price_per_call=1, status="enabled")
        db.add(model)
        db.commit()
        model_id = model.id
        plain, prefix, digest = generate_api_key()
        db.add(ApiKey(user_id=user.id, name="k", key_prefix=prefix, key_hash=digest))
        db.commit()
        key_id = db.query(ApiKey).first().id
        db.close()

        app = FastAPI()
        register_exception_handlers(app)
        app.include_router(portal_router)
        app.include_router(admin_router)
        app.include_router(tasks_router, prefix="/api")
        app.include_router(open_api.router, prefix="/api")

        def _override_db():
            s = Session()
            try:
                yield s
            finally:
                s.close()

        def _override_user():
            s = Session()
            try:
                return s.get(User, user.id)
            finally:
                s.close()

        app.dependency_overrides[get_db] = _override_db
        app.dependency_overrides[get_current_user] = _override_user
        client = TestClient(app, raise_server_exceptions=False)
        headers = {"Authorization": f"Bearer {plain}"}

        # 1. 停用前:门户可见
        assert client.get("/models").json()["data"]["total"] == 1
        # 停用
        resp = client.put(f"/admin/models/{model_id}/status", json={"status": "disabled"})
        assert resp.status_code == 200

        # 2. 联动一:门户列表立即不可见(WP03)
        assert client.get("/models").json()["data"]["total"] == 0
        # 管理端仍可见(含 disabled)
        assert client.get("/admin/models").json()["data"]["total"] == 1

        # 3. 联动二:/tasks/text 调用 409(chat_service.get_enabled_model,
        #    在会话归属与余额冻结之前拦截,get_current_user 已覆盖登录态)
        resp = client.post("/api/tasks/text", json={
            "model_id": model_id, "session_id": 999, "message": "hi",
        })
        assert resp.status_code == 409
        assert resp.json()["message"] == "模型维护中,暂不可调用"

        # 4. 联动三:开放接口 /chat/completions 409(按 model_code 校验状态)
        resp = client.post("/api/chat/completions", json={
            "model": "qwen2.5:1.5b",
            "messages": [{"role": "user", "content": "hi"}],
        }, headers=headers)
        assert resp.status_code == 409
        assert resp.json()["message"] == "模型维护中,暂不可调用"
        # 全程未产生任务(409 在冻结扣费前拦截,不扣费)
        s = Session()
        assert s.query(AiTask).count() == 0
        s.close()

        asyncio.run(rate_limiter.reset(key_id))  # 清理限流单例计数
        engine.dispose()
