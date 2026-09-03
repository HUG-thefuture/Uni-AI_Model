"""模型广场 / 管理端模型 CRUD 的 Pydantic v2 请求模型(WP03)。

- 枚举合法性(provider_type/model_type/vendor/status)在 service 层校验并返回中文 400 提示,
  这里只做结构与长度/非负约束;
- config_json 接受对象或 JSON 字符串,入库统一序列化为 JSON 字符串(models.config_json 为 Text);
- 金额/积分一律整数(price_per_call ≥ 0),禁止浮点。
"""
from pydantic import BaseModel, Field


class ModelCreateRequest(BaseModel):
    """POST /admin/models 请求体(除标注可选外均为必填)。"""

    name: str = Field(min_length=1, max_length=100, description="展示名")
    model_code: str = Field(min_length=1, max_length=200, description="厂商调用名")
    provider_type: str = Field(min_length=1, max_length=20, description="online / local")
    model_type: str = Field(min_length=1, max_length=20, description="text / image / audio / video")
    vendor: str = Field(min_length=1, max_length=30, description="siliconflow / dashscope / ollama / mock")
    endpoint: str | None = Field(default=None, max_length=255, description="自定义端点,本地模型用,可空")
    price_per_call: int = Field(ge=0, description="积分点/次,非负整数")
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
    price_per_call: int | None = Field(default=None, ge=0)
    max_duration_sec: int | None = Field(default=None, ge=0)
    description: str | None = Field(default=None, max_length=500)
    capability_tags: list[str] | None = None
    config_json: dict | str | None = None


class ModelStatusRequest(BaseModel):
    """PUT /admin/models/{id}/status 请求体。"""

    status: str = Field(min_length=1, max_length=20, description="enabled / disabled")
