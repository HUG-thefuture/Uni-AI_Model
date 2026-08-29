"""支撑表 ORM(成员1/成员4 职责范围内的表,这里按 docs/数据字典.md 与 wp 提示词口径建 ORM,
使成员2 的任务/开放平台链路可自测;DDL 归口在 sql/ 目录,成员4 拥有最终字段解释权):

- users / wallets:成员1 定稿口径(数据字典 v1.0)
- consumption_records / operation_logs:成员4 表,本期按最小字段落地,字段变更以成员4 为准(TODO 登记 docs/api.md)
- api_keys / api_usage_logs:wp06 定义的开放平台表(成员4 建表,ORM 先行)
- chat_sessions / chat_messages:wp04 定义的会话与消息表(成员2)
"""
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import TimestampMixin, pk_column


class User(Base):
    """users 表(口径:docs/数据字典.md,成员1 拥有字段解释权)。"""

    __tablename__ = "users"
    __table_args__ = ({"comment": "用户主表(成员1)"},)

    id: Mapped[int] = pk_column()
    username: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="user", server_default="user")
    status: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    real_auth_status: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    school: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )


class Wallet(Base):
    """wallets 表(口径:docs/数据字典.md,成员4 拥有扣费事务最终实现)。"""

    __tablename__ = "wallets"

    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    balance: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, server_default="0")
    total_recharged: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, server_default="0")
    total_consumed: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, server_default="0")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )


class ConsumptionRecord(Base):
    """consumption_records 消费流水(成员4 表,最小字段桩,TODO: 字段对齐)。"""

    __tablename__ = "consumption_records"

    id: Mapped[int] = pk_column()
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    task_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    model_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="消耗积分点(整数)")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())


class OperationLog(TimestampMixin, Base):
    """operation_logs 管理操作日志(成员4 表,最小字段桩)。"""

    __tablename__ = "operation_logs"

    id: Mapped[int] = pk_column()
    user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(50), nullable=False)
    resource_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    detail_json: Mapped[str | None] = mapped_column(Text, nullable=True)


class ApiKey(Base):
    """api_keys 表(wp06 口径;成员4 建表与 Key 管理页面,成员2 只做校验)。"""

    __tablename__ = "api_keys"

    id: Mapped[int] = pk_column()
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    key_prefix: Mapped[str] = mapped_column(String(16), nullable=False, comment="明文前缀 sk-xxxxxx,便于辨认")
    key_hash: Mapped[str] = mapped_column(String(64), nullable=False, comment="sha256(明文),不存明文")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="enabled", server_default="enabled")
    use_count: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, server_default="0")
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    __table_args__ = (Index("uk_key_hash", "key_hash", unique=True),)


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
