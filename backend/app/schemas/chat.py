"""会话相关请求体(WP04)。响应统一走 core/response.ok(),不再单独建模。"""
from pydantic import BaseModel, Field


class ChatSessionCreate(BaseModel):
    """POST /chat/sessions 请求体。"""

    model_id: int = Field(..., gt=0, description="模型 ID,需存在且 enabled")
