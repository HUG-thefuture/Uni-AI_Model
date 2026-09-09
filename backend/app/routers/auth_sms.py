"""短信认证路由:发送验证码 / 验证码登录(自动注册)/ 绑定换绑手机号。

- 响应结构与 /api/auth/login 完全一致:{"token": ..., "user": User_out...};
- main.py 由集成者统一挂载到 settings.api_prefix 下。
"""
import secrets

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import get_settings
from ..core.db import get_async_db
from ..core.deps import get_current_user
from ..core.response import APIError, ok
from ..core.security import create_access_token, hash_password
from ..models.user import User, UserProfile, Wallet
from ..schemas.auth import User_out
from ..schemas.sms import SmsBind_req, SmsLogin_req, SmsSend_req
from ..services import sms as sms_service
from ..services.pricing import to_micro

router = APIRouter(
    prefix="/auth/sms",
    tags=["短信认证"],
)


async def _register_by_phone(db: AsyncSession, phone: str) -> User:
    """手机号首次登录时自动注册:随机密码(可走找回流程),赠送注册积分。"""
    settings = get_settings()
    base = f"user{phone[-6:]}"
    username = base
    # 用户名撞库时追加随机 2 位数字重试(随机密码仅用于占位,可走找回流程重置)
    for _ in range(5):
        exists = await db.scalar(select(User.id).where(User.username == username))
        if exists is None:
            break
        username = f"{base}{secrets.randbelow(90) + 10}"
    else:
        raise APIError(409, "注册失败,请稍后重试")

    random_password = secrets.token_hex(16)
    user = User(
        username=username,
        phone=phone,
        password_hash=hash_password(random_password),
        role="user",
        status=1,
        real_auth_status=0,
        school=None,
    )
    db.add(user)
    await db.flush()  # 拿到 user.id

    profile = UserProfile(user_id=user.id, nickname=f"手机用户{phone[-4:]}")
    # 注册赠金额(元;与 services/auth.py 的 register 口径一致);账本存微元
    gift = to_micro(max(0, settings.default_register_points))
    wallet = Wallet(user_id=user.id, balance=gift, total_recharged=0, total_consumed=0)
    db.add_all([profile, wallet])
    try:
        await db.commit()
    except IntegrityError:  # 并发下用户名/手机号唯一键冲突兜底
        await db.rollback()
        raise APIError(409, "注册失败,请稍后重试") from None
    await db.refresh(user)
    return user


@router.post("/send")
async def send_sms_code(body: SmsSend_req,
                        request: Request,
                        db: AsyncSession = Depends(get_async_db)):
    """发送短信验证码(purpose: login / bind)。"""
    ip = request.client.host if request.client else ""
    data = await sms_service.send_code(db, body.phone, body.purpose, ip)
    return ok(data)


@router.post("/login")
async def sms_login(body: SmsLogin_req,
                    db: AsyncSession = Depends(get_async_db)):
    """验证码登录:老用户直接签发 token,新用户自动注册后签发。"""
    await sms_service.verify_code(db, body.phone, "login", body.code)
    user = await db.scalar(select(User).where(User.phone == body.phone))
    if user is None:
        user = await _register_by_phone(db, body.phone)
    if user.status != 1:
        raise APIError(403, "账号已被禁用")
    token = create_access_token(user.id, user.role)
    return ok({"token": token, "user": User_out.model_validate(user).model_dump(mode="json")})


@router.post("/bind")
async def sms_bind(body: SmsBind_req,
                   current_user: User = Depends(get_current_user),
                   db: AsyncSession = Depends(get_async_db)):
    """绑定/换绑手机号:先校验新手机号的验证码,再落库。"""
    await sms_service.verify_code(db, body.phone, "bind", body.code)
    taken = await db.scalar(
        select(User.id).where(User.phone == body.phone, User.id != current_user.id)
    )
    if taken is not None:
        raise APIError(409, "该手机号已被其他账号绑定")
    current_user.phone = body.phone
    try:
        await db.commit()
    except IntegrityError:  # phone 唯一键并发冲突兜底
        await db.rollback()
        raise APIError(409, "该手机号已被其他账号绑定") from None
    return ok({"phone": body.phone})
