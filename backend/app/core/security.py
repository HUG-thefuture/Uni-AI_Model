"""JWT 签发与校验(全组冻结:Bearer Token,24h 过期)。

注:用户注册/登录路由属成员1;本模块只提供 token 工具,成员1 可直接复用或替换实现。
"""
import datetime as dt

import jwt

from app.core.config import get_settings

_ALGO = "HS256"


def create_access_token(user_id: int, role: str) -> str:
    s = get_settings()
    now = dt.datetime.now(dt.UTC)
    payload = {
        "sub": str(user_id),
        "role": role,
        "iat": now,
        "exp": now + dt.timedelta(hours=s.jwt_expire_hours),
    }
    return jwt.encode(payload, s.secret_key, algorithm=_ALGO)


def decode_token(token: str) -> dict:
    """校验并返回 payload;无效/过期抛 jwt.PyJWTError(由 deps 转成 401)。"""
    return jwt.decode(token, get_settings().secret_key, algorithms=[_ALGO])
