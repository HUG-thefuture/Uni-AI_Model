from sqlalchemy import BigInteger, Integer, DateTime, func, String, Index
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime
from ..core.db import Base


class RechargeOrder(Base):
    __tablename__ = "recharge_orders"
    __table_args__ = (
        # 映射 SQL 中的 UNIQUE KEY uk_order_no (order_no)
        # 由于我们在字段定义了 unique=True，这里可以省略；但为了统一表级定义，也可以写上。
        # 映射 SQL 中的 KEY idx_recharge_user_created (user_id, created_at)
        Index('idx_recharge_user_created', 'user_id', 'created_at'),
        # 映射 SQL 中的 KEY idx_recharge_status_created (status, created_at)
        Index('idx_recharge_status_created', 'status', 'created_at'),
        {'mysql_engine': 'InnoDB', 'mysql_charset': 'utf8mb4'}
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    order_no: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, comment="业务订单号")
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True, comment="逻辑外键 users.id")
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, comment="充值金额(分)")
    points: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, comment="到账积分/点数")

    payment_method: Mapped[str] = mapped_column(String(30), nullable=False, default='mock',
                                                comment="支付方式: alipay / wxpay / bank / mock")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default='pending',
                                        comment="pending / paid / failed / cancelled")
    external_trade_no: Mapped[str | None] = mapped_column(String(128), nullable=True, comment="第三方支付流水号")

    paid_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="支付成功时间")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())