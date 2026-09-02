from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.schemas.auth import User_out, Register_req, Login_req, Profile_res
from app.core.response import ok
from app.core.db import get_db
from app.schemas.wallet import WalletResponse
from app.services import auth as auth_service
from app.models.user import User, get_current_user, UserProfile,Wallet
from sqlalchemy import select
from app.core.response import APIError
from app.core.security import create_access_token, hash_password, verify_password



router = APIRouter(
    prefix="/auth",
    tags=["用户管理模块"]
)

@router.post("/register", status_code=201)
def register(user_req: Register_req,
             db: Session = Depends(get_db)):
    if db.query(User.id).filter(User.username == user_req.username).first() is not None:
        raise APIError(409, "用户名已存在")
    user = User(username=user_req.username, password_hash=hash_password(user_req.password),
                role="user", status=1, real_auth_status=0, school=user_req.school)
    db.add(user)
    db.flush()
    db.add_all([UserProfile(user_id=user.id, nickname=user_req.nickname or user_req.username),
                Wallet(user_id=user.id, balance=0, total_recharged=0, total_consumed=0)])
    db.commit()
    db.refresh(user)
    return ok(User_out.model_validate(user).model_dump(mode="json"), http_status=201)

@router.post("/login")
def login(user_req: Login_req,
          db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == user_req.username).first()
    if user is None or not verify_password(user_req.password, user.password_hash):
        raise APIError(401, "用户名或密码错误")
    if user.status != 1:
        raise APIError(403, "账号已被禁用")
    token = create_access_token(user.id, user.role)
    data = {"token": token, "user": User_out.model_validate(user).model_dump(mode="json")}
    return ok(data)

@router.post("/logout")
async def loginout(current_user: User = Depends(get_current_user)):
    return ok({})


@router.get("/me")
def me(current_user: User = Depends(get_current_user),
       db: Session = Depends(get_db)):
    profile = db.query(UserProfile).filter(UserProfile.user_id == current_user.id).first()
    wallet = db.get(Wallet, current_user.id)
    data = User_out.model_validate(current_user).model_dump(mode="json")
    data["profile"] = Profile_res.model_validate(profile).model_dump(mode="json") if profile else {}
    data["wallet"] = WalletResponse.model_validate(wallet).model_dump(mode="json") if wallet else {}
    return ok(data)
