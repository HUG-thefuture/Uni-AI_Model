from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.db import get_async_db
from app.core.response import ok
from app.models.user import get_current_user,User
from app.schemas.auth import profile_update_req, Profile_res
from app.services import user as user_service

router = APIRouter(prefix="/user", tags=["用户"])


@router.get("/profile")
async def get_profile(
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_async_db),
):
    profile = await user_service.get_profile(db, current_user.id)
    data = Profile_res.model_validate(profile).model_dump(mode="json")
    data["school"] = current_user.school
    return ok(data)

@router.put("/profile")
    # 更新个人资料
async def profile(
        payload:profile_update_req,
        current_user: User = Depends(get_current_user),
        db:AsyncSession = Depends(get_async_db)
):
    profile = await user_service.update_profile(db, current_user.id, payload)
    data = Profile_res.model_validate(profile).model_dump(mode="json")
    data["school"] = current_user.school
    return ok(data)

