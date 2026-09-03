from datetime import datetime

from sqlalchemy import Index, BigInteger, String, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column

from ..core.db import Base


class Invoice(Base):
    __tablename__ = "invoices"
    __table_args__ = (
        Index("idx_invoice_user_created", "user_id", "created_at"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="逻辑外键 users.id")
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, comment="开票金额(积分)")
    title: Mapped[str] = mapped_column(String(100), nullable=False, comment="发票抬头")
    type: Mapped[str] = mapped_column(String(20), nullable=False, default="personal", comment="发票类型: personal / enterprise")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", comment="状态: pending / issued / rejected")
    tax_no: Mapped[str | None] = mapped_column(String(50), nullable=True, comment="企业税号(可空)")

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
