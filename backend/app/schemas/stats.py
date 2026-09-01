from pydantic import BaseModel


class UsageStatsResponse(BaseModel):
    total_call:int
    total_tokens:int
    total_cost:int