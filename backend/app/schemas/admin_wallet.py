from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class AdminWalletItem(BaseModel):
    user_id: int
    username: str
    balance: int
    total_recharge: int
    total_consumed:int
    created_at:datetime


class AdminPaginatedResponse(BaseModel):
    list:list
    total:int
    page:int
    page_size:int


class AdminConsumptionItem(BaseModel):
    id:int
    user_id: int
    model_id: int
    amount: int
    status: str
    created_at:datetime

    model_config = ConfigDict(
        from_attributes=True
    )


class AdminStatsResponse(BaseModel):
    total_call:int
    total_tokens:int
    total_cost:int



# 发票申请请求
class InvoiceCreate(BaseModel):
    amount: int = Field(..., gt=0, description="开票金额")
    title: str = Field(..., max_length=100, description="发票抬头")
    type: str = Field(default="personal", description="发票类型")
    tax_no: str | None = Field(default=None, max_length=50, description="税号")

# 发票响应
class InvoiceResponse(BaseModel):
    id: int
    amount: int
    title: str
    type: str
    status: str
    created_at: datetime

    class Config:
        from_attributes = True