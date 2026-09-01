from pydantic import BaseModel,Field
from datetime import datetime


USERNAME_PATTERN = r"^[A-Za-z0-9_]{3,32}$"
class Register_req(BaseModel):
    # 注册请求
    username: str = Field(pattern=USERNAME_PATTERN, description="3-32位字母/数字/下划线")
    password: str = Field(min_length=8, max_length=64, description="至少8位")
    school: str | None = Field(default=None, max_length=100)
    nickname: str | None = Field(default=None, max_length=50)

class User_out(BaseModel):
        """用户信息返回:永远不包含 password_hash。"""
        id: int
        username: str
        role: str
        status: int
        real_auth_status: int
        school: str | None = None
        created_at: datetime
        model_config = {"from_attributes": True}


class Login_req(BaseModel):
    """登录请求。"""
    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=64)

class Profile_res(BaseModel):
    nickname: str | None = None
    avatar_url: str | None = None
    phone: str | None = None
    email: str | None = None
    major: str | None = None
    bio: str | None = None
    model_config = {"from_attributes": True}


class profile_update_req(BaseModel):
    nickname: str | None = Field(default=None, max_length=50)
    avatar_url: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=20)
    email: str | None = Field(default=None, max_length=100)
    major: str | None = Field(default=None, max_length=100)
    bio: str | None = Field(default=None, max_length=500)