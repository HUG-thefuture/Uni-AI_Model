from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.db import get_async_db
from ..core.deps import require_admin
from ..core.response import ok
from ..models.user import User
from ..schemas.user import (
    AdminBalanceIn,
    AdminResetPasswordIn,
    AdminUserUpdateIn,
    PageResult,
    StatusUpdateIn,
)
from ..services import user as user_service
from ..services.pricing import to_yuan

router = APIRouter(prefix="/admin/users", tags=["管理端-用户"])


@router.get("")
async def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    keyword: str | None = Query(None, max_length=50),
    role: str | None = Query(None, pattern="^(user|admin)$"),
    status: int | None = Query(None, ge=-1, le=1),
    balance_min: float | None = Query(None, description="余额下限(元)"),
    balance_max: float | None = Query(None, description="余额上限(元)"),
    include_deleted: int = Query(0, ge=0, le=1, description="1 时包含软删除用户"),
    current: User = Depends(require_admin),
    db: AsyncSession = Depends(get_async_db),
):
    """用户列表:分页 + 关键字/角色/状态/余额区间筛选,默认排除软删除。"""
    result = await user_service.list_users(
        db, page=page, page_size=page_size, keyword=keyword, role=role, status=status,
        balance_min=balance_min, balance_max=balance_max, include_deleted=bool(include_deleted),
    )
    return ok(PageResult(total=result["total"], page=result["page"],
                         page_size=result["page_size"], items=result["items"]).model_dump(mode="json"))


@router.get("/{user_id}")
async def get_user_detail(
    user_id: int,
    current: User = Depends(require_admin),
    db: AsyncSession = Depends(get_async_db),
):
    """用户详情:主表 + 资料 + 钱包余额。"""
    return ok(await user_service.get_user_detail(db, user_id))


@router.put("/{user_id}")
async def update_user(
    user_id: int,
    payload: AdminUserUpdateIn,
    current: User = Depends(require_admin),
    db: AsyncSession = Depends(get_async_db),
):
    """编辑用户:角色/实名状态/学校/昵称/手机/邮箱。"""
    user = await user_service.update_user(db, user_id, payload, current)
    return ok({"id": user.id, "username": user.username, "role": user.role,
               "real_auth_status": user.real_auth_status, "school": user.school})


@router.put("/{user_id}/status")
async def update_status(
    user_id: int,
    payload: StatusUpdateIn,
    current: User = Depends(require_admin),
    db: AsyncSession = Depends(get_async_db),
):
    """启用/禁用用户:禁用后登录态立即失效。"""
    user = await user_service.update_user_status(db, user_id=user_id, status=payload.status, admin_id=current.id)
    return ok({"id": user.id, "status": user.status, "updated_at": str(user.updated_at)})


@router.put("/{user_id}/balance")
async def adjust_balance(
    user_id: int,
    payload: AdminBalanceIn,
    current: User = Depends(require_admin),
    db: AsyncSession = Depends(get_async_db),
):
    """余额调整:amount 正数充值/补发,负数扣减/回收(元为单位)。"""
    wallet = await user_service.adjust_balance(db, user_id, payload.amount, payload.reason, current)
    return ok({"user_id": wallet.user_id, "balance": to_yuan(wallet.balance)})


@router.put("/{user_id}/password")
async def reset_password(
    user_id: int,
    payload: AdminResetPasswordIn,
    current: User = Depends(require_admin),
    db: AsyncSession = Depends(get_async_db),
):
    """重置用户密码。"""
    user = await user_service.reset_password(db, user_id, payload.password, current)
    return ok({"id": user.id, "username": user.username, "reset": True})


@router.delete("/{user_id}")
async def delete_user(
    user_id: int,
    current: User = Depends(require_admin),
    db: AsyncSession = Depends(get_async_db),
):
    """软删除用户:status 置 -1,登录态立即失效,历史数据保留可追溯。"""
    user = await user_service.soft_delete_user(db, user_id, current)
    return ok({"id": user.id, "username": user.username, "status": user.status, "deleted": True})
