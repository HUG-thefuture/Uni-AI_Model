"""支付相关请求模型。"""
from pydantic import BaseModel, Field
from typing import Literal


class RechargeRequest(BaseModel):
    """POST /wallet/recharge:充值下单(amount 为积分,1 元 = 1 积分)。"""

    amount: int = Field(..., description="充值积分(1-100000,1元=1积分)")
    payment_method: Literal["mock", "alipay"] = Field(
        default="alipay", description="支付方式: alipay(支付宝沙箱) / mock(内置模拟收银台)"
    )


class MockPayRequest(BaseModel):
    """预留请求体(内置收银台确认支付,当前无字段)。"""
