from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.db import get_async_db
from ..core.deps import get_current_user
from ..core.response import ok
from ..schemas.stats import UsageStatsResponse
from ..services import stats

router = APIRouter(
    prefix="/stats",
    tags=["调用统计"]
)

@router.get("/usage")
async def usage_stats(
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(get_current_user),
    model_id: int | None = Query(None, ge=1, description="按模型筛选"),
    task_type: str | None = Query(None, description="按任务类型筛选:text/image/audio_clone/asr/video"),
    days: int | None = Query(None, ge=1, le=365, description="最近 N 天"),
    limit: int = Query(20, ge=1, le=100, description="明细条数上限"),
):
    """个人用量统计:统一响应壳包裹(前端 request() 依赖 code=0 判定成功)。

    支持按模型 / 任务类型 / 时间范围筛选,并返回按模型聚合的汇总。
    """
    data = await stats.get_stats_usage(
        db, current_user.id, model_id=model_id, task_type=task_type, days=days, limit=limit,
    )
    return ok(UsageStatsResponse(**data).model_dump(mode="json"))
