from fastapi import APIRouter,Depends
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.core.db import get_db

router = APIRouter(
    prefix="/auth",
    tags=["用户管理模块"]
)

@router.post("/register")
async def register(request: Request,db:AsyncSession=Depends(get_db)):
