from sqlalchemy.ext.asyncio import AsyncSession
from app.core.response import APIError
from app.models import User, UserProfile
from app.schemas.auth import profile_update_req
from sqlalchemy import select, func, or_


async def get_profile(db: AsyncSession, user_id: int):
    """获取用户资料；用户主表由鉴权依赖校验，资料缺失时返回空资料。"""
    profile = await db.scalar(select(UserProfile).where(UserProfile.user_id == user_id))
    if profile is None:
        raise APIError(404, "用户资料不存在")
    return profile


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


async def list_users(
    db: AsyncSession,
    page: int,
    page_size: int,
    keyword: str | None = None,
    role: str | None = None,
    status: int | None = None,
) -> tuple[int, list[User]]:
    """管理员用户列表:分页 + 关键字/角色/状态筛选。"""
    conds = []
    if keyword:
        like = f"%{keyword}%"
        conds.append(or_(User.username.like(like), User.school.like(like)))
    if role:
        conds.append(User.role == role)
    if status is not None:
        conds.append(User.status == status)
    total = await db.scalar(select(func.count(User.id)).where(*conds)) or 0
    users = await db.scalars(
        select(User)
        .where(*conds)
        .order_by(User.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return total, list(users)


async def update_user_status(db: AsyncSession, target_id: int, status: int, operator: User) -> User:
    """启用/禁用用户;禁止操作自己。"""
    user = await db.get(User, target_id)
    if user is None:
        raise APIError(404, "用户不存在")
    if user.id == operator.id:
        raise APIError(400, "不能操作自己的账号")
    user.status = status
    await db.commit()
    await db.refresh(user)
    return user
