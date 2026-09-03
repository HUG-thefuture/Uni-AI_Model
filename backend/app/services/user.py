from sqlalchemy.ext.asyncio import AsyncSession
from app.core.response import APIError
from app.core.security import hash_password
from app.models import User, UserProfile, Wallet, OperationLog
from app.schemas.auth import profile_update_req
from sqlalchemy import select, func, or_


async def get_profile(db: AsyncSession, user_id: int):
    """获取用户资料；用户主表由鉴权依赖校验，资料缺失时返回空资料。"""
    profile = await db.scalar(select(UserProfile).where(UserProfile.user_id == user_id))
    if profile is None:
        raise APIError(404, "用户资料不存在")
    return profile


async def update_profile(
        db: AsyncSession,
        user_id: int,
        payload: profile_update_req,
):
    profile = await db.scalar(select(UserProfile).where(UserProfile.user_id == user_id))
    user = await db.get(User, user_id)
    if profile is None or user is None:
        raise APIError(404, "用户资料不存在")
    data = payload.model_dump(exclude_unset=True)
    school_provided = "school" in data
    school = data.pop("school", None)
    if school_provided:
        user.school = school
    for key, value in data.items():
        setattr(profile, key, value)
    await db.commit()
    await db.refresh(profile)
    return profile


async def list_users(
    db: AsyncSession,
    page: int,
    page_size: int,
    keyword: str | None = None,
    role: str | None = None,
    status: int | None = None,
    balance_min: int | None = None,
    balance_max: int | None = None,
    include_deleted: bool = False,
) -> tuple[int, list]:
    """管理员用户列表:分页 + 关键字/角色/状态/余额区间筛选。

    返回增强条目(含钱包余额、昵称、手机号等)。软删除(status=-1)默认排除,
    仅当显式筛选 status=-1 或 include_deleted=True 时才纳入。
    """
    conds = []
    if keyword:
        like = f"%{keyword}%"
        conds.append(or_(User.username.like(like), User.school.like(like)))
    if role:
        conds.append(User.role == role)
    if status is not None:
        conds.append(User.status == status)
    elif not include_deleted:
        # 默认排除软删除
        conds.append(User.status != -1)
    if balance_min is not None:
        conds.append(Wallet.balance >= balance_min)
    if balance_max is not None:
        conds.append(Wallet.balance <= balance_max)

    base = (
        select(User, Wallet, UserProfile)
        .outerjoin(Wallet, Wallet.user_id == User.id)
        .outerjoin(UserProfile, UserProfile.user_id == User.id)
        .where(*conds)
    )
    total = await db.scalar(
        select(func.count(User.id))
        .select_from(User)
        .outerjoin(Wallet, Wallet.user_id == User.id)
        .outerjoin(UserProfile, UserProfile.user_id == User.id)
        .where(*conds)
    ) or 0
    rows = (
        (await db.execute(
            base.order_by(User.id).offset((page - 1) * page_size).limit(page_size)
        )).all()
    )
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
            "balance": w.balance if w else 0,
            "total_recharged": w.total_recharged if w else 0,
            "total_consumed": w.total_consumed if w else 0,
            "created_at": str(u.created_at),
        }
        for u, w, p in rows
    ]
    return total, items


async def update_user_status(db: AsyncSession, target_id: int, status: int, operator: User) -> User:
    """启用/禁用用户;禁止操作自己。"""
    user = await db.get(User, target_id)
    if user is None:
        raise APIError(404, "用户不存在")
    if user.id == operator.id:
        raise APIError(400, "不能操作自己的账号")
    user.status = status
    await db.commit()
    await db.refresh(user)
    return user


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
        "balance": wallet.balance if wallet else 0,
        "total_recharged": wallet.total_recharged if wallet else 0,
        "total_consumed": wallet.total_consumed if wallet else 0,
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
    user_fields = {}
    for key in ("role", "real_auth_status", "school"):
        if key in data:
            user_fields[key] = data.pop(key)
    if user_fields:
        for key, value in user_fields.items():
            setattr(user, key, value)

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
    db: AsyncSession,
    target_id: int,
    amount: int,
    reason: str | None,
    operator: User,
) -> Wallet:
    """管理员调整余额:正数增加,负数扣减(不允许扣成负数)。"""
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
        raise APIError(400, f"扣减后余额不能为负,当前余额 {wallet.balance} 分")
    wallet.balance += amount  # 正数充值/补发,负数回收;不改动累计口径(那是真实充值/消费流水)
    # 审计日志
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
