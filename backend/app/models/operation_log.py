from sqlalchemy import BigInteger, Integer, DateTime, func, String, Index
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime
from ..core.db import Base
from .base import pk_column

from sqlalchemy import JSON  # 必须引入 JSON 类型


class OperationLog(Base):
    __tablename__ = "operation_logs"
    __table_args__ = (
        # 映射 SQL 中的 KEY idx_oplog_user_created (user_id, created_at)
        Index('idx_oplog_user_created', 'user_id', 'created_at'),
        # 映射 SQL 中的 KEY idx_oplog_created_at (created_at)
        Index('idx_oplog_created_at', 'created_at'),
        # 映射 SQL 中的 KEY idx_oplog_resource (resource_type, resource_id)
        Index('idx_oplog_resource', 'resource_type', 'resource_id'),
        {'mysql_engine': 'InnoDB', 'mysql_charset': 'utf8mb4'}
    )
    id: Mapped[int] = pk_column()
    user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, comment="逻辑外键 users.id，可为空（系统操作）")
    action: Mapped[str] = mapped_column(String(50), nullable=False, comment="动作名称")
    resource_type: Mapped[str] = mapped_column(String(50), nullable=False, comment="资源类型")
    resource_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, comment="资源主键")
    ip: Mapped[str | None] = mapped_column(String(45), nullable=True, comment="客户端 IP")
    detail_json: Mapped[dict | None] = mapped_column(JSON, nullable=True, comment="详情 JSON")

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())