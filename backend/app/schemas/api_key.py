from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime
from typing import Optional

class ApiKeyCreate(BaseModel):
    name: str=Field(...,max_length=100,description="key名称")

class ApiKeyCreateResponse(BaseModel):
    id:int
    name:str
    key:str
    created_at:datetime


class ApiKeyListResponse(BaseModel):
    id: int
    name: str
    status: str
    key_prefix: str
    use_count:int
    created_at: datetime

    model_config = ConfigDict(
        from_attributes=True
    )

class ApiKeyStatusUpdate(BaseModel):
    status: str = Field(..., pattern="^(enabled|disabled)$", description="状态：enabled 或 disabled")

