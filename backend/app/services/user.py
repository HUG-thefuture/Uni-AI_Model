"""用户资料与管理端用户服务。"""
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.response import APIError
from ..models.user import User, UserProfile
from ..schemas.user import ProfileUpdateRequest


async def update_profile(
    db: AsyncSession, user_id: int, payload: ProfileUpdateRequest
) -> UserProfile:
    profile = await db.scalar(select(UserProfile).where(UserProfile.user_id == user_id))
    if profile is None:
        profile = UserProfile(user_id=user_id)
        db.add(profile)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(profile, key, value)
    await db.commit()
    await db.refresh(profile)
    return profile


async def list_users(
    db: AsyncSession,
    *,
    page: int,
    page_size: int,
    keyword: str | None,
    role: str | None,
    status: int | None,
) -> dict:
    filters = []
    if keyword:
        like = f"%{keyword}%"
        filters.append(or_(User.username.like(like), User.school.like(like)))
    if role:
        filters.append(User.role == role)
    if status is not None:
        filters.append(User.status == status)

    total = await db.scalar(select(func.count()).select_from(User).where(*filters))
    users = (
        await db.scalars(
            select(User)
            .where(*filters)
            .order_by(User.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    return {"total": total or 0, "page": page, "page_size": page_size, "items": list(users)}


async def update_user_status(
    db: AsyncSession, *, user_id: int, status: int, admin_id: int
) -> User:
    if user_id == admin_id:
        raise APIError(403, "禁止管理员禁用或启用自己")
    user = await db.get(User, user_id)
    if user is None:
        raise APIError(404, "用户不存在")
    user.status = status
    await db.commit()
    await db.refresh(user)
    return user
