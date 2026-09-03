"""用户资料与管理端用户服务。"""
from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.response import APIError
from ..models.ai_call_log import AiCallLog
from ..models.ai_task import AiTask
from ..models.api_key import ApiKey
from ..models.consumption_record import ConsumptionRecord
from ..models.operation_log import OperationLog
from ..models.recharge_order import RechargeOrder
from ..models.support import ApiUsageLog, ChatMessage, ChatSession
from ..models.user import User, UserProfile, Wallet
from ..schemas.user import ProfileUpdateRequest


async def update_profile(
    db: AsyncSession, user_id: int, payload: ProfileUpdateRequest
) -> UserProfile:
    profile = await db.scalar(select(UserProfile).where(UserProfile.user_id == user_id))
    if profile is None:
        profile = UserProfile(user_id=user_id)
        db.add(profile)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(profile, key, value)
    await db.commit()
    await db.refresh(profile)
    return profile


async def list_users(
    db: AsyncSession,
    *,
    page: int,
    page_size: int,
    keyword: str | None,
    role: str | None,
    status: int | None,
) -> dict:
    filters = []
    if keyword:
        like = f"%{keyword}%"
        filters.append(or_(User.username.like(like), User.school.like(like)))
    if role:
        filters.append(User.role == role)
    if status is not None:
        filters.append(User.status == status)

    total = await db.scalar(select(func.count()).select_from(User).where(*filters))
    users = (
        await db.scalars(
            select(User)
            .where(*filters)
            .order_by(User.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    return {"total": total or 0, "page": page, "page_size": page_size, "items": list(users)}


async def update_user_status(
    db: AsyncSession, *, user_id: int, status: int, admin_id: int
) -> User:
    if user_id == admin_id:
        raise APIError(403, "禁止管理员禁用或启用自己")
    user = await db.get(User, user_id)
    if user is None:
        raise APIError(404, "用户不存在")
    user.status = status
    await db.commit()
    await db.refresh(user)
    return user


async def delete_user(db: AsyncSession, *, user_id: int, admin_id: int) -> dict:
    """删除账户:级联清理该用户全部关联数据后删除 users 记录。

    - 逻辑外键无物理约束,需按依赖顺序在应用层清理(先子表后主表);
    - 保护:禁止删除自己、禁止删除管理员账户(防止误删导致无管理员可用);
    - 资金/订单类数据一并删除(项目为逻辑外键,不留孤儿行)。
    """
    if user_id == admin_id:
        raise APIError(403, "禁止删除自己的账户")
    user = await db.get(User, user_id)
    if user is None:
        raise APIError(404, "用户不存在")
    if user.role == "admin":
        raise APIError(403, "禁止删除管理员账户")

    try:
        # 1. 聊天消息(通过该用户的会话关联)
        session_ids = select(ChatSession.id).where(ChatSession.user_id == user_id)
        await db.execute(delete(ChatMessage).where(ChatMessage.session_id.in_(session_ids)))
        # 2. 会话
        await db.execute(delete(ChatSession).where(ChatSession.user_id == user_id))
        # 3. 任务与调用日志
        await db.execute(delete(AiTask).where(AiTask.user_id == user_id))
        await db.execute(delete(AiCallLog).where(AiCallLog.user_id == user_id))
        # 4. 开放平台
        await db.execute(delete(ApiKey).where(ApiKey.user_id == user_id))
        await db.execute(delete(ApiUsageLog).where(ApiUsageLog.user_id == user_id))
        # 5. 资金与订单
        await db.execute(delete(ConsumptionRecord).where(ConsumptionRecord.user_id == user_id))
        await db.execute(delete(RechargeOrder).where(RechargeOrder.user_id == user_id))
        # 6. 操作日志
        await db.execute(delete(OperationLog).where(OperationLog.user_id == user_id))
        # 7. 资料与钱包
        await db.execute(delete(UserProfile).where(UserProfile.user_id == user_id))
        await db.execute(delete(Wallet).where(Wallet.user_id == user_id))
        # 8. 主表
        await db.execute(delete(User).where(User.id == user_id))
        await db.commit()
    except Exception:
        await db.rollback()
        raise APIError(500, "账户删除失败,请稍后重试") from None
    return {"id": user_id, "deleted": True}
