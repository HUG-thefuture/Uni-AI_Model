"""models 表:模型元数据(线上与本地统一存储),成员2负责。

- user_id 不在本表;调用归属在 ai_tasks.user_id(逻辑外键 users.id,见 docs/数据字典.md);
- config_json 只存温度、max_tokens 等非敏感参数,严禁存任何密钥;
- 内置供应商(siliconflow/dashscope/ollama)的密钥走环境变量;自定义供应商的
  api_key 存本表(敏感字段,管理端返回时脱敏)。
"""
from decimal import Decimal

from sqlalchemy import BigInteger, Integer, JSON, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..core.db import Base
from .base import TimestampMixin, pk_column


class Model(TimestampMixin, Base):
    __tablename__ = "models"
    __table_args__ = (
        UniqueConstraint("model_code", "provider_type", name="uk_model_code_provider"),
        {"comment": "模型元数据表"},
    )

    id: Mapped[int] = pk_column()
    name: Mapped[str] = mapped_column(String(100), nullable=False, comment="展示名")
    model_code: Mapped[str] = mapped_column(
        String(200), nullable=False, comment="厂商调用名,如 Qwen/Qwen2.5-7B-Instruct"
    )
    provider_type: Mapped[str] = mapped_column(
        String(20), nullable=False, comment="online / local"
    )
    model_type: Mapped[str] = mapped_column(
        String(20), nullable=False, comment="text / image / audio / video"
    )
    vendor: Mapped[str] = mapped_column(
        String(30), nullable=False, comment="内置 siliconflow/dashscope/ollama/mock,或自定义供应商名"
    )
    endpoint: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="自定义端点/base_url(本地或自定义 OpenAI 兼容供应商用,可空)"
    )
    api_key: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="自定义供应商密钥(敏感;内置供应商走环境变量,此字段留空)"
    )
    price_per_call: Mapped[Decimal] = mapped_column(
        Numeric(10, 4), nullable=False, default=0, server_default="0",
        comment="供应商成本单价(元/张·条·次,4位小数);per_call 时生效,售价=成本×加价",
    )
    billing_mode: Mapped[str] = mapped_column(
        String(20), nullable=False, default="per_call", server_default="per_call",
        comment="计费方式: per_call(按次) / per_token(按实际token)",
    )
    # token 单价单位:0.0001 积分/千token(整数)。例:qwen-max 输入 2.4元/1M token
    # = 0.0024 积分/千token → 存 24。此为「供应商成本价」;用户售价 = 成本 × 加价比例
    token_input_price: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, server_default="0",
        comment="输入token成本单价(0.0001积分/千token,整数);billing_mode=per_token 时生效",
    )
    token_output_price: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, server_default="0",
        comment="输出token成本单价(0.0001积分/千token,整数);billing_mode=per_token 时生效",
    )
    token_markup_pct: Mapped[int | None] = mapped_column(
        Integer, nullable=True,
        comment="token售价加价百分比(130=成本加价30%);NULL 时用全局 TOKEN_MARKUP_PCT",
    )
    max_duration_sec: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, comment="音视频时长上限(秒,可空)"
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="enabled", server_default="enabled",
        comment="enabled / disabled",
    )
    config_json: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="非敏感参数 JSON(温度/max_tokens 等,严禁存密钥)"
    )
    description: Mapped[str | None] = mapped_column(String(500), nullable=True, comment="模型说明")
    capability_tags: Mapped[list | None] = mapped_column(
        JSON, nullable=True, comment="能力标签,如 [\"对话\",\"推理\"]"
    )
