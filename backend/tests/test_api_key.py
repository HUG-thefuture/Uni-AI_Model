"""API Key 管理(创建/停用/删除)回归测试。"""
import asyncio
import os
import tempfile
import unittest
from pathlib import Path

_DB_FILE = Path(tempfile.gettempdir()) / "uni_ai_model_test1_apikey.db"
if _DB_FILE.exists():
    _DB_FILE.unlink()
os.environ["DATABASE_URL"] = f"sqlite:///{_DB_FILE.as_posix()}"
os.environ["SECRET_KEY"] = "test-secret-key-at-least-32-bytes-long"

from fastapi.testclient import TestClient  # noqa: E402

from app.core.db import SessionLocal, async_engine, engine, init_db  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.main import app  # noqa: E402
from app.models.user import User, UserProfile  # noqa: E402


class ApiKeyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        init_db()
        with SessionLocal() as db:
            for name in ("keyer_a", "keyer_b"):
                user = User(username=name, password_hash=hash_password("Key12345"),
                            role="user", status=1)
                db.add(user)
                db.flush()
                db.add(UserProfile(user_id=user.id, nickname=name))
            db.commit()
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.client.close()
        engine.dispose()
        asyncio.run(async_engine.dispose())
        if _DB_FILE.exists():
            _DB_FILE.unlink()

    def _login(self, username: str) -> str:
        response = self.client.post(
            "/api/auth/login", json={"username": username, "password": "Key12345"}
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["data"]["token"]

    @staticmethod
    def _auth(token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}"}

    def test_create_disable_delete_flow(self) -> None:
        token = self._login("keyer_a")

        created = self.client.post(
            "/api/api_keys", headers=self._auth(token), json={"name": "联调"}
        )
        self.assertEqual(created.status_code, 200, created.text)
        key_id = created.json()["data"]["id"]
        self.assertTrue(created.json()["data"]["key"].startswith("sk-"))

        # 停用 → 启用 → 删除
        disabled = self.client.put(
            f"/api/api_keys/{key_id}/status", headers=self._auth(token),
            json={"status": "disabled"},
        )
        self.assertEqual(disabled.status_code, 200, disabled.text)
        self.assertEqual(disabled.json()["data"]["status"], "disabled")

        deleted = self.client.delete(f"/api/api_keys/{key_id}", headers=self._auth(token))
        self.assertEqual(deleted.status_code, 200, deleted.text)
        self.assertEqual(deleted.json()["data"]["id"], key_id)

        keys = self.client.get("/api/api_keys", headers=self._auth(token))
        ids = [k["id"] for k in keys.json()["data"]]
        self.assertNotIn(key_id, ids)  # 被删的 Key 已不在列表中

        # 重复删除 → 404
        again = self.client.delete(f"/api/api_keys/{key_id}", headers=self._auth(token))
        self.assertEqual(again.status_code, 404, again.text)

    def test_cannot_delete_others_key(self) -> None:
        token_a = self._login("keyer_a")
        token_b = self._login("keyer_b")

        created = self.client.post(
            "/api/api_keys", headers=self._auth(token_a), json={"name": "A的Key"}
        )
        key_id = created.json()["data"]["id"]

        # B 删除 A 的 Key → 404(不泄露存在性),且 A 的 Key 仍在
        resp = self.client.delete(f"/api/api_keys/{key_id}", headers=self._auth(token_b))
        self.assertEqual(resp.status_code, 404, resp.text)
        keys = self.client.get("/api/api_keys", headers=self._auth(token_a))
        self.assertEqual(len(keys.json()["data"]), 1)


if __name__ == "__main__":
    unittest.main()
