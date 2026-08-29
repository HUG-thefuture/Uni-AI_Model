"""公共字段与列助手:created_at/updated_at 统一,主键 MySQL 用 BIGINT、SQLite 兼容自增。"""
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, func
from sqlalchemy.orm import Mapped, mapped_column


def pk_column() -> Mapped[int]:
    """自增主键:MySQL 为 BIGINT UNSIGNED 语义,SQLite 退化为 INTEGER 以支持自增。"""
    return mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True
    )


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), comment="创建时间"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
        comment="更新时间(自动更新)",
    )
