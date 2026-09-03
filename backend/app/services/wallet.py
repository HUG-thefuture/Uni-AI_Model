import secrets
from datetime import datetime
from sqlalchemy import select,update,func
from sqlalchemy.ext.asyncio import AsyncSession


from ..models.consumption_record import ConsumptionRecord
from ..models.recharge_order import RechargeOrder
from ..models.invoice import Invoice
from ..models.user import Wallet


def create_order_no()->str:
    ts=datetime.now().strftime('%Y%m%d%H%M%S')
    rand=secrets.token_hex(4).upper()
    return f"{ts}{rand}"

async def get_wallet(user_id: int,db:AsyncSession):
    stmt=await db.scalar(select(Wallet).where(Wallet.user_id == user_id))
    if not stmt:
        stmt=Wallet(user_id=user_id,balance=0,total_consumed=0,total_recharged=0)
        db.add(stmt)
        await db.commit()
        await db.refresh(stmt)
    return stmt

async def recharge_order(db:AsyncSession,user_id:int,amount:int):
    order_no=create_order_no()
    new_order=RechargeOrder(order_no=order_no,user_id=user_id,amount=amount,
                            points=amount,payment_method='mock',status='paid',created_at=datetime.now())
    stmt=await get_wallet(user_id,db)
    db.add(new_order)
    stmt.balance+=amount
    stmt.total_recharged+=amount
    await db.commit()
    await db.refresh(new_order)
    return new_order

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
            "created_at": r.created_at
        }
        for r in recharge_records
    ]
    consumption_stmt=select(ConsumptionRecord).where(ConsumptionRecord.user_id == user_id).order_by(ConsumptionRecord.created_at.desc())
    consumption_records=(await db.scalars(consumption_stmt)).all()
    consumption_list=[
        {
            "type":"consumption",
            "order_no": f"TASK-{c.task_id}",  # 借用订单号字段拼接任务ID
            "amount": -c.amount,  # 负数表示扣费
            "status": c.status,  # 'success' / 'failed'
            "created_at": c.created_at
        }
        for c in consumption_records

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

async def get_user_invoices(db: AsyncSession, user_id: int, page: int = 1, page_size: int = 10) -> dict:
    """返回当前用户的发票申请记录，金额沿用钱包的“分”口径。"""
    offset = (page - 1) * page_size
    stmt = (select(Invoice)
            .where(Invoice.user_id == user_id)
            .order_by(Invoice.created_at.desc())
            .offset(offset)
            .limit(page_size))
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
