from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from ..services import wallet
from ..core.db import get_async_db, get_current_user
from ..schemas.wallet import RechargeRequest

router = APIRouter(
    prefix="/api/wallet",
    tags=["钱包"],
)

@router.get("/me")
async def my_wallet(db:AsyncSession=Depends(get_async_db),current_user=Depends(get_current_user)):
    stmt=await wallet.get_wallet(current_user.id,db)
    return stmt


@router.post("/recharge")
async def recharge(recharge_data:RechargeRequest,db:AsyncSession=Depends(get_async_db),current_user=Depends(get_current_user)):
    if recharge_data.amount <= 0:
        raise HTTPException(status_code=400, detail="充值金额必须大于0")
    try:
        stmt=await wallet.recharge_order(db,current_user.id,recharge_data.amount)
        return stmt
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"充值失败: {str(e)}")


@router.get("/records")
async def get_records(db:AsyncSession=Depends(get_async_db),current_user=Depends(get_current_user)):
    return