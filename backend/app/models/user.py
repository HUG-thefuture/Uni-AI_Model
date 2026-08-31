from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import BigInteger, Index, Integer, SmallInteger, String, UniqueConstraint
from app.models.base import TimestampMixin, pk_column
from app.core.db import Base

class User(TimestampMixin, Base):
    """用户主表:登录身份、角色、启用状态。"""

    __tablename__ = "users"
    __table_args__ = (
        Index("idx_status", "status"),
        {"comment": "用户主表"},
    )

    id: Mapped[int] = pk_column()
    username: Mapped[str] = mapped_column(
        String(50), nullable=False, unique=True, comment="用户名(唯一)"
    )
    password_hash: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="密码哈希,禁止明文"
    )
    role: Mapped[str] = mapped_column(
        String(20), nullable=False, default="user", server_default="user",
        comment="user / admin",
    )
    status: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=1, server_default="1", comment="1启用 0禁用"
    )
    real_auth_status: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=0, server_default="0",
        comment="0未认证 1已认证 2审核中(P1实名认证预留)",
    )
    school: Mapped[str | None] = mapped_column(String(100), nullable=True, comment="学校")


class UserProfile(TimestampMixin, Base):
    """用户资料表:user_id 唯一,一对一。"""

    __tablename__ = "user_profiles"
    __table_args__ = (
        UniqueConstraint("user_id", name="uk_user_id"),
        {"comment": "用户资料表"},
    )

    id: Mapped[int] = pk_column()
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="逻辑外键 users.id")
    nickname: Mapped[str | None] = mapped_column(String(50), nullable=True, comment="昵称")
    avatar_url: Mapped[str | None] = mapped_column(String(255), nullable=True, comment="头像地址")
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True, comment="手机号")
    email: Mapped[str | None] = mapped_column(String(100), nullable=True, comment="邮箱")
    major: Mapped[str | None] = mapped_column(String(100), nullable=True, comment="专业")
    bio: Mapped[str | None] = mapped_column(String(500), nullable=True, comment="简介")


class Wallet(TimestampMixin, Base):
    """钱包表:user_id 为主键,注册时余额 0。"""

    __tablename__ = "wallets"
    __table_args__ = {"comment": "钱包表(金额单位:分,整数)"}

    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, comment="主键,逻辑外键 users.id")
    balance: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, server_default="0", comment="可用余额(分)"
    )
    total_recharged: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, server_default="0", comment="累计充值(分)"
    )
    total_consumed: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, server_default="0", comment="累计消费(分)"
    )
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0", comment="乐观锁版本号"
    )

