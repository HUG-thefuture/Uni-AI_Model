from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from ..schemas.auth import User_out, Register_req, Login_req, Profile_res
from ..core.response import ok
from ..core.db import get_async_db
from ..core.deps import get_current_user
from ..core.security import decode_token
from ..core.token_blacklist import revoke
from ..services.pricing import to_yuan
from ..services import auth as auth_service
from ..models.user import User, UserProfile, Wallet
from sqlalchemy import select



router = APIRouter(
    prefix="/auth",
    tags=["用户管理模块"]
)

@router.post("/register", status_code=201)
async def register(user_req: Register_req,
                   db: AsyncSession = Depends(get_async_db)):
    user = await auth_service.register(db, user_req)
    return ok(User_out.model_validate(user).model_dump(mode="json"), http_status=201)

@router.post("/login")
async def login(user_req: Login_req,
                db: AsyncSession = Depends(get_async_db)):
    token, user = await auth_service.login(db, user_req)
    data = {"token": token, "user": User_out.model_validate(user).model_dump(mode="json")}
    return ok(data)

@router.post("/logout")
async def logout(request: Request, current_user: User = Depends(get_current_user)):
    """登出:把当前 Bearer token 拉黑至其自然过期(进程内黑名单)。"""
    auth_header = request.headers.get("Authorization") or ""
    token = auth_header[7:].strip() if auth_header.lower().startswith("bearer ") else ""
    if token:
        try:
            payload = decode_token(token)
            expires_at = payload.get("exp")
            if expires_at:
                revoke(token, float(expires_at))
        except Exception:  # noqa: BLE001 解析失败无需拉黑(token 本就无效)
            pass
    return ok({})


@router.get("/me")
async def me(current_user: User = Depends(get_current_user),
             db: AsyncSession = Depends(get_async_db)):
    profile = await db.scalar(select(UserProfile).where(UserProfile.user_id == current_user.id))
    wallet = await db.get(Wallet,current_user.id)
    data = User_out.model_validate(current_user).model_dump(mode="json")
    data["profile"] = Profile_res.model_validate(profile).model_dump(mode="json") if profile else {}
    # 账本微元 → 元(登录/个人信息响应内嵌钱包)
    data["wallet"] = ({
        "balance": to_yuan(wallet.balance),
        "total_recharged": to_yuan(wallet.total_recharged),
        "total_consumed": to_yuan(wallet.total_consumed),
    } if wallet else {})
    return ok(data)
