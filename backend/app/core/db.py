"""数据库连接:SQLAlchemy 2.x 同步 + 异步双引擎 / SessionLocal / Base。

- 生产用 MySQL 8.0(DATABASE_URL 指向 ai_portal 库);
- 测试可用 sqlite,如 sqlite:///file:testdb?mode=memory&uri=true;
- 异步引擎供注册等 async 接口使用(sqlite→aiosqlite、mysql+pymysql/aiomysql 自动转换);
- 同步引擎保留,建表和成员2 的测试继续使用,两者共用同一库。
- 本期使用逻辑外键,不建物理外键,归属校验在应用层完成。
"""
import asyncio
from collections.abc import AsyncGenerator, Callable, Generator
from typing import TypeVar

T = TypeVar("T")
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials,HTTPBearer
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import NullPool

from .config import   get_settings
from .response  import APIError
from .security import decode_token

class Base(DeclarativeBase):
    pass


def _build_engine():
    settings = get_settings()
    kwargs: dict = {"pool_pre_ping": True, "future": True}
    url = settings.database_url
    if url.startswith("mysql+aiomysql"):
        # 同步引擎需要 pymysql 驱动
        url = url.replace("mysql+aiomysql", "mysql+pymysql", 1)
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    else:
        # MySQL:连接池与回收,避免长时间空闲后断连
        kwargs.update(pool_size=10, max_overflow=20, pool_recycle=3600)
    return create_engine(url, **kwargs)


engine = _build_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


def _async_url(url: str) -> str:
    """把连接串转成异步驱动能用的连接串。"""
    if url.startswith("sqlite"):
        return url.replace("sqlite://", "sqlite+aiosqlite://", 1)
    if url.startswith("mysql+aiomysql") or url.startswith("mysql+pymysql"):
        return url.replace("mysql+pymysql", "mysql+aiomysql", 1)
    return url


def _build_async_engine():
    settings = get_settings()
    kwargs: dict = {"pool_pre_ping": True, "future": True}
    if settings.database_url.startswith("sqlite"):
        # 测试环境用 NullPool,避免连接跨事件循环复用报错
        kwargs["poolclass"] = NullPool
    return create_async_engine(_async_url(settings.database_url), **kwargs)


async_engine = _build_async_engine()
AsyncSessionLocal = async_sessionmaker(
    async_engine, autoflush=False, expire_on_commit=False, class_=AsyncSession
)


def get_db() -> Generator[Session, None, None]:
    """FastAPI 依赖:每请求一个会话。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


async def get_async_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI 依赖:异步接口每请求一个异步会话。"""
    async with AsyncSessionLocal() as db:
        yield db


def init_db() -> None:
    """建表(注册全部模型映射)。"""
    from app.models import (  # noqa: F401 注册映射
        ai_call_log, ai_task, model, user,
        api_key, consumption_record, operation_log, recharge_order, support,
    )

    Base.metadata.create_all(bind=engine)


async def run_db(fn: Callable[..., T], /, *args, **kwargs) -> T:
    """在线程池中执行同步 DB 函数,避免阻塞事件循环。

    async def 路由/后台协程/异步生成器内的 DB 操作一律写成同步辅助函数后经本函数调用:
    `await run_db(_create_task, db, ...)`;异常(APIError 等)原样向上抛。
    def 路由与同步依赖(FastAPI 已自动放线程池)无需包裹。
    Session 非并发安全,须保证同一会话不被多个线程同时使用(顺序 await 即可)。
    """
    return await asyncio.to_thread(fn, *args, **kwargs)


# 获取解析 token → 查用户 → 校验未禁用
bearer_scheme = HTTPBearer(auto_error=False)#自动解析请求头里的 Bearer Token
async def get_current_user(
credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_async_db),
):
    # 延迟导入:models 依赖本模块的 Base,顶层导入会形成循环导入
    from ..models.user import User
    if credentials is None:
        raise APIError(401,"未登录或凭证无效")
    try:
        head = decode_token(credentials.credentials)
        user_id = int(head["sub"])
    except Exception:
        raise APIError(401, "登录凭证无效或已过期") from None

    user = await db.get(User, user_id)
    if user is None:
        raise APIError(401, "未登录或凭证失效")
    if user.status != 1:
        raise APIError(403, "账号已被禁用")
    return user





