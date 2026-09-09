"""用户资料与管理端用户服务。"""
from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.response import APIError
from ..services.pricing import to_micro, to_yuan
from ..core.security import hash_password
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
    balance_min: int | None = None,
    balance_max: int | None = None,
    include_deleted: bool = False,
) -> dict:
    """管理端用户列表:分页 + 关键字/角色/状态/余额区间筛选,返回增强条目(含余额/昵称等)。"""
    filters = []
    if keyword:
        like = f"%{keyword}%"
        filters.append(or_(User.username.like(like), User.school.like(like)))
    if role:
        filters.append(User.role == role)
    if status is not None:
        filters.append(User.status == status)
    elif not include_deleted:
        filters.append(User.status != -1)  # 默认排除软删除
    # 余额区间筛选以「元」传入,账本为微元
    if balance_min is not None:
        filters.append(Wallet.balance >= to_micro(balance_min))
    if balance_max is not None:
        filters.append(Wallet.balance <= to_micro(balance_max))

    base = (
        select(User, Wallet, UserProfile)
        .outerjoin(Wallet, Wallet.user_id == User.id)
        .outerjoin(UserProfile, UserProfile.user_id == User.id)
        .where(*filters)
    )
    total = (
        await db.scalar(
            select(func.count(User.id))
            .select_from(User)
            .outerjoin(Wallet, Wallet.user_id == User.id)
            .outerjoin(UserProfile, UserProfile.user_id == User.id)
            .where(*filters)
        )
    ) or 0
    rows = (
        await db.execute(
            base.order_by(User.id).offset((page - 1) * page_size).limit(page_size)
        )
    ).all()
    items = [
        {
            "id": u.id,
            "username": u.username,
            "role": u.role,
            "status": u.status,
            "real_auth_status": u.real_auth_status,
            "school": u.school,
            "nickname": p.nickname if p else None,
            "phone": p.phone if p else None,
            "email": p.email if p else None,
            "balance": to_yuan(w.balance) if w else 0.0,
            "total_recharged": to_yuan(w.total_recharged) if w else 0.0,
            "total_consumed": to_yuan(w.total_consumed) if w else 0.0,
            "created_at": str(u.created_at),
        }
        for u, w, p in rows
    ]
    return {"total": total, "page": page, "page_size": page_size, "items": items}


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


async def get_user_detail(db: AsyncSession, target_id: int) -> dict:
    """用户详情:主表 + 资料 + 钱包。"""
    user = await db.get(User, target_id)
    if user is None:
        raise APIError(404, "用户不存在")
    profile = await db.scalar(select(UserProfile).where(UserProfile.user_id == target_id))
    wallet = await db.scalar(select(Wallet).where(Wallet.user_id == target_id))
    return {
        "id": user.id,
        "username": user.username,
        "role": user.role,
        "status": user.status,
        "real_auth_status": user.real_auth_status,
        "school": user.school,
        "nickname": profile.nickname if profile else None,
        "phone": profile.phone if profile else None,
        "email": profile.email if profile else None,
        "major": profile.major if profile else None,
        "bio": profile.bio if profile else None,
        "balance": to_yuan(wallet.balance) if wallet else 0.0,
        "total_recharged": to_yuan(wallet.total_recharged) if wallet else 0.0,
        "total_consumed": to_yuan(wallet.total_consumed) if wallet else 0.0,
        "created_at": str(user.created_at),
        "updated_at": str(user.updated_at),
    }


async def update_user(db: AsyncSession, target_id: int, payload, operator: User) -> User:
    """管理员编辑用户:角色/实名状态/学校写到 users,昵称/手机/邮箱写到 user_profiles。"""
    user = await db.get(User, target_id)
    if user is None:
        raise APIError(404, "用户不存在")
    if user.id == operator.id and payload.role is not None and payload.role != "admin":
        raise APIError(400, "不能通过此操作降级自己的账号")
    data = payload.model_dump(exclude_unset=True)
    for key in ("role", "real_auth_status", "school"):
        if key in data and data[key] is not None:
            setattr(user, key, data.pop(key))
    profile = await db.scalar(select(UserProfile).where(UserProfile.user_id == target_id))
    profile_changed = {k: v for k, v in data.items() if v is not None}
    if profile_changed:
        if profile is None:
            profile = UserProfile(user_id=target_id)
            db.add(profile)
        for key, value in profile_changed.items():
            setattr(profile, key, value)
    await db.commit()
    await db.refresh(user)
    return user


async def adjust_balance(
    db: AsyncSession, target_id: int, amount: int, reason: str | None, operator: User
) -> Wallet:
    """管理员调整余额(元):正数增加,负数扣减(不允许扣成负数);账本按微元记账。"""
    amount = to_micro(amount)
    if amount == 0:
        raise APIError(400, "调整额不能为 0")
    user = await db.get(User, target_id)
    if user is None:
        raise APIError(404, "用户不存在")
    if user.status == -1:
        raise APIError(400, "该用户已删除(软删),不能调整余额")
    wallet = await db.scalar(select(Wallet).where(Wallet.user_id == target_id))
    if wallet is None:
        wallet = Wallet(user_id=target_id, balance=0, total_recharged=0, total_consumed=0)
        db.add(wallet)
        await db.flush()
    if amount < 0 and wallet.balance + amount < 0:
        raise APIError(400, f"扣减后余额不能为负,当前余额 {to_yuan(wallet.balance)} 元")
    wallet.balance += amount
    db.add(OperationLog(
        user_id=operator.id,
        action="admin.adjust_balance",
        resource_type="wallet",
        resource_id=target_id,
        detail_json={"amount": amount, "reason": reason, "target_user": target_id},
    ))
    await db.commit()
    await db.refresh(wallet)
    return wallet


async def reset_password(db: AsyncSession, target_id: int, new_password: str, operator: User) -> User:
    """管理员重置密码。"""
    user = await db.get(User, target_id)
    if user is None:
        raise APIError(404, "用户不存在")
    user.password_hash = hash_password(new_password)
    db.add(OperationLog(
        user_id=operator.id,
        action="admin.reset_password",
        resource_type="user",
        resource_id=target_id,
        detail_json={"operator": operator.id},
    ))
    await db.commit()
    await db.refresh(user)
    return user


async def soft_delete_user(db: AsyncSession, target_id: int, operator: User) -> User:
    """软删除用户:status 置 -1(登录态立即失效),保留所有历史数据可追溯。"""
    user = await db.get(User, target_id)
    if user is None:
        raise APIError(404, "用户不存在")
    if user.id == operator.id:
        raise APIError(400, "不能删除自己的账号")
    if user.status == -1:
        raise APIError(400, "该用户已删除")
    user.status = -1
    await db.commit()
    await db.refresh(user)
    return user
