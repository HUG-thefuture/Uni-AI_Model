"""短信认证相关请求模型(与项目命名约定保持一致:XXX_req)。"""
from typing import Literal

from pydantic import BaseModel, Field

PHONE_PATTERN = r"^1[3-9]\d{9}$"


class SmsSend_req(BaseModel):
    """发送短信验证码请求。"""

    phone: str = Field(min_length=1, max_length=20, description="11位大陆手机号")
    purpose: Literal["login", "bind"] = Field(description="验证码用途:login 登录 / bind 绑定手机号")


class SmsLogin_req(BaseModel):
    """短信验证码登录请求(手机号不存在时自动注册)。"""

    phone: str = Field(min_length=1, max_length=20, description="11位大陆手机号")
    code: str = Field(min_length=1, max_length=8, description="6位数字验证码")


class SmsBind_req(BaseModel):
    """绑定/换绑手机号请求(需登录,先校验新手机号的验证码)。"""

    phone: str = Field(min_length=1, max_length=20, description="11位大陆手机号")
    code: str = Field(min_length=1, max_length=8, description="6位数字验证码")
