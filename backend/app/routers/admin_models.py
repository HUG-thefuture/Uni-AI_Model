"""管理端模型 CRUD 路由(WP03,全部 require_admin)。

- GET    /admin/models           全量分页(含 disabled),支持 keyword/category/type 筛选
- POST   /admin/models           创建(model_code+provider_type 唯一,冲突 409)
- GET    /admin/models/{id}      详情(含 config_json + 近 7 天调用量/成功率 +
                                daily_stats 逐日统计 + error_stats 错误分布,WP08)
- PUT    /admin/models/{id}      部分更新
- PUT    /admin/models/{id}/status  启用/停用
- DELETE /admin/models/{id}      物理删除(被进行中任务引用则 409)
- 写操作写 operation_logs(action: model_create/model_update/model_status/model_delete)。
路径不写 /api 前缀,由 main.py 统一挂载。
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import require_admin
from app.core.response import ok
from app.schemas.model import ModelCreateRequest, ModelStatusRequest, ModelUpdateRequest
from app.services import model_service

router = APIRouter(prefix="/admin", tags=["admin-models"])


@router.get("/models")
def list_models(
    category: str | None = Query(default=None, description="类别筛选:online/local"),
    model_type: str | None = Query(default=None, alias="type",
                                   description="模型类型:text/image/audio/video"),
    keyword: str | None = Query(default=None, max_length=100,
                                description="关键字,模糊匹配 name/description"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    admin=Depends(require_admin),
    db: Session = Depends(get_db),
):
    """模型管理列表:全量分页(含 disabled)。"""
    data = model_service.list_admin_models(
        db, category=category, model_type=model_type, keyword=keyword,
        page=page, page_size=page_size,
    )
    return ok(data=data)


@router.post("/models", status_code=201)
def create_model(
    payload: ModelCreateRequest,
    admin=Depends(require_admin),
    db: Session = Depends(get_db),
):
    """创建模型:枚举非法 400;model_code+provider_type 冲突 409「模型已存在」。"""
    model = model_service.create_model(db, admin.id, payload)
    return ok(data=model_service.model_to_admin(model), http_status=201)


@router.get("/models/{model_id}")
def get_model(
    model_id: int,
    admin=Depends(require_admin),
    db: Session = Depends(get_db),
):
    """模型详情:全量字段 + 近 7 天调用量/成功率 + 逐日统计 + 错误分布;不存在 404。"""
    return ok(data=model_service.get_model_detail(db, model_id))


@router.put("/models/{model_id}")
def update_model(
    model_id: int,
    payload: ModelUpdateRequest,
    admin=Depends(require_admin),
    db: Session = Depends(get_db),
):
    """部分更新:仅修改请求体中显式传入的字段;不存在 404;唯一冲突 409。"""
    model = model_service.update_model(db, admin.id, model_id, payload)
    return ok(data=model_service.model_to_admin(model))


@router.put("/models/{model_id}/status")
def update_model_status(
    model_id: int,
    payload: ModelStatusRequest,
    admin=Depends(require_admin),
    db: Session = Depends(get_db),
):
    """启用/停用:停用后门户列表立即不可见;不存在 404;非法值 400。"""
    model = model_service.update_model_status(db, admin.id, model_id, payload.status)
    return ok(data={"id": model.id, "status": model.status})


@router.delete("/models/{model_id}")
def delete_model(
    model_id: int,
    admin=Depends(require_admin),
    db: Session = Depends(get_db),
):
    """删除模型:存在 pending/processing 任务引用则 409;否则物理删除。"""
    model_service.delete_model(db, admin.id, model_id)
    return ok(data={"id": model_id})
