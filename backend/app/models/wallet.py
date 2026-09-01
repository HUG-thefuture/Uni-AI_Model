from sqlalchemy import BigInteger, Integer, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime
from core.db import Base


class Wallet(Base):
    __tablename__ = "wallets"
    __table_args__ = (
        # 表级别参数：指定 InnoDB 引擎和 utf8mb4 字符集（宝塔环境通用）
        {'mysql_engine': 'InnoDB', 'mysql_charset': 'utf8mb4'}
    )
    # 逻辑外键，直接作为主键
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, comment="逻辑外键 users.id")
    # 金额单位为“分”，所以用 Integer 或 BigInteger
    balance: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, comment="可用余额(分)")
    total_recharged: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, comment="累计充值金额(分)")
    total_consumed: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, comment="累计消费金额(分)")
    # 乐观锁版本号，防并发扣减
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="乐观锁版本号")

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(),
                                                 comment="更新时间")