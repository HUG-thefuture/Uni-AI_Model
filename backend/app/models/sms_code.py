from datetime import datetime

from sqlalchemy import DateTime, Index, SmallInteger, String, func
from sqlalchemy.orm import Mapped, mapped_column

from ..core.db import Base
from .base import pk_column


class SmsCode(Base):
    """短信验证码:手机号+用途维度的一次性验证码,只存哈希不存明文。"""

    __tablename__ = "sms_codes"
    __table_args__ = (
        Index("idx_sms_phone", "phone"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )

    id: Mapped[int] = pk_column()
    phone: Mapped[str] = mapped_column(String(20), nullable=False, comment="手机号")
    purpose: Mapped[str] = mapped_column(String(20), nullable=False, comment="用途:login 登录 / bind 绑定手机号")
    code_hash: Mapped[str] = mapped_column(String(128), nullable=False, comment="验证码哈希(sha256(code+phone+盐))")
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="过期时间")
    attempts: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=0, server_default="0", comment="已校验失败次数"
    )
    used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="使用时间(校验通过后写入)")
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="发送来源 IP")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), comment="创建时间"
    )
