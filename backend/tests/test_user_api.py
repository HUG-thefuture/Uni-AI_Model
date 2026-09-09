"""用户、权限与统计接口的端到端回归测试。"""
import asyncio
import os
import tempfile
import unittest
from pathlib import Path

_DB_FILE = Path(tempfile.gettempdir()) / "uni_ai_model_test1_user_api.db"
if _DB_FILE.exists():
    _DB_FILE.unlink()
os.environ["DATABASE_URL"] = f"sqlite:///{_DB_FILE.as_posix()}"
os.environ["SECRET_KEY"] = "test-secret-key-at-least-32-bytes-long"

from fastapi.testclient import TestClient  # noqa: E402

from app.core.db import SessionLocal, async_engine, engine, init_db  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.main import app  # noqa: E402
from app.models.ai_task import AiTask  # noqa: E402
from app.models.user import User, UserProfile, Wallet  # noqa: E402
from sqlalchemy import inspect  # noqa: E402


class UserApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        init_db()
        init_db()
        expected_tables = {
            "users", "user_profiles", "wallets", "models", "ai_tasks", "ai_call_logs",
            "recharge_orders", "consumption_records", "api_keys", "api_usage_logs",
            "operation_logs", "chat_sessions", "chat_messages",
        }
        assert expected_tables.issubset(set(inspect(engine).get_table_names()))
        with SessionLocal() as db:
            admin = User(
                username="admin_test",
                password_hash=hash_password("Admin1234"),
                role="admin",
                status=1,
                real_auth_status=0,
            )
            db.add(admin)
            db.flush()
            db.add_all([
                UserProfile(user_id=admin.id, nickname="管理员"),
                Wallet(user_id=admin.id, balance=0, total_recharged=0, total_consumed=0),
            ])
            db.commit()
            cls.admin_id = admin.id
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.client.close()
        engine.dispose()
        asyncio.run(async_engine.dispose())
        if _DB_FILE.exists():
            _DB_FILE.unlink()

    def _login(self, username: str, password: str) -> str:
        response = self.client.post(
            "/api/auth/login", json={"username": username, "password": password}
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["data"]["token"]

    @staticmethod
    def _auth(token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}"}

    def test_user_admin_and_stats_flow(self) -> None:
        no_token = self.client.get("/api/auth/me")
        self.assertEqual(no_token.status_code, 401, no_token.text)
        bad_token = self.client.get(
            "/api/auth/me", headers=self._auth("not-a-valid-token")
        )
        self.assertEqual(bad_token.status_code, 401, bad_token.text)

        register = self.client.post(
            "/api/auth/register",
            json={
                "username": "student_test",
                "password": "Student1234",
                "school": "四川大学",
                "nickname": "测试学生",
            },
        )
        self.assertEqual(register.status_code, 201, register.text)
        user_id = register.json()["data"]["id"]

        user_token = self._login("student_test", "Student1234")
        profile = self.client.put(
            "/api/user/profile",
            headers=self._auth(user_token),
            json={"nickname": "新昵称", "email": "student@example.com", "bio": "测试简介"},
        )
        self.assertEqual(profile.status_code, 200, profile.text)
        self.assertEqual(profile.json()["data"]["nickname"], "新昵称")

        invalid_profile = self.client.put(
            "/api/user/profile",
            headers=self._auth(user_token),
            json={"phone": "not-a-phone", "email": "a@b@c"},
        )
        self.assertEqual(invalid_profile.status_code, 400, invalid_profile.text)

        me = self.client.get("/api/auth/me", headers=self._auth(user_token))
        self.assertEqual(me.status_code, 200, me.text)
        self.assertEqual(me.json()["data"]["profile"]["email"], "student@example.com")

        # 充值新流程:下单(pending) → 内置收银台确认支付(mock-pay) → 入账
        recharge = self.client.post(
            "/api/wallet/recharge",
            headers=self._auth(user_token),
            json={"amount": 100, "payment_method": "mock"},
        )
        self.assertEqual(recharge.status_code, 200, recharge.text)
        recharge_data = recharge.json()["data"]
        self.assertEqual(recharge_data["status"], "pending")
        order_no = recharge_data["order_no"]
        wallet = self.client.get("/api/wallet/me", headers=self._auth(user_token))
        self.assertEqual(wallet.status_code, 200, wallet.text)
        # 下单未支付,余额仅为注册赠积分
        self.assertEqual(wallet.json()["data"]["balance"], 10)
        paid = self.client.post(
            f"/api/wallet/orders/{order_no}/mock-pay", headers=self._auth(user_token)
        )
        self.assertEqual(paid.status_code, 200, paid.text)
        wallet = self.client.get("/api/wallet/me", headers=self._auth(user_token))
        # 余额 = 注册赠积分(默认 10) + 本次充值 100
        self.assertEqual(wallet.json()["data"]["balance"], 110)
        invalid_method = self.client.post(
            "/api/wallet/recharge",
            headers=self._auth(user_token),
            json={"amount": 100, "payment_method": "unknown"},
        )
        self.assertEqual(invalid_method.status_code, 400, invalid_method.text)

        denied = self.client.get("/api/admin/users", headers=self._auth(user_token))
        self.assertEqual(denied.status_code, 403, denied.text)

        admin_token = self._login("admin_test", "Admin1234")
        users = self.client.get(
            "/api/admin/users?keyword=student&page=1&page_size=10",
            headers=self._auth(admin_token),
        )
        self.assertEqual(users.status_code, 200, users.text)
        self.assertEqual(users.json()["data"]["total"], 1)
        self.assertNotIn("password_hash", users.text)

        with SessionLocal() as db:
            # 用量统计口径为 ai_tasks(成功任务):1 个成功(含 token)+1 个失败(不扣费)
            db.add_all([
                AiTask(
                    request_id="req-stats-1", user_id=self.admin_id, model_id=1,
                    task_type="text", prompt="统计用任务", status="succeeded",
                    cost=700, frozen_cost=700, cost_status="settled",  # 微元:¥0.0007
                    prompt_tokens=100, completion_tokens=50,
                ),
                AiTask(
                    request_id="req-stats-2", user_id=self.admin_id, model_id=1,
                    task_type="text", prompt="失败任务", status="failed",
                    cost=0, frozen_cost=0, cost_status="refunded",
                ),
            ])
            db.commit()

        disabled = self.client.put(
            f"/api/admin/users/{user_id}/status",
            headers=self._auth(admin_token),
            json={"status": 0},
        )
        self.assertEqual(disabled.status_code, 200, disabled.text)

        invalidated = self.client.get("/api/auth/me", headers=self._auth(user_token))
        self.assertEqual(invalidated.status_code, 401, invalidated.text)

        stats = self.client.get("/api/stats/usage", headers=self._auth(admin_token))
        self.assertEqual(stats.status_code, 200, stats.text)
        # 统一响应壳 + 明细:{"code":0,...,"data":{..., "items":[...]}}
        self.assertEqual(stats.json()["code"], 0)
        data = stats.json()["data"]
        self.assertEqual(
            {k: data[k] for k in ("total_call", "total_tokens", "total_cost")},
            {"total_call": 1, "total_tokens": 150, "total_cost": 0.0007},
        )
        self.assertEqual(len(data["items"]), 1)
        self.assertEqual(data["items"][0]["total_tokens"], 150)

        self_disable = self.client.put(
            f"/api/admin/users/{self.admin_id}/status",
            headers=self._auth(admin_token),
            json={"status": 0},
        )
        self.assertEqual(self_disable.status_code, 403, self_disable.text)

        schema = self.client.get("/openapi.json").json()
        operation_ids = [
            operation["operationId"]
            for path in schema["paths"].values()
            for operation in path.values()
            if isinstance(operation, dict) and "operationId" in operation
        ]
        self.assertEqual(len(operation_ids), len(set(operation_ids)))


if __name__ == "__main__":
    unittest.main()
