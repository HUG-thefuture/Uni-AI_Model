"""数据库连接:SQLAlchemy 2.x engine / SessionLocal / Base。

- 生产用 MySQL 8.0(DATABASE_URL 指向 ai_portal 库);
- 测试可用 sqlite,如 sqlite:///file:testdb?mode=memory&uri=true;
- 本期使用逻辑外键,不建物理外键,归属校验在应用层完成。
"""
from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings


class Base(DeclarativeBase):
    pass


def _build_engine():
    settings = get_settings()
    kwargs: dict = {"pool_pre_ping": True, "future": True}
    if settings.database_url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    else:
        # MySQL:连接池与回收,避免长时间空闲后断连
        kwargs.update(pool_size=10, max_overflow=20, pool_recycle=3600)
    return create_engine(settings.database_url, **kwargs)


engine = _build_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


def get_db() -> Generator[Session, None, None]:
    """FastAPI 依赖:每请求一个会话。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """建表(成员2 负责的三张表;成员1/4 的表由其建表 SQL 管理)。"""
    from app.models import ai_call_log, ai_task, model  # noqa: F401 注册映射

    Base.metadata.create_all(bind=engine)
