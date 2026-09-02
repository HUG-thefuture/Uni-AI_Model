from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_async_db
from app.core.deps import require_admin
from app.core.response import ok
from app.models.user import User
from app.schemas.user import PageResult, StatusUpdateIn, UserAdminOut
from app.services import user as user_service

router = APIRouter(prefix="/admin/users",
                   tags=["管理端-用户"])


@router.get("")
async def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    keyword: str | None = Query(None, max_length=50),
    role: str | None = Query(None, pattern="^(user|admin)$"),
    status: int | None = Query(None, ge=0, le=1),
    current: User = Depends(require_admin),
    db: AsyncSession = Depends(get_async_db),
):
    """用户列表:普通用户访问返回 403。"""
    total, users = await user_service.list_users(db, page, page_size, keyword, role, status)
    items = [UserAdminOut.model_validate(u).model_dump(mode="json") for u in users]
    data = PageResult(total=total, page=page, page_size=page_size, items=items)
    return ok(data.model_dump(mode="json"))


@router.put("/{user_id}/status")
async def update_status(
    user_id: int,
    payload: StatusUpdateIn,
    current: User = Depends(require_admin),
    db: AsyncSession = Depends(get_async_db),
):
    """启用/禁用用户:禁用后登录态立即失效(鉴权时校验 status)。"""
    user = await user_service.update_user_status(db, user_id, payload.status, current)
    return ok({"id": user.id, "status": user.status, "updated_at": str(user.updated_at)})
