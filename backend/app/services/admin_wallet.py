from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import get_settings
from ..models.ai_task import AiTask
from ..models.model import Model
from ..models.user import User, Wallet
from ..models.consumption_record import ConsumptionRecord
from ..models.invoice import Invoice
from ..models.recharge_order import RechargeOrder
from ..services.pricing import to_yuan
from ..schemas.admin_wallet import InvoiceCreate


def _dt(value):
    return value.isoformat() if value is not None and hasattr(value, "isoformat") else value


# 管理端:用户钱包列表(分页/搜索)
async def get_admin_wallets(db: AsyncSession, page: int, page_size: int, keyword: str = "") -> dict:
    offset = (page - 1) * page_size

    stmt = select(Wallet, User.username).join(User, User.id == Wallet.user_id)
    if keyword:
        stmt = stmt.where(User.username.like(f"%{keyword}%"))
    stmt = stmt.order_by(Wallet.updated_at.desc()).offset(offset).limit(page_size)
    result = await db.execute(stmt)
    rows = result.all()

    total_count = await db.scalar(select(func.count()).select_from(Wallet))

    wallet_list = [
        {
            "user_id": w.user_id,
            "username": u,
            "balance": to_yuan(w.balance),
            "total_recharged": to_yuan(w.total_recharged),
            "total_consumed": to_yuan(w.total_consumed),
            "created_at": _dt(w.created_at),
        }
        for w, u in rows
    ]
    return {"list": wallet_list, "total": total_count, "page": page, "page_size": page_size}


# 管理端:充值订单
async def get_admin_orders(db: AsyncSession, page: int, page_size: int, status: str = "") -> dict:
    offset = (page - 1) * page_size
    stmt = select(RechargeOrder)
    if status:
        stmt = stmt.where(RechargeOrder.status == status)
    stmt = stmt.order_by(RechargeOrder.created_at.desc()).offset(offset).limit(page_size)

    orders = (await db.scalars(stmt)).all()
    total_count = await db.scalar(select(func.count()).select_from(RechargeOrder))

    order_list = [
        {
            "id": order.id,
            "order_no": order.order_no,
            "user_id": order.user_id,
            "amount": order.amount,
            "payment_method": order.payment_method,
            "status": order.status,
            "external_trade_no": order.external_trade_no,
            "paid_at": _dt(order.paid_at),
            "created_at": _dt(order.created_at),
            "updated_at": _dt(order.updated_at),
        }
        for order in orders
    ]
    return {"list": order_list, "total": total_count, "page": page, "page_size": page_size}


# 管理端:消费记录
async def get_admin_consumption(db: AsyncSession, page: int, page_size: int, user_id: int = None) -> dict:
    offset = (page - 1) * page_size
    stmt = select(ConsumptionRecord)
    if user_id:
        stmt = stmt.where(ConsumptionRecord.user_id == user_id)
    stmt = stmt.order_by(ConsumptionRecord.created_at.desc()).offset(offset).limit(page_size)

    records = (await db.scalars(stmt)).all()
    total_count = await db.scalar(select(func.count()).select_from(ConsumptionRecord))

    record_list = [
        {
            "id": record.id,
            "user_id": record.user_id,
            "model_id": record.model_id,
            "amount": to_yuan(record.amount),
            "status": record.status,
            "created_at": _dt(record.created_at),
        }
        for record in records
    ]
    return {"list": record_list, "total": total_count, "page": page, "page_size": page_size}


# 管理端:发票
async def get_admin_invoices(db: AsyncSession, page: int, page_size: int) -> dict:
    offset = (page - 1) * page_size
    stmt = select(Invoice).order_by(Invoice.created_at.desc()).offset(offset).limit(page_size)
    invoices = (await db.scalars(stmt)).all()

    total_count = await db.scalar(select(func.count()).select_from(Invoice))

    invoice_list = [
        {
            "id": invoice.id,
            "user_id": invoice.user_id,
            "amount": invoice.amount,
            "title": invoice.title,
            "type": invoice.type,
            "status": invoice.status,
            "tax_no": invoice.tax_no,
            "created_at": _dt(invoice.created_at),
            "updated_at": _dt(invoice.updated_at),
        }
        for invoice in invoices
    ]
    return {"list": invoice_list, "total": total_count, "page": page, "page_size": page_size}


# 用户申请开票
async def create_invoice(db: AsyncSession, user_id: int, data: InvoiceCreate) -> Invoice:
    invoice = Invoice(
        user_id=user_id,
        amount=data.amount,
        title=data.title,
        type=data.type,
        tax_no=data.tax_no,
        status="pending",
    )
    db.add(invoice)
    await db.commit()
    await db.refresh(invoice)
    return invoice


# 管理端:全量调用统计 + token 收入/成本/毛利报表
async def get_admin_usage_stats(db: AsyncSession) -> dict:
    total_users = await db.scalar(select(func.count()).select_from(User))

    # 全站成功任务口径(与个人统计一致,从 ai_tasks 聚合)
    conditions = (AiTask.status == "succeeded",)
    total_calls = await db.scalar(select(func.count(AiTask.id)).where(*conditions))
    total_cost = await db.scalar(select(func.coalesce(func.sum(AiTask.cost), 0)).where(*conditions))
    total_tokens = await db.scalar(
        select(func.coalesce(
            func.sum(
                func.coalesce(AiTask.prompt_tokens, 0)
                + func.coalesce(AiTask.completion_tokens, 0)
            ), 0)
        ).where(*conditions)
    )

    # 盈利报表(仅按 token 计费模型:成本价可得):
    # revenue = 实际结算积分;provider_cost_raw = Σ(tokens × 成本单价)(单位 0.0001积分/千token)
    row = (
        await db.execute(
            select(
                func.coalesce(func.sum(AiTask.cost), 0),
                func.coalesce(
                    func.sum(
                        func.coalesce(AiTask.prompt_tokens, 0) * Model.token_input_price
                        + func.coalesce(AiTask.completion_tokens, 0) * Model.token_output_price
                    ), 0
                ),
            )
            .join(Model, Model.id == AiTask.model_id)
            .where(*conditions, Model.billing_mode == "per_token")
        )
    ).one()
    revenue = to_yuan(row[0])
    # raw = Σ(tokens × 成本单价),单价 0.0001 元/千token → 元:÷1000(千token)÷10000(微元) = ÷10^7
    provider_cost = round(int(row[1] or 0) / 10_000_000, 4)
    profit = round(revenue - provider_cost, 4)

    return {
        "total_call": total_calls or 0,
        "total_tokens": total_tokens or 0,
        "total_cost": to_yuan(total_cost),
        "total_users": total_users or 0,
        "token_revenue": revenue,
        "token_provider_cost": provider_cost,
        "token_profit": profit,
        "token_markup_pct": get_settings().token_markup_pct,
    }
