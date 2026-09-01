from sqlalchemy import BigInteger, Integer, DateTime, func, String, Index
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime
from core.db import Base

class ApiKey(Base):
    __tablename__ = "api_keys"
    __table_args__ = (
        # 映射 SQL 中的 KEY idx_user_created (user_id, created_at)
        Index('idx_user_created', 'user_id', 'created_at'),
        # 映射 SQL 中的 KEY idx_status (status)
        Index('idx_status', 'status'),
        # 映射 SQL 中的 KEY idx_expires_at (expires_at)
        Index('idx_expires_at', 'expires_at'),
        {'mysql_engine': 'InnoDB', 'mysql_charset': 'utf8mb4'}
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True, comment="逻辑外键 users.id")
    name: Mapped[str] = mapped_column(String(100), nullable=False, comment="Key 名称")
    key_prefix: Mapped[str] = mapped_column(String(20), nullable=False, comment="Key 前缀")
    key_hash: Mapped[str] = mapped_column(String(255), nullable=False, comment="Key 哈希值，仅保存哈希")

    status: Mapped[str] = mapped_column(String(20), nullable=False, default='enabled', comment="enabled / disabled / expired")
    use_count: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, comment="累计调用次数")
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="过期时间")

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())