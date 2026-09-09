import secrets
from datetime import datetime
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession


from ..core.response import APIError
from ..models.ai_task import AiTask
from ..models.consumption_record import ConsumptionRecord
from ..models.invoice import Invoice
from ..models.model import Model
from ..models.recharge_order import RechargeOrder
from ..models.user import Wallet
from . import payment
from .pricing import MICRO, to_micro, to_yuan
from .pricing import MICRO, to_micro, to_yuan


def create_order_no()->str:
    ts=datetime.now().strftime('%Y%m%d%H%M%S')
    rand=secrets.token_hex(4).upper()
    return f"{ts}{rand}"

async def get_wallet(user_id: int,db:AsyncSession):
    wallet = await db.scalar(select(Wallet).where(Wallet.user_id == user_id))
    if wallet is None:
        wallet = Wallet(user_id=user_id,balance=0,total_consumed=0,total_recharged=0)
        db.add(wallet)
        try:
            await db.commit()
        except Exception:
            await db.rollback()
            raise
        await db.refresh(wallet)
    return wallet

async def create_pending_order(
    db: AsyncSession, user_id: int, amount: int, payment_method: str = "alipay"
):
    """充值下单:创建 pending 订单并返回支付信息(不再即时入账)。

    - amount 为充值金额(元),1-100000;
    - 支付宝已配置 → pay_mode=alipay,返回沙箱收银台跳转 URL;
    - 未配置 → pay_mode=sandbox(内置模拟收银台页 /pay.html)。
    """
    if not (1 <= amount <= 100000):
        raise APIError(400, "充值金额必须在 1-100000 元之间")
    method = "alipay" if payment_method == "alipay" and payment.is_alipay_enabled() else "mock"
    order = RechargeOrder(
        order_no=create_order_no(), user_id=user_id, amount=amount,
        points=amount, payment_method=method, status="pending", created_at=datetime.now(),
    )
    try:
        db.add(order)
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    await db.refresh(order)

    pay_url = None
    if method == "alipay":
        pay_url = payment.build_pay_url(order)
    pay_info = {
        "pay_mode": "alipay" if method == "alipay" else "sandbox",
        "pay_url": pay_url or f"/pay.html?order_no={order.order_no}",
    }
    return order, pay_info

async def settle_order_payment(
    db: AsyncSession, order_no: str, external_trade_no: str, payment_method: str
):
    """支付成功入账(幂等):订单 pending → paid,行锁钱包按「元 → 微元」入账。

    幂等语义:订单已是 paid 直接返回(不重复加钱);failed/cancelled 拒绝 409。
    """
    order = await db.scalar(
        select(RechargeOrder).where(RechargeOrder.order_no == order_no).with_for_update()
    )
    if order is None:
        raise APIError(404, "订单不存在")
    if order.status == "paid":
        return order  # 幂等:已入账
    if order.status != "pending":
        raise APIError(409, "订单状态不允许支付")
    wallet = await db.scalar(
        select(Wallet).where(Wallet.user_id == order.user_id).with_for_update()
    )
    if wallet is None:
        wallet = Wallet(user_id=order.user_id, balance=0, total_recharged=0, total_consumed=0)
        db.add(wallet)
        await db.flush()
    credited = to_micro(order.amount)
    wallet.balance += credited
    wallet.total_recharged += credited
    wallet.version = (wallet.version or 0) + 1
    order.status = "paid"
    order.paid_at = datetime.now()
    order.external_trade_no = external_trade_no
    order.payment_method = payment_method
    await db.commit()
    await db.refresh(order)
    return order

async def get_order(db: AsyncSession, user_id: int, order_no: str) -> RechargeOrder:
    """查本人的支付订单:不存在或非本人一律 404(不泄露他人订单)。"""
    order = await db.scalar(select(RechargeOrder).where(RechargeOrder.order_no == order_no))
    if order is None or order.user_id != user_id:
        raise APIError(404, "订单不存在")
    return order

async def get_user_records(db:AsyncSession,user_id:int,page:int=1,page_size:int=10)->dict:
    offset=(page-1)*page_size
    stmt=select(RechargeOrder).where(RechargeOrder.user_id == user_id).order_by(RechargeOrder.created_at.desc())
    recharge_records=(await db.scalars(stmt)).all()
    recharge_list=[
        {
            "type":"recharge",
            "order_no": r.order_no,
            "amount": r.amount,               # 正数
            "status": r.status,               # 'paid'
            "model_name": None,
            "prompt_tokens": None,
            "completion_tokens": None,
            "created_at": r.created_at
        }
        for r in recharge_records
    ]
    # 消费流水联 ai_tasks/models 带出模型名与 token 明细(历史任务列为空则回退 0/None)
    consumption_stmt=(
        select(ConsumptionRecord, AiTask.prompt_tokens, AiTask.completion_tokens, Model.name)
        .outerjoin(AiTask, AiTask.id == ConsumptionRecord.task_id)
        .outerjoin(Model, Model.id == ConsumptionRecord.model_id)
        .where(ConsumptionRecord.user_id == user_id)
        .order_by(ConsumptionRecord.created_at.desc())
    )
    consumption_rows=(await db.execute(consumption_stmt)).all()
    consumption_list=[
        {
            "type":"consumption",
            "order_no": f"TASK-{c.task_id}",  # 借用订单号字段拼接任务ID
            # 消费为负数(支出);refunded 为退款(收入),展示为正数;账本微元 → 元
            "amount": to_yuan(c.amount) if c.status == "refunded" else to_yuan(-c.amount),
            "status": c.status,  # 'success' / 'refunded'
            "model_name": model_name,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "created_at": c.created_at
        }
        for c, prompt_tokens, completion_tokens, model_name in consumption_rows

    ]
    all_records=recharge_list+consumption_list
    all_records.sort(key=lambda x:x["created_at"] ,reverse=True)
    total=len(all_records)
    paginated_list=all_records[offset:offset+page_size]
    return {
        "list":paginated_list,
        "total":total,
        "page":page,
        "page_size":page_size,
    }


async def export_records_csv(db: AsyncSession, user_id: int) -> str:
    """导出当前用户全部充值/消费流水 CSV(含 BOM,Excel 直接打开不乱码);消费行带 token 明细。"""
    stmt = select(RechargeOrder).where(RechargeOrder.user_id == user_id).order_by(RechargeOrder.created_at.desc())
    recharge_records = (await db.scalars(stmt)).all()
    consumption_rows = (
        await db.execute(
            select(ConsumptionRecord, AiTask.prompt_tokens, AiTask.completion_tokens, Model.name)
            .outerjoin(AiTask, AiTask.id == ConsumptionRecord.task_id)
            .outerjoin(Model, Model.id == ConsumptionRecord.model_id)
            .where(ConsumptionRecord.user_id == user_id)
            .order_by(ConsumptionRecord.created_at.desc())
        )
    ).all()

    rows: list[tuple[str, str, str, int, int, int, str]] = []
    for r in recharge_records:
        rows.append((
            r.created_at.strftime("%Y-%m-%d %H:%M:%S") if r.created_at else "",
            "充值", r.order_no, r.amount, 0, 0,
            "已支付" if r.status == "paid" else r.status,
        ))
    for c, prompt_tokens, completion_tokens, model_name in consumption_rows:
        is_refund = c.status == "refunded"
        rows.append((
            c.created_at.strftime("%Y-%m-%d %H:%M:%S") if c.created_at else "",
            "退款" if is_refund else "消费",
            f"{model_name or ''} (TASK-{c.task_id})",
            to_yuan(c.amount) if is_refund else to_yuan(-c.amount),
            prompt_tokens or 0,
            completion_tokens or 0,
            "成功" if c.status == "success" else ("已退款" if is_refund else c.status),
        ))
    rows.sort(key=lambda x: x[0], reverse=True)

    lines = ["\ufeff时间,类型,模型/订单,变动金额(元),输入token,输出token,状态"]
    for time_s, type_s, no, amount, in_t, out_t, status in rows:
        # 防公式注入:前缀单引号处理以 =+-@ 开头的单元格
        safe = [f"'{v}" if isinstance(v, str) and v and v[0] in "=+-@" else v for v in (time_s, type_s, no, amount, in_t, out_t, status)]
        lines.append(",".join(str(v) for v in safe))
    return "\n".join(lines)


async def get_user_invoices(db: AsyncSession, user_id: int, page: int = 1, page_size: int = 10) -> dict:
    """返回当前用户的发票申请记录(amount 为元)。"""
    offset = (page - 1) * page_size
    stmt = (
        select(Invoice)
        .where(Invoice.user_id == user_id)
        .order_by(Invoice.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    invoices = (await db.scalars(stmt)).all()
    total = await db.scalar(select(func.count()).select_from(Invoice).where(Invoice.user_id == user_id))
    return {
        "list": [
            {
                "id": invoice.id,
                "amount": invoice.amount,
                "title": invoice.title,
                "type": invoice.type,
                "status": invoice.status,
                "tax_no": invoice.tax_no,
                "created_at": invoice.created_at,
                "updated_at": invoice.updated_at,
            }
            for invoice in invoices
        ],
        "total": total or 0,
        "page": page,
        "page_size": page_size,
    }
