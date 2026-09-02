from typing import Optional

from fastapi import APIRouter, Depends,Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.db import get_async_db
from core.deps import require_admin
from core.response import APIError
from models.invoice import Invoice

from services import admin_wallet

router = APIRouter(
    prefix="/admin",
    tags=["管理员"],
)

@router.get("/wallets")
async def get_admin_wallets(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    keyword: str = Query("", description="搜索用户名"),
    db: AsyncSession = Depends(get_async_db),
    admin = Depends(require_admin)  # 必须管理员
):
    return await admin_wallet.get_admin_wallets(db, page, page_size, keyword)

@router.get("/orders")
async def get_admin_orders(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    status: str = Query("", description="订单状态"),
    db: AsyncSession = Depends(get_async_db),
    admin = Depends(require_admin)
):
    return await admin_wallet.get_admin_orders(db, page, page_size, status)


@router.get("/consumption-records")
async def get_admin_consumption(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    user_id: Optional[int] = Query(None, description="按用户ID筛选"),
    db: AsyncSession = Depends(get_async_db),
    admin = Depends(require_admin)
):
    return await admin_wallet.get_admin_consumption(db, page, page_size, user_id)

@router.get("/invoices")

async def get_admin_invoices(
        page: int = Query(1, ge=1),
        page_size: int = Query(10, ge=1, le=100),
        db: AsyncSession = Depends(get_async_db),
        admin=Depends(require_admin)
):
    return await admin_wallet.get_admin_invoices(db, page, page_size)




# ==========================================
# 补充接口 2：管理后台审核发票（简单状态修改）
# ==========================================
@router.put("/admin/invoices/{invoice_id}/status")
async def update_invoice_status(
        invoice_id: int,
        data: dict,  # {"status": "issued"}
        db: AsyncSession = Depends(get_async_db),
        admin=Depends(require_admin)
):
    invoice = await db.scalar(select(Invoice).where(Invoice.id == invoice_id))
    if not invoice:
        raise APIError(404,"发票不存在")

    invoice.status = data.get("status", invoice.status)
    await db.commit()
    return {"message": "审核状态已更新", "status": invoice.status}





@router.get("/stats/usage")
async def get_admin_usage_stats(
    db: AsyncSession = Depends(get_async_db),
    admin = Depends(require_admin)
):
    return await admin_wallet.get_admin_usage_stats(db)