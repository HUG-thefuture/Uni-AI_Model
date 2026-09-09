"""计价与按 token 结算内核的单元测试(pricing.freeze_amount / billing.settle_usage)。

金额口径(2026-09-07 起):账本单位微元,1 元 = 10_000 微元;
token 费用按真实 usage 以微元精确扣减,无累积器。
"""
import os
import tempfile
import unittest
from pathlib import Path

_DB_FILE = Path(tempfile.gettempdir()) / "uni_ai_model_test1_billing.db"
if _DB_FILE.exists():
    _DB_FILE.unlink()
os.environ["DATABASE_URL"] = f"sqlite:///{_DB_FILE.as_posix()}"
os.environ["SECRET_KEY"] = "test-secret-key-at-least-32-bytes-long"

from app.core.db import SessionLocal, async_engine, engine, init_db  # noqa: E402
from app.models.model import Model  # noqa: E402
from app.models.user import User, UserProfile, Wallet  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.services import billing, pricing  # noqa: E402

YUAN = billing.MICRO  # 1 元 = 10_000 微元


def _per_token_model() -> Model:
    """输入 8 / 输出 20(0.0001 元/千token):即 ¥0.0008 与 ¥0.002 每千token 成本。"""
    return Model(
        name="t", model_code="t", provider_type="online", model_type="text",
        vendor="mock", price_per_call=0, billing_mode="per_token",
        token_input_price=8, token_output_price=20,
    )


class BillingPricingTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        init_db()
        cls.user_ids: list[int] = []
        with SessionLocal() as db:
            for i in range(3):
                user = User(username=f"bill_{i}", password_hash=hash_password("Bill12345"),
                            role="user", status=1)
                db.add(user)
                db.flush()
                db.add_all([
                    UserProfile(user_id=user.id, nickname=f"bill_{i}"),
                    Wallet(user_id=user.id, balance=100 * YUAN, total_recharged=0, total_consumed=0),  # ¥100
                ])
                db.commit()
                cls.user_ids.append(user.id)

    @classmethod
    def tearDownClass(cls) -> None:
        engine.dispose()
        import asyncio
        asyncio.run(async_engine.dispose())
        if _DB_FILE.exists():
            _DB_FILE.unlink()

    def test_cost_micro_and_freeze(self) -> None:
        model = _per_token_model()
        # 售价 = 成本(8/20) × 全局默认加价 130% → 输入 (8*130+50)//100=10,输出 (20*130+50)//100=26
        self.assertEqual(pricing.sell_prices(model), (10, 26))
        # 1000 输入 + 1000 输出 = 3600 微元(按售价,即 ¥0.0036)
        self.assertEqual(pricing.cost_micro(model, 1000, 1000), 3600)
        self.assertEqual(pricing.to_yuan(3600), 0.0036)
        # 供应商成本口径不加价:仍为 2800 微元(¥0.0028)
        self.assertEqual(pricing.provider_cost_micro(model, 1000, 1000), 2800)
        # per_call 模型返回 None;单价换算 price_per_call=3 元 → 30000 微元
        per_call = Model(name="c", model_code="c", provider_type="online",
                         model_type="text", vendor="mock", price_per_call=3)
        self.assertIsNone(pricing.cost_micro(per_call, 1000, 1000))
        self.assertEqual(pricing.per_call_micro(per_call), 3_000_000)          # 成本 ¥3
        self.assertEqual(pricing.per_call_sell_micro(per_call), 3_900_000)     # 售价 ¥3.9(×130%)
        # 数量结算:图像 2 张 = 单价×2
        self.assertEqual(pricing.per_call_sell_micro(per_call, 2), 7_800_000)
        self.assertEqual(pricing.to_micro(10.5), 10_500_000)
        # 模型行加价覆盖:150% → 输入 (8*150+50)//100=12,输出 (20*150+50)//100=30
        model.token_markup_pct = 150
        self.assertEqual(pricing.sell_prices(model), (12, 30))
        model.token_markup_pct = None
        # freeze:1000 输入字符 ≈ 500 token,输出封顶 2048 → (500*10 + 2048*26)//10 = 5824 微元
        self.assertEqual(pricing.freeze_amount(model, 1000), 5824)
        # 贵价模型(输入成本价 30000 = ¥3/千token):prompt_chars=0 时输入至少 1 token → 39 微元
        expensive = Model(name="e", model_code="e", provider_type="online", model_type="text",
                          vendor="mock", billing_mode="per_token",
                          token_input_price=30000, token_output_price=0)
        self.assertEqual(pricing.freeze_amount(expensive, 0), 3900)

    def test_settle_usage_exact_and_refund(self) -> None:
        """冻结 ¥5,实际 36 微元:精确扣 36 微元,差额退回,无累积器。"""
        uid = self.user_ids[0]
        model = _per_token_model()
        with SessionLocal() as db:
            billing.freeze(db, uid, 5 * YUAN)  # 预扣 ¥5
            db.commit()
            settled = billing.settle_usage(db, uid, frozen=5 * YUAN,
                                           actual_micro=pricing.cost_micro(model, 1000, 1000))
            db.commit()
            wallet = db.query(Wallet).filter(Wallet.user_id == uid).one()
            self.assertEqual(settled, 3600)               # 实扣 ¥0.0036
            self.assertEqual(wallet.balance, 100 * YUAN - 3600)
            self.assertEqual(wallet.credit_remainder, 0)  # 累积器已废弃
            self.assertEqual(wallet.total_consumed, 3600)

    def test_settle_usage_deducts_each_call(self) -> None:
        """多次小额调用逐次精确扣减(不再等累积满 1 积分)。"""
        uid = self.user_ids[1]
        with SessionLocal() as db:
            billing.freeze(db, uid, YUAN)  # ¥1
            db.commit()
            settled1 = billing.settle_usage(db, uid, frozen=YUAN, actual_micro=6000)
            billing.freeze(db, uid, YUAN)
            db.commit()
            settled2 = billing.settle_usage(db, uid, frozen=YUAN, actual_micro=6000)
            db.commit()
            wallet = db.query(Wallet).filter(Wallet.user_id == uid).one()
            self.assertEqual((settled1, settled2), (6000, 6000))
            # ¥100 - ¥0.006×2 = ¥99.988
            self.assertEqual(wallet.balance, 100 * YUAN - 12_000)
            self.assertEqual(wallet.credit_remainder, 0)
            self.assertEqual(wallet.total_consumed, 12_000)

    def test_settle_usage_extra_charge_capped_by_balance(self) -> None:
        """实际超冻结:补扣差额;余额不足时最多扣到 0。"""
        uid = self.user_ids[2]
        with SessionLocal() as db:
            billing.freeze(db, uid, YUAN)
            db.commit()
            # 实际 ¥3(3×10⁶ 微元),冻结 ¥1 → 补扣 ¥2
            settled = billing.settle_usage(db, uid, frozen=YUAN, actual_micro=3 * YUAN)
            db.commit()
            wallet = db.query(Wallet).filter(Wallet.user_id == uid).one()
            self.assertEqual(settled, 3 * YUAN)
            self.assertEqual(wallet.balance, 100 * YUAN - 3 * YUAN)
            # 清零余额后再来一次大额:补扣封顶
            wallet.balance = 0
            db.commit()
            billing.freeze(db, uid, 0)
            settled2 = billing.settle_usage(db, uid, frozen=0, actual_micro=50 * YUAN)
            db.commit()
            db.refresh(wallet)
            self.assertEqual(settled2, 0)  # 无可扣余额,按 0 计(不产生负余额)

    def test_freeze_insufficient_balance_message(self) -> None:
        """余额不足 409,文案为「余额不足,请先充值」。"""
        uid = self.user_ids[0]
        with SessionLocal() as db:
            from app.core.response import APIError
            with self.assertRaises(APIError) as ctx:
                billing.freeze(db, uid, 999 * YUAN)
            self.assertEqual(ctx.exception.status_code, 409)
            self.assertIn("余额不足", ctx.exception.message)


if __name__ == "__main__":
    unittest.main()
