import secrets
from datetime import datetime
from sqlalchemy import select,update,func
from sqlalchemy.ext.asyncio import AsyncSession

from models.recharge_order import RechargeOrder
from models.wallet import Wallet
from schemas.wallet import RechargeRequest

def create_order_no()->str:
    ts=datetime.now().strftime('%Y%m%d%H%M%S')
    rand=secrets.token_hex(4).upper()
    return f"{ts}+{rand}"

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
    stmt.balance+=amount
    stmt.total_recharged+=amount
    await db.commit()
    await db.refresh(stmt)
    return stmt

async def get_user_records(db:AsyncSession,user_id:int):
