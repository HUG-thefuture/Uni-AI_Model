"""个人用量统计响应模型(含近期任务 token 明细与按模型汇总)。
金额字段单位:元(后端由微元换算,4 位小数)。
"""
from pydantic import BaseModel


class UsageItem(BaseModel):
    task_id: int
    task_type: str
    model_id: int | None = None
    model_name: str | None = None
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost: float
    created_at: str | None = None


class ModelBreakdownItem(BaseModel):
    model_id: int | None = None
    model_name: str
    calls: int
    tokens: int
    cost: float


class UsageStatsResponse(BaseModel):
    total_call: int
    total_tokens: int
    total_cost: float
    items: list[UsageItem] = []
    model_breakdown: list[ModelBreakdownItem] = []
