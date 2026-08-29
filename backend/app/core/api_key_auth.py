"""开放平台 API Key 鉴权(WP06)。

- generate_api_key():生成 (明文, key_prefix, sha256hex),供成员4 的 Key 管理接口复用;
  明文仅在创建响应中出现一次,库内只存 sha256 哈希与前缀;
- require_api_key:FastAPI 依赖,每请求直查 DB(无缓存),禁用/过期立即生效。
"""
import hashlib
import secrets
from datetime import datetime

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.response import APIError
from app.models.support import ApiKey, User

_bearer = HTTPBearer(auto_error=False)


def generate_api_key() -> tuple[str, str, str]:
    """生成新 Key:返回 (明文 "sk-<32位hex>", key_prefix(前12字符), sha256hex)。"""
    plain = f"sk-{secrets.token_hex(16)}"
    return plain, plain[:12], hashlib.sha256(plain.encode()).hexdigest()


def hash_api_key(plain: str) -> str:
    """明文 → sha256hex(与 generate_api_key 口径一致)。"""
    return hashlib.sha256(plain.encode()).hexdigest()


def require_api_key(
    request: Request,
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    """校验 Authorization: Bearer sk-xxx,返回 Key 所属 User。

    - 缺失/格式不对 → 401「缺少API Key」;
    - 哈希查不到 / status != enabled / 已过期 → 401「API Key 无效或已禁用」;
    - 每请求直查 DB 无缓存,禁用立即生效;
    - 通过后 use_count += 1 并 commit,key_id/user_id 挂 request.state。
    """
    if creds is None or not creds.credentials:
        raise APIError(401, "缺少API Key")
    plain = creds.credentials
    if not plain.startswith("sk-"):
        raise APIError(401, "缺少API Key")

    key = (
        db.query(ApiKey)
        .filter(ApiKey.key_hash == hash_api_key(plain))
        .one_or_none()
    )
    if key is None or key.status != "enabled":
        raise APIError(401, "API Key 无效或已禁用")
    if key.expires_at is not None:
        expires = key.expires_at
        if expires.tzinfo is not None:
            expires = expires.astimezone(tz=None).replace(tzinfo=None)
        if expires < datetime.now():
            raise APIError(401, "API Key 无效或已禁用")

    user = db.get(User, key.user_id)
    if user is None or user.status != 1:
        raise APIError(401, "API Key 无效或已禁用")

    request.state.api_key_id = key.id
    request.state.api_user_id = key.user_id
    key.use_count = (key.use_count or 0) + 1
    db.commit()
    return user
