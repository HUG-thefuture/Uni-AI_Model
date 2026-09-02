"""用户模块管理端/个人中心 请求与响应模型(成员1负责)。"""
from datetime import datetime

from pydantic import BaseModel, Field


class UserAdminOut(BaseModel):
    """管理员看到的用户条目(绝不包含 password_hash)。"""

    id: int
    username: str
    role: str
    status: int
    real_auth_status: int
    school: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class PageResult(BaseModel):
    """通用分页响应。"""

    total: int
    page: int
    page_size: int
    items: list


class StatusUpdateIn(BaseModel):
    """启用/禁用请求。"""

    status: int = Field(ge=0, le=1, description="0 禁用, 1 启用")
