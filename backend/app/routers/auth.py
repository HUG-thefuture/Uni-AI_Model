from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.schemas.auth import User_out, Register_req
from app.core.response import ok
from app.core.db import get_async_db
from app.services import auth as auth_service

router = APIRouter(
    prefix="/auth",
    tags=["用户管理模块"]
)

@router.post("/register", status_code=201)
async def register(user_req: Register_req, db: AsyncSession = Depends(get_async_db)):
    user = await auth_service.register(db, user_req)
    return ok(User_out.model_validate(user).model_dump(mode="json"), http_status=201)
