"""当前用户资料接口。"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.db import get_async_db
from ..core.deps import get_current_user
from ..core.response import ok
from ..models.user import User
from ..schemas.auth import Profile_res
from ..schemas.user import ProfileUpdateRequest
from ..services import user as user_service

router = APIRouter(prefix="/user", tags=["用户管理模块"])


@router.put("/profile")
async def update_profile(
    payload: ProfileUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    profile = await user_service.update_profile(db, current_user.id, payload)
    return ok(Profile_res.model_validate(profile).model_dump(mode="json"))
