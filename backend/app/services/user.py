from sqlalchemy.ext.asyncio import AsyncSession
from app.core.response import APIError
from app.models import User, UserProfile
from app.schemas.auth import profile_update_req
from sqlalchemy import select

async def update_profile(
        db: AsyncSession,
        user_id: int,
        payload: profile_update_req,
):
    profile = await db.scalar(select(UserProfile).where(UserProfile.user_id == user_id))
    user = await db.get(User, user_id)
    if profile is None or user is None:
        raise APIError(404, "用户资料不存在")
    data = payload.model_dump(exclude_unset=True)
    school_provided = "school" in data
    school = data.pop("school", None)
    if school_provided:
        user.school = school
    for key, value in data.items():
        setattr(profile, key, value)
    await db.commit()
    await db.refresh(profile)
    return profile