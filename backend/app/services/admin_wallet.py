from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User, Wallet  # 假设User模型在其他地方定义
from ..models.consumption_record import ConsumptionRecord
from ..models.invoice import Invoice
from ..models.recharge_order import RechargeOrder
from ..schemas.admin_wallet import InvoiceCreate


# ... 原有代码 ...

# 4. 管理端：用户钱包列表（分页/搜索）
async def get_admin_wallets(db: AsyncSession, page: int, page_size: int, keyword: str = "") -> dict:
    offset = (page - 1) * page_size

    # 联表查询：查询钱包和对应的用户名
    stmt = select(Wallet, User.username).join(User, User.id == Wallet.user_id)

    if keyword:
        stmt = stmt.where(User.username.like(f"%{keyword}%"))

    stmt = stmt.order_by(Wallet.updated_at.desc()).offset(offset).limit(page_size)

    # 必须用 db.execute，因为拿回的是 (钱包对象, 用户名) 的元组
    result = await db.execute(stmt)
    rows = result.all()

    # 计算总数
    total_count = await db.scalar(select(func.count()).select_from(Wallet))

    # 转换格式，把元组拆开，方便前端直接读取
    wallet_list = [
        {
            "user_id": w.user_id,
            "username": u,
            "balance": w.balance,
            "total_recharged": w.total_recharged,
            "total_consumed": w.total_consumed,
            "created_at": w.created_at
        }
        for w, u in rows
    ]
    return {"list": wallet_list, "total": total_count, "page": page, "page_size": page_size}


# 5. 管理端：充值订单
async def get_admin_orders(db: AsyncSession, page: int, page_size: int, status: str = "") -> dict:
    offset = (page - 1) * page_size
    stmt = select(RechargeOrder)
    if status:
        stmt = stmt.where(RechargeOrder.status == status)
    stmt = stmt.order_by(RechargeOrder.created_at.desc()).offset(offset).limit(page_size)

    orders = (await db.scalars(stmt)).all()
    total_count = await db.scalar(select(func.count()).select_from(RechargeOrder))

    return {"list": orders, "total": total_count, "page": page, "page_size": page_size}


# 6. 管理端：消费记录
async def get_admin_consumption(db: AsyncSession, page: int, page_size: int, user_id: int = None) -> dict:
    offset = (page - 1) * page_size
    stmt = select(ConsumptionRecord)

    if user_id:
        stmt = stmt.where(ConsumptionRecord.user_id == user_id)

    stmt = stmt.order_by(ConsumptionRecord.created_at.desc()).offset(offset).limit(page_size)

    records = (await db.scalars(stmt)).all()
    total_count = await db.scalar(select(func.count()).select_from(ConsumptionRecord))

    return {"list": records, "total": total_count, "page": page, "page_size": page_size}


# 7. 管理端：发票（P1）
async def get_admin_invoices(db: AsyncSession, page: int, page_size: int) -> dict:
    offset = (page - 1) * page_size
    stmt = select(Invoice).order_by(Invoice.created_at.desc()).offset(offset).limit(page_size)
    invoices = (await db.scalars(stmt)).all()

    total_count = await db.scalar(select(func.count()).select_from(Invoice))

    return {"list": invoices, "total": total_count, "page": page, "page_size": page_size}


# 新增：用户申请开票
async def create_invoice(db: AsyncSession, user_id: int, data: InvoiceCreate) -> Invoice:
    invoice = Invoice(
        user_id=user_id,
        amount=data.amount,
        title=data.title,
        type=data.type,
        tax_no=data.tax_no,
        status='pending'  # 初始状态待审核
    )
    db.add(invoice)
    await db.commit()
    await db.refresh(invoice)
    return invoice

# 12. 管理端：全量调用统计
async def get_admin_usage_stats(db: AsyncSession) -> dict:
    # 1. 总调用次数
    total_calls = await db.scalar(
        select(func.count(ConsumptionRecord.id)).where(ConsumptionRecord.status == 'success')
    )

    # 2. 总消费金额
    total_cost = await db.scalar(
        select(func.sum(ConsumptionRecord.amount)).where(ConsumptionRecord.status == 'success')
    )

    # 3. 总用户数（跨表查一下 users 的数量）
    total_users = await db.scalar(select(func.count()).select_from(User))

    return {
        "total_calls": total_calls or 0,
        "total_users": total_users or 0,
        "total_cost": total_cost or 0
    }