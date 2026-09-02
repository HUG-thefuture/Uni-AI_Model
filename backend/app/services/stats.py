from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.consumption_record import ConsumptionRecord


async def get_stats_usage(db:AsyncSession,user_id:int)->dict:
    total_call=await db.scalar(
        select(func.count(ConsumptionRecord.id)
               .where(ConsumptionRecord.user_id == user_id,
                      ConsumptionRecord.status=="success")))

    total_cost=await db.scalar(
        select(func.sum(ConsumptionRecord.amount)
               .where(ConsumptionRecord.user_id == user_id,
                      ConsumptionRecord.status=="success"))
    )

    total_tokens=0

    return {
        "total_call":total_call,
        "total_cost":total_cost,
        "total_tokens":total_tokens,
    }
