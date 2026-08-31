from sqlalchemy.orm import Mapped,mapped_column
from sqlalchemy import Index, String, SmallInteger
from backend.app.models.base import TimestampMixin, pk_column
from backend.app.core.db import Base

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

