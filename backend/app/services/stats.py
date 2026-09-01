from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.consumption_record import ConsumptionRecord


async def get_stats_usage(db:AsyncSession,user_id:int)->dict:
    success_records = (
        ConsumptionRecord.user_id == user_id,
        ConsumptionRecord.status == "success",
    )
    total_call = await db.scalar(
        select(func.count()).select_from(ConsumptionRecord).where(*success_records)
    )

    total_cost = await db.scalar(
        select(func.coalesce(func.sum(ConsumptionRecord.amount), 0)).where(*success_records)
    )

    total_tokens=0

    return {
        "total_call": total_call or 0,
        "total_cost": total_cost or 0,
        "total_tokens":total_tokens,
    }
