"""ai_tasks 表:四类 AI 任务统一(文本/图像/声音克隆/语音识别/视频),成员2负责。

- user_id 逻辑外键 users.id(见 docs/数据字典.md),应用层校验归属;
- cost 为整数积分点,失败一律为 0(红线:调用失败不得扣费);
- status 四态:pending → processing → succeeded / failed(前端轮询依赖此口径)。
"""
from sqlalchemy import BigInteger, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..core.db import Base
from .base import TimestampMixin, pk_column


class AiTask(TimestampMixin, Base):
    __tablename__ = "ai_tasks"
    __table_args__ = (
        Index("idx_user_created", "user_id", "created_at"),
        Index("idx_status_created", "status", "created_at"),
        Index("idx_task_type", "task_type"),
        {"comment": "AI 任务表(文本/图像/声音/视频统一)"},
    )

    id: Mapped[int] = pk_column()
    request_id: Mapped[str] = mapped_column(String(64), nullable=False, comment="链路 ID")
    user_id: Mapped[int] = mapped_column(
        BigInteger, nullable=False, comment="所属用户,逻辑外键 users.id"
    )
    model_id: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="模型,逻辑外键 models.id")
    task_type: Mapped[str] = mapped_column(
        String(20), nullable=False, comment="text / image / audio_clone / asr / video"
    )
    prompt: Mapped[str | None] = mapped_column(Text, nullable=True, comment="用户输入")
    params_json: Mapped[str | None] = mapped_column(Text, nullable=True, comment="调用参数 JSON")
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending", server_default="pending",
        comment="pending / processing / succeeded / failed",
    )
    result_text: Mapped[str | None] = mapped_column(Text, nullable=True, comment="文本结果")
    result_url: Mapped[str | None] = mapped_column(Text, nullable=True, comment="文件结果地址或地址数组 JSON")
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True, comment="失败原因(中文)")
    cost: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, server_default="0",
        comment="消耗积分点(整数,失败为 0)",
    )
    cost_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="frozen", server_default="frozen",
        comment="frozen(预冻结) / settled(结算) / refunded(退回)",
    )
    latency_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True, comment="总耗时(毫秒)")
