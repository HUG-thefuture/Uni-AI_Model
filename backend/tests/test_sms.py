"""短信认证接口(send/login/bind)的端到端回归测试。

与 test_user_api.py 相同模式:模块顶部先设 os.environ 再 import app,
env 优先于 .env,SMS_DEBUG=true 使未配置阿里云时响应回显 debug_code。
"""
import asyncio
import os
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

_DB_FILE = Path(tempfile.gettempdir()) / "uni_ai_model_test1_sms.db"
if _DB_FILE.exists():
    _DB_FILE.unlink()
os.environ["DATABASE_URL"] = f"sqlite:///{_DB_FILE.as_posix()}"
os.environ["SECRET_KEY"] = "test-secret-key-at-least-32-bytes-long"
os.environ["SMS_DEBUG"] = "true"

from app.core.config import get_settings  # noqa: E402

# get_settings 为 lru_cache 单例:若其它测试模块先于本模块导入(其 env 无 SMS_DEBUG),
# 清空缓存让本模块顶部设置的环境变量重新生效,保证任意测试顺序均可运行。
get_settings.cache_clear()

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import inspect, select  # noqa: E402

import app.models.sms_code  # noqa: E402,F401,SMS-1 注册 SmsCode 到 Base.metadata(建表前置)
from app.core.config import get_settings  # noqa: E402
from app.core.db import SessionLocal, async_engine, engine, init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models.sms_code import SmsCode  # noqa: E402
from app.models.user import User, UserProfile, Wallet  # noqa: E402
from app.routers import auth_sms  # noqa: E402

# main.py 由集成者统一接线;测试进程内若尚未挂载则自行挂载(避免重复路由)
if not any(getattr(route, "path", "") == "/api/auth/sms/send" for route in app.routes):
    app.include_router(auth_sms.router, prefix=get_settings().api_prefix)


def _backdate_sms(phone: str, seconds: int = 61) -> None:
    """把某手机号的历史验证码记录前移,绕过 60 秒冷却(测试专用)。"""
    with SessionLocal() as db:
        records = db.execute(select(SmsCode).where(SmsCode.phone == phone)).scalars().all()
        for record in records:
            record.created_at = record.created_at - timedelta(seconds=seconds)
        db.commit()


class SmsAuthTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        init_db()
        assert "sms_codes" in set(inspect(engine).get_table_names())
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.client.close()
        engine.dispose()
        asyncio.run(async_engine.dispose())
        if _DB_FILE.exists():
            _DB_FILE.unlink()

    def _send(self, phone: str, purpose: str = "login") -> dict:
        response = self.client.post(
            "/api/auth/sms/send", json={"phone": phone, "purpose": purpose}
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["data"]

    @staticmethod
    def _auth(token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}"}

    def _password_token(self, username: str, password: str) -> str:
        response = self.client.post(
            "/api/auth/login", json={"username": username, "password": password}
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["data"]["token"]

    def test_01_send_returns_debug_code(self) -> None:
        """①未配置阿里云 + SMS_DEBUG:发送成功且响应回显 6 位 debug_code。"""
        phone = "13900000001"
        data = self._send(phone)
        self.assertIs(data["sent"], False)          # console 通道
        self.assertEqual(data["channel"], "console")
        self.assertEqual(data["cooldown"], 60)
        debug_code = data.get("debug_code")
        self.assertRegex(debug_code, r"^\d{6}$")
        with SessionLocal() as db:
            record = db.scalar(select(SmsCode).where(SmsCode.phone == phone).order_by(SmsCode.id.desc()))
            self.assertIsNotNone(record)
            self.assertEqual(record.purpose, "login")
            self.assertNotIn(debug_code, record.code_hash)  # 库里只存哈希
            self.assertIsNone(record.used_at)

    def test_02_send_cooldown_429(self) -> None:
        """②60 秒内同手机号二次发送 → 429。"""
        phone = "13900000002"
        self._send(phone)
        again = self.client.post(
            "/api/auth/sms/send", json={"phone": phone, "purpose": "login"}
        )
        self.assertEqual(again.status_code, 429, again.text)
        self.assertEqual(again.json()["message"], "发送过于频繁,请稍后再试")

    def test_03_send_bad_phone_400(self) -> None:
        """③手机号格式不正确 → 400。"""
        for phone in ("12345", "23800000003", "1390000000"):
            response = self.client.post(
                "/api/auth/sms/send", json={"phone": phone, "purpose": "login"}
            )
            self.assertEqual(response.status_code, 400, response.text)

    def test_04_sms_login_auto_register(self) -> None:
        """④发送 → 登录 → 自动注册:users.phone 可查、钱包有赠送积分;再次登录复用同一账号。"""
        phone = "13900000004"
        code = self._send(phone)["debug_code"]
        login = self.client.post("/api/auth/sms/login", json={"phone": phone, "code": code})
        self.assertEqual(login.status_code, 200, login.text)
        data = login.json()["data"]
        self.assertIn("token", data)
        self.assertEqual(data["user"]["phone"], phone)
        self.assertTrue(data["user"]["username"].startswith("user"))
        self.assertEqual(data["user"]["status"], 1)

        with SessionLocal() as db:
            user = db.scalar(select(User).where(User.phone == phone))
            self.assertIsNotNone(user)
            profile = db.scalar(select(UserProfile).where(UserProfile.user_id == user.id))
            self.assertIsNotNone(profile)
            self.assertEqual(profile.nickname, f"手机用户{phone[-4:]}")
            wallet = db.get(Wallet, user.id)
            self.assertIsNotNone(wallet)
            self.assertEqual(wallet.balance, get_settings().default_register_points * 1_000_000)  # 赠送金额按微元入账(1元=10⁶)
            user_id = user.id

        # 老用户第二次登录(冷却已过,重新发码):不再重复注册,同一账号
        _backdate_sms(phone)
        code2 = self._send(phone)["debug_code"]
        again = self.client.post("/api/auth/sms/login", json={"phone": phone, "code": code2})
        self.assertEqual(again.status_code, 200, again.text)
        self.assertEqual(again.json()["data"]["user"]["id"], user_id)
        self.assertIn("token", again.json()["data"])

    def test_05_sms_login_wrong_code_and_limits(self) -> None:
        """⑤验证码错误 → 401;错误 5 次后失效;过期验证码 → 401。"""
        phone = "13900000005"
        code = self._send(phone)["debug_code"]
        wrong = "000000" if code != "000000" else "000001"
        for _ in range(5):
            bad = self.client.post("/api/auth/sms/login", json={"phone": phone, "code": wrong})
            self.assertEqual(bad.status_code, 401, bad.text)
            self.assertEqual(bad.json()["message"], "验证码错误")
        # 错满 5 次后,即使填对真码也已失效
        dead = self.client.post("/api/auth/sms/login", json={"phone": phone, "code": code})
        self.assertEqual(dead.status_code, 401, dead.text)
        self.assertEqual(dead.json()["message"], "验证码错误次数过多,已失效,请重新获取")

        # 过期:直接把 expires_at 拨到过去
        phone2 = "13900000006"
        code2 = self._send(phone2)["debug_code"]
        with SessionLocal() as db:
            record = db.scalar(select(SmsCode).where(SmsCode.phone == phone2).order_by(SmsCode.id.desc()))
            record.expires_at = datetime.now() - timedelta(seconds=1)
            db.commit()
        expired = self.client.post("/api/auth/sms/login", json={"phone": phone2, "code": code2})
        self.assertEqual(expired.status_code, 401, expired.text)
        self.assertEqual(expired.json()["message"], "验证码已过期,请重新获取")

    def test_06_bind_flow(self) -> None:
        """⑥登录用户绑定手机号成功;同号被其他用户绑定 → 409;换绑走同一接口。"""
        phone = "13900000007"
        # 未登录 → 401
        anon = self.client.post("/api/auth/sms/bind", json={"phone": phone, "code": "123456"})
        self.assertEqual(anon.status_code, 401, anon.text)

        self.client.post(
            "/api/auth/register",
            json={"username": "bind_user_a", "password": "Bind12345", "nickname": "绑定甲"},
        )
        token_a = self._password_token("bind_user_a", "Bind12345")

        # 甲绑定成功
        code = self._send(phone, purpose="bind")["debug_code"]
        bound = self.client.post(
            "/api/auth/sms/bind", headers=self._auth(token_a),
            json={"phone": phone, "code": code},
        )
        self.assertEqual(bound.status_code, 200, bound.text)
        self.assertEqual(bound.json()["data"], {"phone": phone})
        with SessionLocal() as db:
            user_a = db.scalar(select(User).where(User.username == "bind_user_a"))
            self.assertEqual(user_a.phone, phone)
            user_a_id = user_a.id

        # 乙注册并绑定同一手机号 → 409
        self.client.post(
            "/api/auth/register",
            json={"username": "bind_user_b", "password": "Bind12345", "nickname": "绑定乙"},
        )
        token_b = self._password_token("bind_user_b", "Bind12345")
        _backdate_sms(phone)
        code2 = self._send(phone, purpose="bind")["debug_code"]
        conflict = self.client.post(
            "/api/auth/sms/bind", headers=self._auth(token_b),
            json={"phone": phone, "code": code2},
        )
        self.assertEqual(conflict.status_code, 409, conflict.text)
        self.assertEqual(conflict.json()["message"], "该手机号已被其他账号绑定")

        # 甲换绑新号:同一接口,先验证新号验证码
        new_phone = "13900000008"
        code3 = self._send(new_phone, purpose="bind")["debug_code"]
        rebinding = self.client.post(
            "/api/auth/sms/bind", headers=self._auth(token_a),
            json={"phone": new_phone, "code": code3},
        )
        self.assertEqual(rebinding.status_code, 200, rebinding.text)
        with SessionLocal() as db:
            user_a = db.get(User, user_a_id)
            self.assertEqual(user_a.phone, new_phone)


if __name__ == "__main__":
    unittest.main()
