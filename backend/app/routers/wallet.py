from fastapi import APIRouter, Depends, Query
from fastapi.encoders import jsonable_encoder
from sqlalchemy.ext.asyncio import AsyncSession


from ..core.response import APIError, ok
from ..core.deps import get_current_user
from ..schemas.admin_wallet import InvoiceCreate, InvoiceResponse
from ..services import admin_wallet, wallet
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


@router.get("/invoices")
async def get_invoices(
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(get_current_user),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(10, ge=1, le=100, description="每页条数"),
):
    return ok(jsonable_encoder(await wallet.get_user_invoices(db, current_user.id, page, page_size)))


@router.post("/invoices")
async def create_invoice(
    data: InvoiceCreate,
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(get_current_user),
):
    # 校验用户是否有足够的可开票金额
    w = await wallet.get_wallet(current_user.id, db)
    if w.total_recharged - w.total_consumed < data.amount:
        raise APIError(400, "可开票余额不足")
    invoice = await admin_wallet.create_invoice(db, current_user.id, data)
    return ok(InvoiceResponse.model_validate(invoice).model_dump(mode="json"))

