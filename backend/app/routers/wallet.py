from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession


from core.response import APIError
from models.user import get_current_user
from services import wallet
from core.db import get_db
from schemas.wallet import RechargeRequest, WalletRecordsResponse, WalletResponse, RechargeResponse

router = APIRouter(
    prefix="/api/wallet",
    tags=["钱包"],
)

@router.get("/me", response_model=WalletResponse)
async def my_wallet(db:AsyncSession=Depends(get_db),current_user=Depends(get_current_user)):
    stmt=await wallet.get_wallet(current_user.id,db)
    return stmt


@router.post("/recharge", response_model=RechargeResponse)
async def recharge(recharge_data:RechargeRequest,db:AsyncSession=Depends(get_db),current_user=Depends(get_current_user)):
    if recharge_data.amount <= 0:
        raise APIError(400, "充值金额必须大于0")
    try:
        stmt=await wallet.recharge_order(db,current_user.id,recharge_data.amount)
        return stmt
    except Exception as e:
        raise APIError(500, f"充值失败: {str(e)}")


@router.get("/records", response_model=WalletRecordsResponse)
async def get_records(db:AsyncSession=Depends(get_db),current_user=Depends(get_current_user),page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(10, ge=1, le=100, description="每页条数")):
    stmt=await wallet.get_user_records(db,current_user.id,page,page_size)
    return stmt

