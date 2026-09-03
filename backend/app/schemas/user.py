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


class AdminUserUpdateIn(BaseModel):
    """管理员编辑用户资料/角色。字段全部可选,只更新传入项。"""

    role: str | None = Field(default=None, pattern="^(user|admin)$")
    real_auth_status: int | None = Field(default=None, ge=0, le=2)
    school: str | None = Field(default=None, min_length=1, max_length=100)
    nickname: str | None = Field(default=None, min_length=1, max_length=50)
    phone: str | None = Field(default=None, max_length=20)
    email: str | None = Field(default=None, max_length=100)


class AdminBalanceIn(BaseModel):
    """管理员调整用户余额(分为单位,可正可负)。"""

    amount: int = Field(description="调整额(分),正数为充值/补发,负数为扣减/回收")
    reason: str | None = Field(default=None, max_length=200, description="调整原因(可选,写入操作日志)")


class AdminResetPasswordIn(BaseModel):
    """管理员重置用户密码。"""

    password: str = Field(min_length=8, max_length=64, description="新密码,至少8位")
