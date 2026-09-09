"""FastAPI 依赖:get_current_user(JWT)/ require_admin。

与成员1 约定:JWT payload 含 sub(user_id)、role;每次请求校验用户存在且 status=1,
禁用立即失效。成员1 的用户模块就绪后可直接复用本依赖。
"""
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

import jwt as pyjwt

from ..models import User
from .db import get_async_db
from .response import APIError
from .security import decode_token
from .token_blacklist import is_revoked

_bearer = HTTPBearer(auto_error=False)


def _credentials_error() -> APIError:
    return APIError(401, "未登录或凭证失效")


async def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: AsyncSession = Depends(get_async_db),
) -> User:
    if creds is None or not creds.credentials:
        raise _credentials_error()
    try:
        payload = decode_token(creds.credentials)
        user_id = int(payload["sub"])
    except (pyjwt.PyJWTError, KeyError, TypeError, ValueError):
        raise _credentials_error()
    if is_revoked(creds.credentials):  # 登出拉黑的 token 立即失效
        raise _credentials_error()
    user = await db.get(User, user_id)
    if user is None or user.status != 1:  # 禁用立即失效
        raise _credentials_error()
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise APIError(403, "无权限,需要管理员身份")
    return user


async def get_optional_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: AsyncSession = Depends(get_async_db),
) -> User | None:
    """可选登录:匿名返回 None(公开接口预留)。"""
    if creds is None or not creds.credentials:
        return None
    try:
        payload = decode_token(creds.credentials)
        user = await db.get(User, int(payload["sub"]))
        return user if user and user.status == 1 else None
    except (pyjwt.PyJWTError, KeyError, TypeError, ValueError):
        return None
