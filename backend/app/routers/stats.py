from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_async_db
from app.core.response import ok
from app.models.user import get_current_user
from app.schemas.stats import UsageStatsResponse
from app.services import stats

router = APIRouter(
    prefix="/stats",
    tags=["调用统计"]
)

@router.get("/usage")
async def usage_stats(db: AsyncSession = Depends(get_async_db), current_user=Depends(get_current_user)):
    stmt=await stats.get_stats_usage(db,current_user.id)
    return ok(UsageStatsResponse.model_validate(stmt).model_dump(mode="json"))
