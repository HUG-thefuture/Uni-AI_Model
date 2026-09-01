"""ai_call_logs 表:每次模型调用记录(排障与统计依据),成员2负责。

与成员4 的 api_usage_logs(开放平台 Key 调用统计)口径不同:本表记录门户内部
Provider 层的每一次上游调用,含失败调用,用于超时重试分析与模型链路排障。
"""
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from ..core.db import Base
from .base import pk_column


class AiCallLog(Base):
    __tablename__ = "ai_call_logs"
    __table_args__ = ({"comment": "模型调用日志表(Provider 层)"},)

    id: Mapped[int] = pk_column()
    request_id: Mapped[str] = mapped_column(String(64), nullable=False, comment="链路 ID")
    user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, comment="用户,逻辑外键 users.id")
    model_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, comment="模型,逻辑外键 models.id")
    provider: Mapped[str] = mapped_column(String(30), nullable=False, comment="siliconflow / ollama / mock")
    latency_ms: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, comment="耗时(毫秒)")
    success: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, comment="是否成功")
    error_code: Mapped[str | None] = mapped_column(String(50), nullable=True, comment="错误码(成功为空)")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), comment="创建时间"
    )
