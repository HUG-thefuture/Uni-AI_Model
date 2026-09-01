"""扣费事务(成员4 wallets 服务的兼容实现,字段口径:docs/数据字典.md)。

铁律:预扣冻结 → 调用 → 成功结算 → 失败释放,失败绝不扣费。
实现说明:数据字典 wallets 表无「冻结余额」列,故冻结=行锁校验余额后立即扣减,
失败时等额退回(余额永不为负);结算只累计 total_consumed 并写流水。
成员4 就绪后可整包替换本模块,接口签名保持不变。
"""
import logging

from sqlalchemy.orm import Session

from ..core.response import APIError
from ..models.support import ConsumptionRecord, Wallet

logger = logging.getLogger("app.billing")


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
    """预扣冻结:余额不足抛 409「积分不足,请先充值」;成功则立即扣减并落冻结记录。"""
    assert amount >= 0, "扣费金额必须为非负整数"
    if amount == 0:
        return
    wallet = _lock_wallet(db, user_id)
    if wallet.balance < amount:
        raise APIError(409, "积分不足,请先充值")
    wallet.balance -= amount


def settle(db: Session, user_id: int, amount: int, task_id: int | None = None,
           model_id: int | None = None) -> None:
    """结算:调用成功,扣减转消费累计并写流水(consumption_records 最小桩)。"""
    if amount == 0:
        return
    wallet = _lock_wallet(db, user_id)
    wallet.total_consumed += amount
    db.add(ConsumptionRecord(user_id=user_id, task_id=task_id, model_id=model_id, amount=amount))


def refund(db: Session, user_id: int, amount: int, task_id: int | None = None) -> None:
    """失败释放:冻结/扣减等额退回(红线:失败绝不扣费)。"""
    if amount == 0:
        return
    wallet = _lock_wallet(db, user_id)
    wallet.balance += amount
