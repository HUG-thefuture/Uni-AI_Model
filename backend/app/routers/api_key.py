from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.response import APIError
from app.services import api_key
from app.core.db import get_db
from app.models.user import get_current_user
from app.schemas.api_key import ApiKeyCreate,ApiKeyCreateResponse, ApiKeyListResponse, ApiKeyStatusUpdate

router = APIRouter(
    prefix="/api/api_keys",
    tags=["api_key管理"]
)


@router.post("/", response_model=ApiKeyCreateResponse)
async def create_api_key(data:ApiKeyCreate,db:AsyncSession = Depends(get_db),current_user=Depends(get_current_user)):
    stmts=await api_key.create_api_keys(db,current_user.id,data.name)
    return {
        "id":stmts.id,
        "name":stmts.name,
        "key":stmts._raw_key,
        "created_at":stmts.created_at,
    }


@router.get("/", response_model=list[ApiKeyListResponse])
async def get_api_keys(current_user = Depends(get_current_user),db:AsyncSession = Depends(get_db)):
    stmt=await api_key.get_api_keys(db,current_user.id)
    return stmt

@router.put("/{id}/status", response_model=ApiKeyListResponse)
async def update_api_key_status(id:int,data:ApiKeyStatusUpdate,current_user=Depends(get_current_user),db:AsyncSession = Depends(get_db)):
    stmt=await api_key.update_api_keys(db,current_user.id,id,data.status)
    if not stmt:
        raise APIError(404,"API Key 不存在或无权操作")
    return stmt
