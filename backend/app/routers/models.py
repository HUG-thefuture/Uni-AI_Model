"""门户端模型广场路由(WP03,WP08 增强)。

- GET /models:需登录(get_current_user),仅返回 enabled 模型,
  不暴露 endpoint 与 config_json;
  WP08:每项透传 available 字段(local 模型轻量探活 + 60s 缓存,逻辑在
  services/model_service.model_to_portal,路由层只透传);
- 路径不写 /api 前缀(main.py 统一挂载 /api 与 /api/v1)。
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.db import get_db
from app.core.response import ok
from app.services import model_service

router = APIRouter(tags=["models"])


@router.get("/models")
def list_models(
    category: str | None = Query(default=None, description="类别筛选:online/local"),
    model_type: str | None = Query(default=None, alias="type",
                                   description="模型类型:text/image/audio/video"),
    keyword: str | None = Query(default=None, max_length=100,
                                description="关键字,模糊匹配 name/description"),
    page: int = Query(default=1, ge=1, description="页码,默认 1"),
    page_size: int = Query(default=10, ge=1, le=100, description="每页条数,默认 10 最大 100"),
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """模型广场列表(需登录):仅 enabled,分页 {total, page, page_size, items}。"""
    data = model_service.list_portal_models(
        db, category=category, model_type=model_type, keyword=keyword,
        page=page, page_size=page_size,
    )
    return ok(data=data)
