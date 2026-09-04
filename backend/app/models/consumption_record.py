from sqlalchemy import BigInteger, Integer, DateTime, func, String, Index
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime
from ..core.db import Base
from .base import pk_column


class ConsumptionRecord(Base):
    __tablename__ = "consumption_records"
    __table_args__ = (
        # 映射 SQL 中的 KEY idx_consume_user_created (user_id, created_at)
        Index('idx_consume_user_created', 'user_id', 'created_at'),
        # 映射 SQL 中的 KEY idx_consume_task_id (task_id)
        Index('idx_consume_task_id', 'task_id'),
        # 映射 SQL 中的 KEY idx_consume_model_id (model_id)
        Index('idx_consume_model_id', 'model_id'),
        # 映射 SQL 中的 KEY idx_consume_status_created (status, created_at)
        Index('idx_consume_status_created', 'status', 'created_at'),
        {'mysql_engine': 'InnoDB', 'mysql_charset': 'utf8mb4'}
    )

    id: Mapped[int] = pk_column()
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="逻辑外键 users.id")
    task_id: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="逻辑外键 ai_tasks.id")
    model_id: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="逻辑外键 models.id")

    amount: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, server_default="0", comment="消费金额(分)")
    balance_before: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, server_default="0", comment="扣费前余额")
    balance_after: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, server_default="0", comment="扣费后余额")

    status: Mapped[str] = mapped_column(String(20), nullable=False, default='success', server_default='success',
                                        comment="success / failed / refunded")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
