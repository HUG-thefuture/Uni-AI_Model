"""数据库连接:SQLAlchemy 2.x engine / SessionLocal / Base。

- 生产用 MySQL 8.0(DATABASE_URL 指向 ai_portal 库);
- 测试可用 sqlite,如 sqlite:///file:testdb?mode=memory&uri=true;
- 本期使用逻辑外键,不建物理外键,归属校验在应用层完成;
- 性能固化(WP09):MySQL 池参数 pool_size=20 / max_overflow=10 / pool_recycle=1800,
  慢查询日志阈值 settings.slow_query_ms(默认 500ms,超过记 warning)。
"""
import asyncio
import logging
import time
from collections.abc import Callable, Generator
from typing import TypeVar

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings

logger = logging.getLogger("app.db")

T = TypeVar("T")


class Base(DeclarativeBase):
    pass


def _build_engine():
    settings = get_settings()
    kwargs: dict = {"pool_pre_ping": True, "future": True}
    if settings.database_url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    else:
        # MySQL:连接池与回收(WP09 固化:池 20+10,空闲连接 30 分钟回收,避免长时间空闲后断连)
        kwargs.update(pool_size=20, max_overflow=10, pool_recycle=1800)
    return create_engine(settings.database_url, **kwargs)


engine = _build_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


def _register_slow_query_listener(target_engine) -> None:
    """慢查询日志(WP09):before/after_cursor_execute 记录单条 SQL 耗时,
    超过 settings.slow_query_ms(默认 500ms)记 warning(阈值每次调用时读取,便于热调)。"""

    @event.listens_for(target_engine, "before_cursor_execute")
    def _before_cursor(conn, cursor, statement, parameters, context, executemany):
        conn.info.setdefault("_query_start_times", []).append(time.perf_counter())

    @event.listens_for(target_engine, "after_cursor_execute")
    def _after_cursor(conn, cursor, statement, parameters, context, executemany):
        starts = conn.info.get("_query_start_times")
        if not starts:
            return
        elapsed_ms = (time.perf_counter() - starts.pop()) * 1000
        threshold = get_settings().slow_query_ms
        if elapsed_ms >= threshold:
            logger.warning(
                "慢查询 %.0fms(阈值 %sms): %s",
                elapsed_ms, threshold, (statement or "")[:200],
            )


_register_slow_query_listener(engine)


def get_db() -> Generator[Session, None, None]:
    """FastAPI 依赖:每请求一个会话。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


async def run_db(fn: Callable[..., T], /, *args, **kwargs) -> T:
    """在线程池中执行同步 DB 函数,避免阻塞事件循环。

    async def 路由/后台协程/异步生成器内的 DB 操作一律写成同步辅助函数后经本函数调用:
    `await run_db(_create_task, db, ...)`;异常(APIError 等)原样向上抛。
    def 路由与同步依赖(FastAPI 已自动放线程池)无需包裹。
    Session 非并发安全,须保证同一会话不被多个线程同时使用(顺序 await 即可)。
    """
    return await asyncio.to_thread(fn, *args, **kwargs)


def init_db() -> None:
    """建表:成员2 全部表 + 支撑表桩(users/wallets 等成员1/4 表以 sql/ 下 DDL 为准)。"""
    from app.models import (  # noqa: F401 注册映射
        ai_call_log, ai_task, model, support,
    )

    Base.metadata.create_all(bind=engine)
