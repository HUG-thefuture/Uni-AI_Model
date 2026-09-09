"""扣费事务(成员4 wallets 服务,字段口径:docs/数据字典.md)。

铁律:预扣冻结 → 调用 → 成功结算 → 失败释放,失败绝不扣费。
实现说明:数据字典 wallets 表无「冻结余额」列,故冻结=行锁校验余额后立即扣减,
失败时等额退回(余额永不为负);结算累计 total_consumed 并写流水
(consumption_records 含 balance_before/after 台账;退款写 status='refunded' 流水)。

金额口径(2026-09-07 起按「元」记账):账本内部单位为「微元」,
1 元 = MICRO(1_000_000) 微元,最小精度 0.000001 元。

按 token 计费(per_token 模型)使用 settle_usage():
- 实际费用以微元参与运算,按真实 usage 精确扣减,不再需要小额累积器;
- 冻结(预扣估算)与实际费用的差额多退少不补,余额不足时最多扣到 0。
"""
import logging

from sqlalchemy.orm import Session

from ..core.response import APIError
from ..models.support import ConsumptionRecord, Wallet

logger = logging.getLogger("app.billing")

# 微元换算:1 元 = 1_000_000 微元(token 单价 0.0001 元/千token 口径见 models.token_*_price)
MICRO = 1_000_000


def _lock_wallet(db: Session, user_id: int) -> Wallet:
    wallet = (
        db.query(Wallet)
        .filter(Wallet.user_id == user_id)
        .with_for_update()
        .one_or_none()
    )
    if wallet is None:
        # 注册事务应初始化钱包;缺失时兜底创建(余额 0)
        wallet = Wallet(user_id=user_id)
        db.add(wallet)
        db.flush()
    return wallet


def ensure_wallet(db: Session, user_id: int) -> Wallet:
    return _lock_wallet(db, user_id)


def freeze(db: Session, user_id: int, amount: int, task_id: int | None = None) -> None:
    """预扣冻结(微元):余额不足抛 409「余额不足,请先充值」;成功则立即扣减。"""
    assert amount >= 0, "扣费金额必须为非负整数"
    if amount == 0:
        return
    wallet = _lock_wallet(db, user_id)
    if wallet.balance < amount:
        raise APIError(409, "余额不足,请先充值")
    wallet.balance -= amount
    wallet.version = (wallet.version or 0) + 1


def settle(db: Session, user_id: int, amount: int, task_id: int | None = None,
           model_id: int | None = None) -> None:
    """按次结算(微元):调用成功,扣减转消费累计并写台账流水(balance_before/after)。

    注意:冻结时已扣减余额,本函数不再动余额,只累计消费并落流水。
    """
    if amount == 0:
        return
    wallet = _lock_wallet(db, user_id)
    balance_before = wallet.balance
    wallet.total_consumed += amount
    wallet.version = (wallet.version or 0) + 1
    db.add(ConsumptionRecord(
        user_id=user_id, task_id=task_id or 0, model_id=model_id or 0,
        amount=amount, balance_before=balance_before, balance_after=balance_before,
        status="success",
    ))


def refund(db: Session, user_id: int, amount: int, task_id: int | None = None,
           model_id: int | None = None) -> None:
    """失败释放(微元):冻结/扣减等额退回(红线:失败绝不扣费),并写退款台账流水。"""
    if amount == 0:
        return
    wallet = _lock_wallet(db, user_id)
    balance_before = wallet.balance
    wallet.balance += amount
    wallet.version = (wallet.version or 0) + 1
    db.add(ConsumptionRecord(
        user_id=user_id, task_id=task_id or 0, model_id=model_id or 0,
        amount=amount, balance_before=balance_before, balance_after=wallet.balance,
        status="refunded",
    ))


def settle_usage(db: Session, user_id: int, *, frozen: int, actual_micro: int,
                 task_id: int | None = None, model_id: int | None = None) -> int:
    """按 token 计费的实际结算:按真实用量(微元)精确扣减,多退少不补。

    - actual_micro:实际费用(微元,0.0001 元),已含加价;
    - 应扣 ≤ 冻结额:差额立即退回余额,按应扣计入消费;
    - 应扣 > 冻结额:补扣差额,余额不足时最多扣到 0(费用按实扣计);
    - 返回最终计入消费的金额(微元),并由调用方写入任务 cost。
    """
    due = max(0, int(actual_micro))
    wallet = _lock_wallet(db, user_id)
    balance_before = wallet.balance
    if due <= frozen:
        # 差额退回
        if frozen - due:
            wallet.balance += frozen - due
        settled = due
    else:
        # 补扣差额,余额不足时最多扣到 0(费用按实扣计)
        extra = min(due - frozen, balance_before)
        wallet.balance -= extra
        settled = frozen + extra

    wallet.total_consumed += settled
    wallet.version = (wallet.version or 0) + 1
    if settled > 0:
        db.add(ConsumptionRecord(
            user_id=user_id, task_id=task_id or 0, model_id=model_id or 0,
            amount=settled, balance_before=balance_before, balance_after=wallet.balance,
            status="success",
        ))
    return settled
