"""个人用量统计:调用次数、消费金额、token 总量 + 近期任务明细 + 按模型汇总。

口径:
- 统计对象为当前用户 status=succeeded 的任务(门户聊天与开放平台共用 ai_tasks);
- 支持按模型(model_id)/任务类型(task_type)/时间范围(days)筛选;
- total_tokens = sum(prompt_tokens + completion_tokens),历史数据列为空按 0 计;
- total_cost = sum(cost),账本为微元(1 元 = 10_000 微元),API 输出换算为「元」;
- total_call 只统计成功调用(与消费口径一致,失败调用不扣费也不计入);
- items 为筛选后最近 limit(默认 20,上限 100)条成功任务的 token 明细;
- model_breakdown 为筛选范围内按模型聚合的调用次数 / token / 消费。
"""
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.ai_task import AiTask
from ..models.model import Model
from ..services.pricing import to_yuan

DETAIL_LIMIT = 20
DETAIL_LIMIT_MAX = 100


async def get_stats_usage(db: AsyncSession, user_id: int, *, model_id: int | None = None,
                          task_type: str | None = None, days: int | None = None,
                          limit: int = DETAIL_LIMIT) -> dict:
    conditions = [AiTask.user_id == user_id, AiTask.status == "succeeded"]
    if model_id:
        conditions.append(AiTask.model_id == model_id)
    if task_type:
        conditions.append(AiTask.task_type == task_type)
    if days and days > 0:
        conditions.append(AiTask.created_at >= datetime.now() - timedelta(days=days))

    total_call = await db.scalar(
        select(func.count()).select_from(AiTask).where(*conditions)
    )
    total_cost = await db.scalar(
        select(func.coalesce(func.sum(AiTask.cost), 0)).where(*conditions)
    )
    total_tokens = await db.scalar(
        select(func.coalesce(
            func.sum(
                func.coalesce(AiTask.prompt_tokens, 0)
                + func.coalesce(AiTask.completion_tokens, 0)
            ), 0)
        ).where(*conditions)
    )

    # 按模型汇总(同一筛选条件):模型 / 调用次数 / token / 消费(元)
    breakdown_rows = (
        await db.execute(
            select(
                Model.id, Model.name, Model.model_code,
                func.count().label("calls"),
                func.coalesce(func.sum(
                    func.coalesce(AiTask.prompt_tokens, 0)
                    + func.coalesce(AiTask.completion_tokens, 0)
                ), 0).label("tokens"),
                func.coalesce(func.sum(AiTask.cost), 0).label("cost"),
            )
            .outerjoin(Model, Model.id == AiTask.model_id)
            .where(*conditions)
            .group_by(Model.id, Model.name, Model.model_code)
            .order_by(func.coalesce(func.sum(AiTask.cost), 0).desc())
        )
    ).all()
    model_breakdown = [
        {
            "model_id": model_id_,
            "model_name": name or code or f"模型#{model_id_}",
            "calls": int(calls or 0),
            "tokens": int(tokens or 0),
            "cost": to_yuan(cost),
        }
        for model_id_, name, code, calls, tokens, cost in breakdown_rows
    ]

    # 近期成功任务的 token 明细(时间倒序),联模型表取名称
    rows = (
        await db.execute(
            select(AiTask, Model.name, Model.model_code)
            .outerjoin(Model, Model.id == AiTask.model_id)
            .where(*conditions)
            .order_by(AiTask.id.desc())
            .limit(max(1, min(int(limit or DETAIL_LIMIT), DETAIL_LIMIT_MAX)))
        )
    ).all()
    items = [
        {
            "task_id": task.id,
            "task_type": task.task_type,
            "model_id": task.model_id,
            "model_name": model_name or model_code or f"模型#{task.model_id}",
            "prompt_tokens": task.prompt_tokens or 0,
            "completion_tokens": task.completion_tokens or 0,
            "total_tokens": (task.prompt_tokens or 0) + (task.completion_tokens or 0),
            "cost": to_yuan(task.cost),
            "created_at": task.created_at.isoformat() if task.created_at else None,
        }
        for task, model_name, model_code in rows
    ]

    return {
        "total_call": total_call or 0,
        "total_cost": to_yuan(total_cost),
        "total_tokens": total_tokens or 0,
        "items": items,
        "model_breakdown": model_breakdown,
    }
