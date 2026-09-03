from fastapi import APIRouter, Depends, Query
from fastapi.encoders import jsonable_encoder
from sqlalchemy.ext.asyncio import AsyncSession


from ..core.response import APIError, ok
from ..core.deps import get_current_user
from ..services import wallet
from ..core.db import get_async_db
from ..schemas.wallet import RechargeRequest, WalletRecordsResponse, WalletResponse, RechargeResponse

router = APIRouter(
    prefix="/api/wallet",
    tags=["钱包"],
)

@router.get("/me")
async def my_wallet(db: AsyncSession = Depends(get_async_db), current_user=Depends(get_current_user)):
    stmt=await wallet.get_wallet(current_user.id,db)
    return ok(WalletResponse.model_validate(stmt).model_dump(mode="json"))


@router.post("/recharge")
async def recharge(recharge_data: RechargeRequest, db: AsyncSession = Depends(get_async_db), current_user=Depends(get_current_user)):
    if recharge_data.amount <= 0:
        raise APIError(400, "充值金额必须大于0")
    try:
        stmt=await wallet.recharge_order(
            db, current_user.id, recharge_data.amount, recharge_data.payment_method
        )
        return ok(RechargeResponse.model_validate(stmt).model_dump(mode="json"))
    except APIError:
        raise
    except Exception:
        raise APIError(500, "充值失败，请稍后重试") from None


@router.get("/records")
async def get_records(db: AsyncSession = Depends(get_async_db), current_user=Depends(get_current_user), page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(10, ge=1, le=100, description="每页条数")):
    stmt=await wallet.get_user_records(db,current_user.id,page,page_size)
    return ok(jsonable_encoder(stmt))

