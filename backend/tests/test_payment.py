"""支付订单状态机与内置模拟收银台的回归测试(未配置支付宝 → 沙箱模式)。"""
import asyncio
import os
import tempfile
import unittest
from pathlib import Path

_DB_FILE = Path(tempfile.gettempdir()) / "uni_ai_model_test1_payment.db"
if _DB_FILE.exists():
    _DB_FILE.unlink()
os.environ["DATABASE_URL"] = f"sqlite:///{_DB_FILE.as_posix()}"
os.environ["SECRET_KEY"] = "test-secret-key-at-least-32-bytes-long"

from fastapi.testclient import TestClient  # noqa: E402

from app.core.db import SessionLocal, async_engine, engine, init_db  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.main import app  # noqa: E402
from app.models.user import User, UserProfile, Wallet  # noqa: E402
from app.services import payment  # noqa: E402


class PaymentTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        init_db()
        with SessionLocal() as db:
            for name, pwd in (("payer_test", "Payer1234"), ("other_test", "Other1234")):
                user = User(
                    username=name, password_hash=hash_password(pwd),
                    role="user", status=1, real_auth_status=0,
                )
                db.add(user)
                db.flush()
                db.add_all([
                    UserProfile(user_id=user.id, nickname=name),
                    Wallet(user_id=user.id, balance=0, total_recharged=0, total_consumed=0),
                ])
            db.commit()
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

    def test_recharge_mock_cashier_flow(self) -> None:
        """下单 → 内置收银台确认支付 → 幂等 → 余额到账(完整闭环)。"""
        token = self._login("payer_test", "Payer1234")

        order = self.client.post(
            "/api/wallet/recharge",
            headers=self._auth(token),
            json={"amount": 50, "payment_method": "mock"},
        )
        self.assertEqual(order.status_code, 200, order.text)
        data = order.json()["data"]
        self.assertEqual(data["status"], "pending")
        self.assertEqual(data["pay_mode"], "sandbox")
        self.assertIn("pay.html", data["pay_url"])
        order_no = data["order_no"]

        # 未支付前余额不变(注册赠分为 0:手工建用户)
        wallet = self.client.get("/api/wallet/me", headers=self._auth(token))
        self.assertEqual(wallet.json()["data"]["balance"], 0)

        # 确认支付(内置沙箱)
        paid = self.client.post(
            f"/api/wallet/orders/{order_no}/mock-pay", headers=self._auth(token)
        )
        self.assertEqual(paid.status_code, 200, paid.text)
        self.assertEqual(paid.json()["data"]["status"], "paid")

        status = self.client.get(f"/api/wallet/orders/{order_no}", headers=self._auth(token))
        self.assertEqual(status.json()["data"]["status"], "paid")

        wallet = self.client.get("/api/wallet/me", headers=self._auth(token))
        self.assertEqual(wallet.json()["data"]["balance"], 50)

        # 幂等:重复确认支付,余额不变
        again = self.client.post(
            f"/api/wallet/orders/{order_no}/mock-pay", headers=self._auth(token)
        )
        self.assertEqual(again.status_code, 200, again.text)
        wallet = self.client.get("/api/wallet/me", headers=self._auth(token))
        self.assertEqual(wallet.json()["data"]["balance"], 50)

        # 流水有一条充值记录
        records = self.client.get("/api/wallet/records", headers=self._auth(token))
        types = [r["type"] for r in records.json()["data"]["list"]]
        self.assertIn("recharge", types)

    def test_recharge_amount_validation(self) -> None:
        """金额非法(0 / 超上限)一律 400。"""
        token = self._login("payer_test", "Payer1234")
        for amount in (0, -5, 200000):
            resp = self.client.post(
                "/api/wallet/recharge", headers=self._auth(token), json={"amount": amount}
            )
            self.assertEqual(resp.status_code, 400, resp.text)

    def test_other_users_order_forbidden(self) -> None:
        """他人订单确认支付/查询一律 404(不泄露存在性)。"""
        token = self._login("other_test", "Other1234")
        resp = self.client.post(
            "/api/wallet/orders/NOT-EXIST-ORDER/mock-pay", headers=self._auth(token)
        )
        self.assertEqual(resp.status_code, 404, resp.text)
        resp = self.client.get("/api/wallet/orders/NOT-EXIST-ORDER", headers=self._auth(token))
        self.assertEqual(resp.status_code, 404, resp.text)

    def test_sign_and_verify_roundtrip(self) -> None:
        """RSA2 签名/验签往返:注入临时 RSA 密钥对,同参数签名可复现、验签通过、篡改失败。"""
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import rsa

        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        priv_pem = key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ).decode()
        pub_pem = key.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode()

        settings = payment.get_settings()
        object.__setattr__(settings, "alipay_app_id", "2026000000000000")
        object.__setattr__(settings, "alipay_private_key", priv_pem)
        object.__setattr__(settings, "alipay_public_key", pub_pem)

        self.assertTrue(payment.is_alipay_enabled())
        params = {"app_id": "2026000000000000", "method": "alipay.trade.page.pay",
                  "biz_content": '{"out_trade_no":"T1"}'}
        sign1 = payment.sign_params(params)
        sign2 = payment.sign_params(params)
        self.assertEqual(sign1, sign2)  # 同参数签名确定

        signed = dict(params, sign=sign1, sign_type="RSA2")
        self.assertTrue(payment.verify_signature(signed))
        tampered = dict(signed, biz_content='{"out_trade_no":"T2"}')
        self.assertFalse(payment.verify_signature(tampered))

        # 还原缓存 settings,避免污染同进程其它用例(恢复为未配置支付宝状态)
        object.__setattr__(settings, "alipay_app_id", "")
        object.__setattr__(settings, "alipay_private_key", "")
        object.__setattr__(settings, "alipay_public_key", "")
        self.assertFalse(payment.is_alipay_enabled())


if __name__ == "__main__":
    unittest.main()
