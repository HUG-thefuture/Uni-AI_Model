"""支撑表 ORM(兼容层)。

成员1/成员4 的正式 ORM 已迁至独立模块:
- users / user_profiles / wallets -> app/models/user.py
- consumption_records             -> app/models/consumption_record.py
- operation_logs                  -> app/models/operation_log.py
- api_keys                        -> app/models/api_key.py
- recharge_orders                 -> app/models/recharge_order.py

本模块保留这些名字的重导出(成员2 的服务/路由/测试历史 import 路径不变),
并继续持有 app.models 尚未承接的三张表:api_usage_logs / chat_sessions / chat_messages。
"""
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from ..core.db import Base
from .api_key import ApiKey
from .base import TimestampMixin, pk_column
from .consumption_record import ConsumptionRecord
from .operation_log import OperationLog
from .user import User, Wallet

__all__ = [
    "User",
    "Wallet",
    "ConsumptionRecord",
    "OperationLog",
    "ApiKey",
    "ApiUsageLog",
    "ChatSession",
    "ChatMessage",
]


class ApiUsageLog(Base):
    """api_usage_logs 开放平台调用统计(wp06 口径)。"""

    __tablename__ = "api_usage_logs"

    id: Mapped[int] = pk_column()
    key_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    path: Mapped[str] = mapped_column(String(200), nullable=False)
    model_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    status_code: Mapped[int] = mapped_column(Integer, nullable=False)
    latency_ms: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())


class ChatSession(TimestampMixin, Base):
    """chat_sessions 对话会话(wp04)。"""

    __tablename__ = "chat_sessions"
    __table_args__ = (Index("idx_session_user_updated", "user_id", "updated_at"),)

    id: Mapped[int] = pk_column()
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    title: Mapped[str] = mapped_column(String(100), nullable=False, comment="首条消息前 20 字")
    model_id: Mapped[int] = mapped_column(BigInteger, nullable=False)


class ChatMessage(Base):
    """chat_messages 对话消息(wp04)。"""

    __tablename__ = "chat_messages"
    __table_args__ = (Index("idx_msg_session_created", "session_id", "created_at"),)

    id: Mapped[int] = pk_column()
    session_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False, comment="user / assistant")
    content: Mapped[str] = mapped_column(Text, nullable=False)
    model_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    tokens_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
