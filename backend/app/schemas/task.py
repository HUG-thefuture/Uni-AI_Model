"""任务相关请求体(WP04+WP05)。响应统一走 core/response.ok(),不再单独建模。"""
from pydantic import BaseModel, Field


class TextTaskCreate(BaseModel):
    """POST /tasks/text 请求体(SSE 流式对话)。"""

    session_id: int = Field(..., gt=0, description="会话 ID,需归属当前用户")
    model_id: int = Field(..., gt=0, description="模型 ID,需存在且 enabled")
    message: str = Field(..., min_length=1, max_length=4000, description="用户输入")


class ImageTaskParams(BaseModel):
    """图像任务可选参数。"""

    image_size: str | None = Field(default=None, description="尺寸,如 1024x1024,默认 1024x1024")
    num: int | None = Field(default=None, ge=1, le=4, description="生成数量 1..4,默认 1")
    image_url: str | None = Field(default=None, description="图生图参考图 URL(WP07 图生图预留)")


class ImageTaskCreate(BaseModel):
    """POST /tasks/image 请求体(异步四态任务)。"""

    model_id: int = Field(..., gt=0, description="模型 ID,需存在且 enabled 且 model_type=image")
    prompt: str = Field(..., min_length=1, max_length=2000, description="生成提示词")
    params: ImageTaskParams | None = Field(default=None, description="可选参数")
