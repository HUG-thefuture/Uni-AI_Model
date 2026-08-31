from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.schemas.auth import Register_req
from app.models.user import User, UserProfile, Wallet
from app.core.response import APIError
from app.core.security import hash_password


async def register(db: AsyncSession, payload: Register_req) -> User:
    exists = await db.scalar(select(User.id).where(User.username == payload.username))
    if exists is not None:
        raise APIError(409, "用户名已存在")

    user = User(
        username=payload.username,
        password_hash=hash_password(payload.password),
        role="user",
        status=1,
        real_auth_status=0,
        school=payload.school,
    )
    db.add(user)
    await db.flush()  # 拿到 user.id

    profile = UserProfile(user_id=user.id, nickname=payload.nickname or payload.username)
    wallet = Wallet(user_id=user.id, balance=0, total_recharged=0, total_consumed=0)
    db.add_all([profile, wallet])
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        raise APIError(500, "注册失败,请稍后重试") from None
    await db.refresh(user)
    return user








