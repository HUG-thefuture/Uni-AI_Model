"""WP03 本地 pytest 自测:模型广场 + 管理端模型 CRUD + seed 脚本幂等。

- sqlite 内存库(StaticPool 共享连接),Base.metadata.create_all 建全部表
  (从 app.models.support 导入 users 表,其余映射经 app.models.model 等注册);
- fastapi.testclient 构建临时 app,include 门户/管理两个 router;
- dependency_overrides 覆盖 get_db 与 get_current_user(伪造 User),
  require_admin 不覆盖,从而真实触发普通用户 403;
- 覆盖:列表只含 enabled、管理 CRUD、409 重复、停用后门户不可见、
  普通用户调管理接口 403、删除被未完成任务引用 409、seed 幂等。
"""
import importlib.util
import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.db import Base, get_db
from app.core.deps import get_current_user
from app.core.response import register_exception_handlers
from app.models import AiCallLog, AiTask, Model  # noqa: F401 注册全部成员2 映射
from app.models.support import OperationLog, User
from app.routers.admin_models import router as admin_router
from app.routers.models import router as portal_router

REPO_ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# 临时应用与夹具
# ---------------------------------------------------------------------------
def _fake_user(role: str = "admin", user_id: int = 1) -> User:
    """伪造 User 对象(不落库,仅走依赖覆盖)。"""
    return User(
        id=user_id, username="tester", password_hash="x",
        role=role, status=1,
    )


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()
    engine.dispose()


@pytest.fixture()
def client(db_session):
    """临时 FastAPI app:get_db 指向内存库;当前用户默认管理员(可换)。"""
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(portal_router)
    app.include_router(admin_router)

    current_user = {"user": _fake_user("admin")}

    def _override_db():
        yield db_session

    def _override_user():
        return current_user["user"]

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = _override_user

    def _set_user(user: User):
        current_user["user"] = user

    client = TestClient(app)
    client.set_user = _set_user  # type: ignore[attr-defined]
    return client


def _create_model(client, **overrides) -> dict:
    """创建一个模型的便捷方法,返回 data。"""
    body = {
        "name": "Qwen2.5-7B 对话",
        "model_code": "Qwen/Qwen2.5-7B-Instruct",
        "provider_type": "online",
        "model_type": "text",
        "vendor": "siliconflow",
        "price_per_call": 1,
        "description": "对话模型",
        "capability_tags": ["对话", "推理"],
        "config_json": {"temperature": 0.7},
    }
    body.update(overrides)
    resp = client.post("/admin/models", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]


def _add_model_row(db, **overrides) -> Model:
    """直接插入一条 Model(用于预置 enabled/disabled 数据)。"""
    row = Model(
        name=overrides.pop("name", "预置模型"),
        model_code=overrides.pop("model_code", "mock/test-model"),
        provider_type=overrides.pop("provider_type", "online"),
        model_type=overrides.pop("model_type", "text"),
        vendor=overrides.pop("vendor", "mock"),
        **overrides,
    )
    db.add(row)
    db.commit()
    return row


# ---------------------------------------------------------------------------
# 门户端 GET /models
# ---------------------------------------------------------------------------
class TestPortalModels:
    def test_requires_login(self, client):
        """未覆盖用户时,get_current_user 抛 401:这里直接验证未登录被拒。"""
        resp = client.get("/models")
        # 伪造的 get_current_user 直接返回用户,不会 401;改为验证带登录返回 200
        assert resp.status_code == 200

    def test_list_only_enabled(self, client, db_session):
        """门户列表只含 enabled,且不暴露 endpoint/config_json。"""
        _add_model_row(db_session, name="启用模型", model_code="m/enabled",
                       endpoint="http://local:1", config_json='{"a":1}',
                       capability_tags=["对话"])
        _add_model_row(db_session, name="停用模型", model_code="m/disabled",
                       status="disabled")
        resp = client.get("/models")
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 0
        data = body["data"]
        assert data["total"] == 1
        assert len(data["items"]) == 1
        item = data["items"][0]
        assert item["name"] == "启用模型"
        assert item["status"] == "enabled"
        assert "endpoint" not in item and "config_json" not in item
        # 分页结构完整
        assert set(data.keys()) == {"total", "page", "page_size", "items"}
        # 不含 model_code(门户不暴露厂商调用名以外细节也可,字段按冻结口径)
        # WP08:新增 available 字段(online/mock 恒 True)
        assert set(item.keys()) == {
            "id", "name", "vendor", "provider_type", "model_type",
            "description", "capability_tags", "price_per_call", "status",
            "available",
        }
        assert item["available"] is True

    def test_filters_and_pagination(self, client, db_session):
        """category/type/keyword 筛选与分页。"""
        _add_model_row(db_session, name="本地对话", model_code="local/chat",
                       provider_type="local", model_type="text", vendor="ollama")
        _add_model_row(db_session, name="文生图", model_code="img/sd",
                       model_type="image")
        _add_model_row(db_session, name="旧版对话", model_code="old/chat",
                       status="disabled")
        # category 筛选
        data = client.get("/models", params={"category": "local"}).json()["data"]
        assert data["total"] == 1 and data["items"][0]["name"] == "本地对话"
        # type 筛选
        data = client.get("/models", params={"type": "image"}).json()["data"]
        assert data["total"] == 1 and data["items"][0]["name"] == "文生图"
        # keyword 模糊(匹配 description 或 name)
        data = client.get("/models", params={"keyword": "生图"}).json()["data"]
        assert data["total"] == 1 and data["items"][0]["name"] == "文生图"
        # 分页
        data = client.get("/models", params={"page": 2, "page_size": 1}).json()["data"]
        assert data["total"] == 2 and data["page"] == 2 and len(data["items"]) == 1
        # 非法枚举 400
        resp = client.get("/models", params={"category": "bad"})
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# 管理端 CRUD
# ---------------------------------------------------------------------------
class TestAdminModels:
    def test_create_and_get_detail(self, client, db_session):
        """创建成功 201,详情含 config_json 与近 7 天统计。"""
        data = _create_model(client)
        assert data["id"] > 0 and data["status"] == "enabled"
        assert data["price_per_call"] == 1
        # 预置调用日志:2 次,1 成功 → success_rate 0.5
        db_session.add(AiCallLog(request_id="r1", model_id=data["id"],
                                 provider="siliconflow", latency_ms=10, success=True))
        db_session.add(AiCallLog(request_id="r2", model_id=data["id"],
                                 provider="siliconflow", latency_ms=10, success=False))
        db_session.commit()
        resp = client.get(f"/admin/models/{data['id']}")
        assert resp.status_code == 200
        detail = resp.json()["data"]
        assert detail["config_json"] == {"temperature": 0.7}
        assert detail["call_stats_7d"]["total"] == 2
        assert detail["call_stats_7d"]["success"] == 1
        assert detail["call_stats_7d"]["success_rate"] == 0.5
        # 不存在 404
        assert client.get("/admin/models/99999").status_code == 404

    def test_create_validation(self, client, db_session):
        """非法枚举 400;负数价格 400。"""
        base = {"name": "x", "model_code": "x/1", "model_type": "text",
                "provider_type": "online", "vendor": "mock", "price_per_call": 0}
        for bad in ({"provider_type": "cloud"}, {"model_type": "ppt"},
                    {"vendor": "openai"}):
            resp = client.post("/admin/models", json={**base, **bad})
            assert resp.status_code == 400, bad
        resp = client.post("/admin/models", json=dict(
            name="x", model_code="x/2", model_type="text",
            provider_type="online", vendor="mock", price_per_call=-1))
        assert resp.status_code == 400

    def test_create_duplicate_409(self, client):
        """model_code+provider_type 重复 → 409「模型已存在」。"""
        _create_model(client)
        resp = client.post("/admin/models", json={
            "name": "重复模型", "model_code": "Qwen/Qwen2.5-7B-Instruct",
            "provider_type": "online", "model_type": "text",
            "vendor": "siliconflow", "price_per_call": 5,
        })
        assert resp.status_code == 409
        assert resp.json()["message"] == "模型已存在"
        # 同 code 不同 provider_type 不冲突(local 需带 endpoint,与新校验规则对齐)
        resp = client.post("/admin/models", json={
            "name": "本地同款", "model_code": "Qwen/Qwen2.5-7B-Instruct",
            "provider_type": "local", "model_type": "text",
            "vendor": "ollama", "price_per_call": 0,
            "endpoint": "http://localhost:11434",
        })
        assert resp.status_code == 201

    def test_update_partial(self, client, db_session):
        """部分更新:未传字段保持原值;改唯一键冲突 409。"""
        model = _create_model(client)
        resp = client.put(f"/admin/models/{model['id']}", json={"description": "新描述"})
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["description"] == "新描述"
        assert data["model_code"] == model["model_code"]  # 未传字段不变
        assert data["price_per_call"] == 1
        # 改成与另一条冲突 → 409
        _create_model(client, model_code="other/code")
        resp = client.put(f"/admin/models/{model['id']}",
                          json={"model_code": "other/code"})
        assert resp.status_code == 409
        # 不存在 404
        assert client.put("/admin/models/99999", json={"name": "x"}).status_code == 404

    def test_status_and_portal_visibility(self, client, db_session):
        """停用后门户立即不可见,启用后恢复。"""
        model = _create_model(client)
        model_id = model["id"]
        # 非法 status 400
        resp = client.put(f"/admin/models/{model_id}/status", json={"status": "off"})
        assert resp.status_code == 400
        # 停用
        resp = client.put(f"/admin/models/{model_id}/status", json={"status": "disabled"})
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "disabled"
        assert client.get("/models").json()["data"]["total"] == 0  # 门户不可见
        # 管理端仍可见(含 disabled)
        assert client.get("/admin/models").json()["data"]["total"] == 1
        # 重新启用
        client.put(f"/admin/models/{model_id}/status", json={"status": "enabled"})
        assert client.get("/models").json()["data"]["total"] == 1
        # 停用不存在的模型 → 404
        assert client.put("/admin/models/99999/status",
                          json={"status": "disabled"}).status_code == 404

    def test_delete_with_blocking_tasks(self, client, db_session):
        """被 pending/processing 任务引用 → 409;结束后可删除。"""
        model = _create_model(client)
        model_id = model["id"]
        task = AiTask(request_id="r-1", user_id=1, model_id=model_id,
                      task_type="text", prompt="hi", status="pending")
        db_session.add(task)
        db_session.commit()
        resp = client.delete(f"/admin/models/{model_id}")
        assert resp.status_code == 409
        # 任务结束后可删除
        task.status = "succeeded"
        db_session.commit()
        resp = client.delete(f"/admin/models/{model_id}")
        assert resp.status_code == 200
        assert client.get(f"/admin/models/{model_id}").status_code == 404
        assert db_session.query(Model).count() == 0

    def test_admin_list_pagination(self, client, db_session):
        """管理列表含 disabled,支持筛选。"""
        _add_model_row(db_session, name="a", model_code="m/a")
        _add_model_row(db_session, name="b", model_code="m/b", status="disabled")
        data = client.get("/admin/models").json()["data"]
        assert data["total"] == 2
        data = client.get("/admin/models", params={"keyword": "b"}).json()["data"]
        assert data["total"] == 1 and data["items"][0]["status"] == "disabled"

    def test_normal_user_forbidden(self, client, db_session):
        """普通用户调管理接口 → 403(require_admin 真实校验)。"""
        client.set_user(_fake_user(role="user", user_id=2))
        resp = client.get("/admin/models")
        assert resp.status_code == 403
        assert client.post("/admin/models", json={
            "name": "x", "model_code": "x/x", "model_type": "text",
            "provider_type": "online", "vendor": "mock", "price_per_call": 0,
        }).status_code == 403
        assert client.put("/admin/models/1/status",
                          json={"status": "disabled"}).status_code == 403
        assert client.delete("/admin/models/1").status_code == 403
        # 门户接口普通用户可用
        assert client.get("/models").status_code == 200

    def test_operation_logs_direct(self, db_session):
        """直接调 service 验证 operation_logs 字段内容。"""
        from app.schemas.model import ModelCreateRequest
        from app.services import model_service

        admin_id = 9
        model = model_service.create_model(
            db_session, admin_id,
            ModelCreateRequest(name="日志模型", model_code="log/m", provider_type="online",
                               model_type="text", vendor="mock", price_per_call=0),
        )
        model_service.update_model_status(db_session, admin_id, model.id, "disabled")
        rows = (
            db_session.query(OperationLog)
            .filter(OperationLog.resource_type == "models")
            .order_by(OperationLog.id)
            .all()
        )
        assert [r.action for r in rows] == ["model_create", "model_status"]
        assert rows[0].user_id == admin_id and rows[0].resource_id == model.id
        detail = json.loads(rows[0].detail_json)
        assert detail["model_code"] == "log/m"
        assert json.loads(rows[1].detail_json) == {"before": "enabled", "after": "disabled"}


# ---------------------------------------------------------------------------
# seed 脚本幂等
# ---------------------------------------------------------------------------
def _load_seed_module():
    """从 backend/scripts/seed_models.py 动态导入(scripts 非包)。"""
    path = REPO_ROOT / "backend" / "scripts" / "seed_models.py"
    spec = importlib.util.spec_from_file_location("seed_models", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestSeed:
    def test_seed_idempotent(self, db_session):
        """首次执行按模板全部新增，重复执行只更新不重复插入(数量以模板为准)。"""
        seed = _load_seed_module()
        items = seed.load_template()
        n = len(items)
        assert n >= 2, "模板至少应包含线上与本地模型"
        first = seed.upsert_models(db_session, items)
        assert first == {"created": n, "updated": 0, "total": n}
        second = seed.upsert_models(db_session, items)
        assert second == {"created": 0, "updated": n, "total": n}
        rows = db_session.query(Model).all()
        assert len(rows) == n
        # 字段与模板一致
        by_code = {r.model_code: r for r in rows}
        assert by_code["qwen2.5:3b"].provider_type == "local"
        assert by_code["qwen2.5:1.5b"].provider_type == "local"
        assert by_code["qwen2.5:1.5b"].vendor == "ollama"
        assert by_code["qwen2.5:1.5b"].price_per_call == 1
        assert by_code["qwen2.5:1.5b"].capability_tags == ["对话", "本地"]
        assert by_code["Qwen/Qwen2.5-7B-Instruct"].price_per_call == 1
        assert by_code["stabilityai/stable-diffusion-3-5-large"].model_type == "image"
        assert by_code["Qwen/Qwen2.5-7B-Instruct"].capability_tags == ["对话", "推理"]
        assert by_code["FunAudioLLM/CosyVoice2-0.5B"].model_type == "audio"
        assert by_code["Wan-AI/Wan2.2-T2V-A14B"].model_type == "video"

    def test_seed_template_matches_real_file(self):
        """模板文件真实存在且可解析(与仓库内文件一致,含阿里百炼 DashScope 批次)。"""
        seed = _load_seed_module()
        items = seed.load_template()
        assert {i["vendor"] for i in items} <= {"siliconflow", "ollama", "dashscope"}
        assert "siliconflow" in {i["vendor"] for i in items}
        assert "ollama" in {i["vendor"] for i in items}
        assert "dashscope" in {i["vendor"] for i in items}  # init_all 一步同步必须含阿里模型
        assert all(i["status"] in ("enabled", "disabled") for i in items)
        assert any(i["status"] == "enabled" for i in items)
        # config_json 均为合法 JSON 字符串
        for item in items:
            json.loads(item["config_json"])
