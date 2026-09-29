"""模型广场 / 管理端模型 CRUD 的 Pydantic v2 请求模型(WP03)。

- 枚举合法性(provider_type/model_type/vendor/status)在 service 层校验并返回中文 400 提示,
  这里只做结构与长度/非负约束;
- config_json 接受对象或 JSON 字符串,入库统一序列化为 JSON 字符串(models.config_json 为 Text);
- price_per_call 为元(浮点,4 位小数,≥0);token 单价保持整数(0.0001 元/千token)。
"""
from typing import Literal

from pydantic import BaseModel, Field


class ModelCreateRequest(BaseModel):
    """POST /admin/models 请求体(除标注可选外均为必填)。"""

    name: str = Field(min_length=1, max_length=100, description="展示名")
    model_code: str = Field(min_length=1, max_length=200, description="厂商调用名")
    provider_type: str = Field(min_length=1, max_length=20, description="online / local")
    model_type: str = Field(min_length=1, max_length=20, description="text / image / audio / video")
    vendor: str = Field(min_length=1, max_length=30, description="siliconflow / dashscope / ollama / mock 或自定义供应商名")
    endpoint: str | None = Field(default=None, max_length=255, description="自定义端点/base_url,本地或自定义供应商用,可空")
    api_key: str | None = Field(default=None, max_length=255, description="自定义供应商密钥(敏感),内置供应商留空")
    price_per_call: float = Field(ge=0, description="成本单价(元/张·条·次),非负")
    billing_mode: Literal["per_call", "per_token"] = Field(default="per_call", description="计费方式: per_call(按量) / per_token(按实际token)")
    token_input_price: int = Field(default=0, ge=0, description="输入token成本单价(0.0001元/千token,整数)")
    token_output_price: int = Field(default=0, ge=0, description="输出token成本单价(0.0001元/千token,整数)")
    token_markup_pct: int | None = Field(default=None, ge=1, le=10000, description="售价加价百分比(130=成本加价30%);留空用全局默认")
    max_duration_sec: int | None = Field(default=None, ge=0, description="音视频时长上限(秒),可空")
    description: str | None = Field(default=None, max_length=500, description="模型说明")
    capability_tags: list[str] | None = Field(default=None, description="能力标签,如 [\"对话\",\"推理\"]")
    config_json: dict | str | None = Field(default=None, description="非敏感参数(严禁存密钥),对象或 JSON 字符串")


class ModelUpdateRequest(BaseModel):
    """PUT /admin/models/{id} 请求体:部分更新,未传字段不修改。"""

    name: str | None = Field(default=None, min_length=1, max_length=100)
    model_code: str | None = Field(default=None, min_length=1, max_length=200)
    provider_type: str | None = Field(default=None, min_length=1, max_length=20)
    model_type: str | None = Field(default=None, min_length=1, max_length=20)
    vendor: str | None = Field(default=None, min_length=1, max_length=30)
    endpoint: str | None = Field(default=None, max_length=255)
    api_key: str | None = Field(default=None, max_length=255)
    price_per_call: float | None = Field(default=None, ge=0)
    billing_mode: Literal["per_call", "per_token"] | None = Field(default=None, description="per_call / per_token")
    token_input_price: int | None = Field(default=None, ge=0)
    token_output_price: int | None = Field(default=None, ge=0)
    token_markup_pct: int | None = Field(default=None, ge=1, le=10000, description="传 null 表示恢复全局默认加价")
    max_duration_sec: int | None = Field(default=None, ge=0)
    description: str | None = Field(default=None, max_length=500)
    capability_tags: list[str] | None = None
    config_json: dict | str | None = None


class ModelStatusRequest(BaseModel):
    """PUT /admin/models/{id}/status 请求体。"""

    status: str = Field(min_length=1, max_length=20, description="enabled / disabled")


class FetchModelsRequest(BaseModel):
    """POST /admin/models/fetch 请求体:手动获取供应商可用模型列表。"""

    base_url: str = Field(min_length=1, max_length=255, description="供应商 OpenAI 兼容 base_url")
    api_key: str = Field(min_length=1, max_length=255, description="供应商 api_key")
