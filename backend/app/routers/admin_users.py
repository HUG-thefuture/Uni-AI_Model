"""管理端用户列表与启用/禁用接口。"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.db import get_async_db
from ..core.deps import require_admin
from ..core.response import APIError, ok
from ..models.user import User
from ..schemas.user import AdminUserItem, UserStatusUpdateRequest
from ..services import user as user_service

router = APIRouter(prefix="/admin/users", tags=["管理端用户"])


@router.get("")
async def list_users(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    keyword: str | None = Query(default=None, max_length=100),
    role: str | None = Query(default=None),
    status: int | None = Query(default=None, ge=0, le=1),
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_async_db),
):
    if role is not None and role not in {"user", "admin"}:
        raise APIError(400, "role 非法，仅支持 user/admin")
    result = await user_service.list_users(
        db, page=page, page_size=page_size, keyword=keyword, role=role, status=status
    )
    result["items"] = [
        AdminUserItem.model_validate(item).model_dump(mode="json") for item in result["items"]
    ]
    return ok(result)


@router.put("/{user_id}/status")
async def update_user_status(
    user_id: int,
    payload: UserStatusUpdateRequest,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_async_db),
):
    user = await user_service.update_user_status(
        db, user_id=user_id, status=payload.status, admin_id=admin.id
    )
    return ok({
        "id": user.id,
        "status": user.status,
        "updated_at": user.updated_at.isoformat() if user.updated_at else None,
    })
