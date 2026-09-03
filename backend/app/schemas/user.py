"""用户资料与管理端用户接口的数据结构。"""
import re
from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class ProfileUpdateRequest(BaseModel):
    nickname: str | None = Field(default=None, max_length=50)
    avatar_url: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=20)
    email: str | None = Field(default=None, max_length=100)
    major: str | None = Field(default=None, max_length=100)
    bio: str | None = Field(default=None, max_length=500)

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, value: str | None) -> str | None:
        if value is not None and value and re.fullmatch(r"\+?[0-9]{6,20}", value) is None:
            raise ValueError("手机号格式不正确")
        return value

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str | None) -> str | None:
        if value is not None and value and re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value) is None:
            raise ValueError("邮箱格式不正确")
        return value


class UserStatusUpdateRequest(BaseModel):
    status: int = Field(ge=0, le=1)


class AdminUserItem(BaseModel):
    id: int
    username: str
    role: str
    status: int
    real_auth_status: int
    school: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}
