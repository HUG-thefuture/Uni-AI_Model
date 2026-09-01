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