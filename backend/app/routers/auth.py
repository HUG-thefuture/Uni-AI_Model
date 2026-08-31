from fastapi import APIRouter,Depends
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status
from backend.app.services import register as services_register
from backend.app.core.db import get_db
from backend.app.schemas.auth import Register_req

router = APIRouter(
    prefix="/auth",
    tags=["用户管理模块"]
)

@router.post("/register",status_code=201)
async def register(user_req: Register_req,db:AsyncSession=Depends(get_db)):
    user=await services_register()
