"""API Key 管理路由:创建 / 列表 / 停用启用 / 删除。

- 路径不含 /api 前缀,main.py 统一挂 settings.api_prefix;
- 全部返回统一响应壳 ok()({"code":0,...,"data":...}),前端 request() 依赖 code=0 判定成功;
- 明文 Key 仅在创建响应出现一次,库内只存 sha256 哈希与前缀。
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.response import APIError, ok
from ..services import api_key
from ..core.db import get_async_db
from ..core.deps import get_current_user
from ..schemas.api_key import ApiKeyCreate, ApiKeyCreateResponse, ApiKeyListResponse, ApiKeyStatusUpdate

router = APIRouter(
    prefix="/api_keys",
    tags=["api_key管理"]
)


@router.post("")
@router.post("/")  # 兼容带尾斜杠路径,避免 307 重定向
async def create_api_key(data: ApiKeyCreate, db: AsyncSession = Depends(get_async_db), current_user=Depends(get_current_user)):
    """创建 API Key:明文仅本次响应返回。"""
    stmts = await api_key.create_api_keys(db, current_user.id, data.name)
    return ok(ApiKeyCreateResponse(
        id=stmts.id,
        name=stmts.name,
        key=stmts._raw_key,
        created_at=stmts.created_at,
    ).model_dump(mode="json"))


@router.get("")
@router.get("/")
async def get_api_keys(current_user=Depends(get_current_user), db: AsyncSession = Depends(get_async_db)):
    """我的 Key 列表(不含明文)。"""
    stmt = await api_key.get_api_keys(db, current_user.id)
    return ok([ApiKeyListResponse.model_validate(k).model_dump(mode="json") for k in stmt])


@router.put("/{id}/status")
async def update_api_key_status(id: int, data: ApiKeyStatusUpdate, current_user=Depends(get_current_user), db: AsyncSession = Depends(get_async_db)):
    """启用/停用 Key。"""
    stmt = await api_key.update_api_keys(db, current_user.id, id, data.status)
    if not stmt:
        raise APIError(404, "API Key 不存在或无权操作")
    return ok(ApiKeyListResponse.model_validate(stmt).model_dump(mode="json"))


@router.delete("/{id}")
async def delete_api_key(id: int, current_user=Depends(get_current_user), db: AsyncSession = Depends(get_async_db)):
    """删除 API Key(物理删除):该 Key 立即失效且不可恢复;他人 Key 一律 404。"""
    deleted = await api_key.delete_api_key(db, current_user.id, id)
    if not deleted:
        raise APIError(404, "API Key 不存在或无权操作")
    return ok({"id": id})
