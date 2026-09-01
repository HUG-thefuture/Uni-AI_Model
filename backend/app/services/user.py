from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends
from app.core.db import get_async_db
from app.core.response import APIError
from app.models import UserProfile
from app.schemas.auth import profile_update_req
from sqlalchemy import select

async def update_profile(
                   payload:profile_update_req,
                   user_id:int,
                   db:AsyncSession = Depends(get_async_db)
):
    profile = await db.scalar(select(UserProfile).where(UserProfile.user_id==user_id))
    if profile is None:
        raise APIError(404, "用户资料不存在")
    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(profile, key, value)
    await db.commit()
    await db.refresh(profile)
    return profile