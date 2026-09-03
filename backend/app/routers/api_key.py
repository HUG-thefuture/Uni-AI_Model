from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.response import APIError, ok
from app.services import api_key
from app.core.db import get_async_db
from app.models.user import get_current_user
from app.schemas.api_key import ApiKeyCreate,ApiKeyCreateResponse, ApiKeyListResponse, ApiKeyStatusUpdate

router = APIRouter(
    prefix="/api_keys",
    tags=["api_key管理"]
)


@router.post("")
async def create_api_key(data:ApiKeyCreate,db:AsyncSession = Depends(get_async_db),current_user=Depends(get_current_user)):
    stmts=await api_key.create_api_keys(db,current_user.id,data.name)
    return ok(ApiKeyCreateResponse(
        id=stmts.id,
        name=stmts.name,
        key=stmts._raw_key,
        created_at=stmts.created_at,
    ).model_dump(mode="json"))


@router.get("")
async def get_api_keys(current_user = Depends(get_current_user),db:AsyncSession = Depends(get_async_db)):
    keys=await api_key.get_api_keys(db,current_user.id)
    return ok([ApiKeyListResponse.model_validate(item).model_dump(mode="json") for item in keys])

@router.put("/{id}/status")
async def update_api_key_status(id:int,data:ApiKeyStatusUpdate,current_user=Depends(get_current_user),db:AsyncSession = Depends(get_async_db)):
    stmt=await api_key.update_api_keys(db,current_user.id,id,data.status)
    if not stmt:
        raise APIError(404,"API Key 不存在或无权操作")
    return ok(ApiKeyListResponse.model_validate(stmt).model_dump(mode="json"))
