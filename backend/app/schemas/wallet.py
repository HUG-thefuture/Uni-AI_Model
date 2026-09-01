from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime

class RechargeRequest(BaseModel):
    amount: int=Field(...,gt=0,description="充值金额，必须大于0")
    payment_method: str=Field(default="mock",description="支付方式")


class RechargeResponse(BaseModel):
    order_no: str
    amount: int
    payment_method: str
    status: str
    created_at: datetime

    model_config = ConfigDict(
        from_attributes=True
    )

class WalletResponse(BaseModel):
    balance: int
    total_recharged: int
    total_consumed: int

    model_config = ConfigDict(
        from_attributes=True
    )


class WalletRecordItem(BaseModel):
    type: str  # 类型：'recharge'(充值) 或 'consumption'(消费)
    order_no: str  # 关联的订单号或任务ID
    amount: int  # 变动金额（正数=进账，负数=支出）
    status: str  # 状态：'paid' / 'success' / 'failed'
    created_at: datetime  # 发生时间

    class Config:
        from_attributes = True


# 分页响应模型
class WalletRecordsResponse(BaseModel):
    list: list[WalletRecordItem]
    total: int
    page: int
    page_size: int
