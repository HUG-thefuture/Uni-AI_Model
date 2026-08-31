from pydantic import BaseModel,Field



USERNAME_PATTERN = r"^[A-Za-z0-9_]{3,32}$"
class Register_req(BaseModel):
    username: str = Field(pattern=USERNAME_PATTERN, description="3-32位字母/数字/下划线")
    password: str = Field(min_length=8, max_length=64, description="至少8位")
    school: str | None = Field(default=None, max_length=100)
    nickname: str | None = Field(default=None, max_length=50)
