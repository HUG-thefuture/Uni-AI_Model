"""FastAPI 依赖:get_current_user(JWT)/ require_admin。

与成员1 约定:JWT payload 含 sub(user_id)、role;每次请求校验用户存在且 status=1,
禁用立即失效。成员1 的用户模块就绪后可直接复用本依赖。
"""
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session
from app.models.user import get_current_user
import jwt as pyjwt

from app.core.db import get_db
from app.core.response import APIError
from app.core.security import decode_token
from app.models.support import User

_bearer = HTTPBearer(auto_error=False)


def _credentials_error() -> APIError:
    return APIError(401, "未登录或凭证失效")


# def get_current_user(
#     creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
#     db: Session = Depends(get_db),
# ) -> User:
#     if creds is None or not creds.credentials:
#         raise _credentials_error()
#     try:
#         payload = decode_token(creds.credentials)
#     except pyjwt.PyJWTError:
#         raise _credentials_error()
#     user_id = payload.get("sub")
#     if not user_id:
#         raise _credentials_error()
#     user = db.get(User, int(user_id))
#     if user is None or user.status != 1:  # 禁用立即失效
#         raise _credentials_error()
#     return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise APIError(403, "无权限,需要管理员身份")
    return user


def get_optional_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User | None:
    """可选登录:匿名返回 None(公开接口预留)。"""
    if creds is None or not creds.credentials:
        return None
    try:
        payload = decode_token(creds.credentials)
        user = db.get(User, int(payload["sub"]))
        return user if user and user.status == 1 else None
    except (pyjwt.PyJWTError, KeyError, ValueError):
        return None
