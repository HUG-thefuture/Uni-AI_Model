"""模型广场与模型管理业务逻辑(WP03,WP08 增强)。

- 门户列表仅返回 status=enabled,且不暴露 endpoint 与 config_json;
  WP08:每项增加 available 字段(local 模型轻量探活 Ollama,60s 缓存;
  online/mock 恒 True 不做真实探活,避免拖慢列表);
- 管理端全量分页(含 disabled),创建/更新校验 model_code+provider_type 唯一;
  WP08:详情增加 daily_stats(近 7 天逐日调用量)与 error_stats(错误分布 top10);
- 删除前置校验:存在 status IN (pending, processing) 的 ai_tasks 引用则 409 拒绝;
- 写操作统一写 operation_logs(user_id / action / resource_type="models" / detail_json)。
"""
import json
from datetime import datetime, timedelta

from sqlalchemy import case, func, or_
from sqlalchemy.orm import Query, Session

from app.core.response import APIError
from app.models.ai_call_log import AiCallLog
from app.models.ai_task import AiTask
from app.models.model import Model
from app.models.support import OperationLog

# 全组冻结的合法枚举值
VALID_PROVIDER_TYPES = ("online", "local")
VALID_MODEL_TYPES = ("text", "image", "audio", "video")
VALID_VENDORS = ("siliconflow", "ollama", "mock")
VALID_STATUSES = ("enabled", "disabled")

# 删除前置校验:引用模型且尚未结束的任务状态
BLOCKING_TASK_STATUSES = ("pending", "processing")


# ---------------------------------------------------------------------------
# 校验与序列化助手
# ---------------------------------------------------------------------------
def _validate_enums(
    provider_type: str | None = None,
    model_type: str | None = None,
    vendor: str | None = None,
) -> None:
    """枚举合法性校验,非法返回 400(中文提示)。"""
    if provider_type is not None and provider_type not in VALID_PROVIDER_TYPES:
        raise APIError(400, "provider_type 非法,仅支持 online/local")
    if model_type is not None and model_type not in VALID_MODEL_TYPES:
        raise APIError(400, "model_type 非法,仅支持 text/image/audio/video")
    if vendor is not None and vendor not in VALID_VENDORS:
        raise APIError(400, "vendor 非法,仅支持 siliconflow/ollama/mock")


def _normalize_config_json(config_json) -> str | None:
    """config_json 统一存为 JSON 字符串:对象则序列化,字符串校验合法性,空值归 None。"""
    if config_json is None:
        return None
    if isinstance(config_json, dict):
        return json.dumps(config_json, ensure_ascii=False)
    if isinstance(config_json, str):
        text = config_json.strip()
        if not text:
            return None
        try:
            json.loads(text)
        except json.JSONDecodeError:
            raise APIError(400, "config_json 不是合法的 JSON 字符串")
        return text
    raise APIError(400, "config_json 仅支持对象或 JSON 字符串")


def _ensure_unique(db: Session, model_code: str, provider_type: str,
                   exclude_id: int | None = None) -> None:
    """model_code+provider_type 唯一性校验,冲突 409「模型已存在」。"""
    query = db.query(Model).filter(
        Model.model_code == model_code, Model.provider_type == provider_type
    )
    if exclude_id is not None:
        query = query.filter(Model.id != exclude_id)
    if query.first() is not None:
        raise APIError(409, "模型已存在")


def _parse_config_json(raw: str | None):
    """输出 config_json:优先解析为对象,失败回退原字符串(空值 None)。"""
    if raw is None or raw == "":
        return None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return raw


def _model_available(model: Model) -> bool:
    """门户列表 available 字段(WP08):

    - local 模型:轻量探活 Ollama /api/tags(2s 超时,模块级缓存 60s),失败/超时
      一律 False 且异常全部吞掉,不阻塞列表返回;
    - online / mock 模型:恒 True —— 不做真实探活,避免对 siliconflow 的 HTTP 探测
      拖慢列表接口(mock 本就不发起外部请求,恒可用)。
    """
    if model.provider_type == "local":
        from app.providers.local import LocalProvider

        try:
            return LocalProvider.probe_available(model.endpoint)
        except Exception:  # noqa: BLE001 双保险:探活任何异常都不影响列表
            return False
    return True


def model_to_portal(model: Model) -> dict:
    """门户端条目:不含 endpoint 与 config_json,不暴露调用细节;available 为在线状态。"""
    return {
        "id": model.id,
        "name": model.name,
        "vendor": model.vendor,
        "provider_type": model.provider_type,
        "model_type": model.model_type,
        "description": model.description,
        "capability_tags": model.capability_tags,
        "price_per_call": model.price_per_call,
        "status": model.status,
        "available": _model_available(model),
    }


def model_to_admin(model: Model) -> dict:
    """管理端条目:全量字段,config_json 解析为对象输出。"""
    return {
        "id": model.id,
        "name": model.name,
        "model_code": model.model_code,
        "provider_type": model.provider_type,
        "model_type": model.model_type,
        "vendor": model.vendor,
        "endpoint": model.endpoint,
        "price_per_call": model.price_per_call,
        "max_duration_sec": model.max_duration_sec,
        "status": model.status,
        "config_json": _parse_config_json(model.config_json),
        "description": model.description,
        "capability_tags": model.capability_tags,
        "created_at": str(model.created_at) if model.created_at else None,
        "updated_at": str(model.updated_at) if model.updated_at else None,
    }


def _paginate(query: Query, page: int, page_size: int) -> dict:
    """统一分页结构 {total, page, page_size, items}。"""
    total = query.count()
    items = query.order_by(Model.id).offset((page - 1) * page_size).limit(page_size).all()
    return {"total": total, "page": page, "page_size": page_size, "items": items}


def _apply_filters(query: Query, category: str | None, model_type: str | None,
                   keyword: str | None) -> Query:
    """公共筛选:category→provider_type、type→model_type、keyword 模糊 name/description。"""
    if category:
        _validate_enums(provider_type=category)
        query = query.filter(Model.provider_type == category)
    if model_type:
        _validate_enums(model_type=model_type)
        query = query.filter(Model.model_type == model_type)
    if keyword:
        like = f"%{keyword}%"
        query = query.filter(or_(Model.name.like(like), Model.description.like(like)))
    return query


def _write_operation_log(db: Session, user_id: int, action: str,
                         resource_id: int | None, detail: dict) -> None:
    """写管理操作日志:detail_json 为变更内容 JSON 字符串(落库失败不影响主流程)。"""
    try:
        db.add(OperationLog(
            user_id=user_id,
            action=action,
            resource_type="models",
            resource_id=resource_id,
            detail_json=json.dumps(detail, ensure_ascii=False, default=str),
        ))
    except Exception:  # noqa: BLE001
        db.rollback()
        raise


# ---------------------------------------------------------------------------
# 门户端
# ---------------------------------------------------------------------------
def list_portal_models(
    db: Session,
    *,
    category: str | None = None,
    model_type: str | None = None,
    keyword: str | None = None,
    page: int = 1,
    page_size: int = 10,
) -> dict:
    """门户模型列表:仅 enabled,不暴露 endpoint/config_json。"""
    query = db.query(Model).filter(Model.status == "enabled")
    query = _apply_filters(query, category, model_type, keyword)
    result = _paginate(query, page, page_size)
    result["items"] = [model_to_portal(m) for m in result["items"]]
    return result


# ---------------------------------------------------------------------------
# 管理端
# ---------------------------------------------------------------------------
def list_admin_models(
    db: Session,
    *,
    category: str | None = None,
    model_type: str | None = None,
    keyword: str | None = None,
    page: int = 1,
    page_size: int = 10,
) -> dict:
    """管理端模型列表:全量分页(含 disabled)。"""
    query = db.query(Model)
    query = _apply_filters(query, category, model_type, keyword)
    result = _paginate(query, page, page_size)
    result["items"] = [model_to_admin(m) for m in result["items"]]
    return result


def create_model(db: Session, user_id: int, payload) -> Model:
    """创建模型:枚举校验 + 唯一校验 + 写操作日志。"""
    _validate_enums(provider_type=payload.provider_type, model_type=payload.model_type,
                    vendor=payload.vendor)
    _ensure_unique(db, payload.model_code, payload.provider_type)
    model = Model(
        name=payload.name,
        model_code=payload.model_code,
        provider_type=payload.provider_type,
        model_type=payload.model_type,
        vendor=payload.vendor,
        endpoint=payload.endpoint,
        price_per_call=payload.price_per_call,
        max_duration_sec=payload.max_duration_sec,
        description=payload.description,
        capability_tags=payload.capability_tags,
        config_json=_normalize_config_json(payload.config_json),
        status="enabled",
    )
    db.add(model)
    db.commit()
    db.refresh(model)
    _write_operation_log(db, user_id, "model_create", model.id,
                         {"name": model.name, "model_code": model.model_code,
                          "provider_type": model.provider_type})
    db.commit()
    return model


def _get_model_or_404(db: Session, model_id: int) -> Model:
    model = db.get(Model, model_id)
    if model is None:
        raise APIError(404, "模型不存在")
    return model


def update_model(db: Session, user_id: int, model_id: int, payload) -> Model:
    """部分更新:只修改请求体中出现的字段;唯一性冲突 409;不存在 404。"""
    model = _get_model_or_404(db, model_id)
    # 只处理显式传入的字段(exclude_unset),未传字段保持原值
    provided = payload.model_dump(exclude_unset=True)
    _validate_enums(provider_type=provided.get("provider_type"),
                    model_type=provided.get("model_type"),
                    vendor=provided.get("vendor"))
    if "config_json" in provided:
        provided["config_json"] = _normalize_config_json(provided["config_json"])
    else:
        provided.pop("config_json", None)

    new_code = provided.get("model_code", model.model_code)
    new_provider = provided.get("provider_type", model.provider_type)
    if new_code != model.model_code or new_provider != model.provider_type:
        _ensure_unique(db, new_code, new_provider, exclude_id=model.id)

    before = {k: getattr(model, k) for k in provided}
    for field, value in provided.items():
        setattr(model, field, value)
    db.commit()
    db.refresh(model)
    _write_operation_log(db, user_id, "model_update", model.id,
                         {"before": {k: (str(v) if isinstance(v, datetime) else v) for k, v in before.items()},
                          "after": {k: (str(v) if isinstance(v, datetime) else v) for k, v in provided.items()}})
    db.commit()
    return model


def update_model_status(db: Session, user_id: int, model_id: int, status: str) -> Model:
    """启用/停用:停用后门户列表立即不可见。"""
    if status not in VALID_STATUSES:
        raise APIError(400, "status 非法,仅支持 enabled/disabled")
    model = _get_model_or_404(db, model_id)
    if model.status == status:
        return model  # 幂等:状态一致直接返回
    old = model.status
    model.status = status
    db.commit()
    _write_operation_log(db, user_id, "model_status", model.id,
                         {"before": old, "after": status})
    db.commit()
    return model


def delete_model(db: Session, user_id: int, model_id: int) -> None:
    """物理删除:存在 pending/processing 任务引用则 409 拒绝。"""
    model = _get_model_or_404(db, model_id)
    blocking = (
        db.query(AiTask)
        .filter(AiTask.model_id == model_id, AiTask.status.in_(BLOCKING_TASK_STATUSES))
        .count()
    )
    if blocking > 0:
        raise APIError(409, f"该模型存在 {blocking} 个进行中的任务,禁止删除")
    detail = {"name": model.name, "model_code": model.model_code,
              "provider_type": model.provider_type}
    db.delete(model)
    db.commit()
    _write_operation_log(db, user_id, "model_delete", model_id, detail)
    db.commit()


def _daily_stats_7d(db: Session, model_id: int, since: datetime) -> list[dict]:
    """近 7 天逐日调用量:ai_call_logs 按 DATE(created_at) 聚合。

    func.date() 在 sqlite 与 MySQL 下均兼容;补齐无调用日期为 0,升序输出。
    """
    rows = (
        db.query(
            func.date(AiCallLog.created_at).label("day"),
            func.count(AiCallLog.id).label("total"),
            func.sum(case((AiCallLog.success.is_(True), 1), else_=0)).label("success"),
        )
        .filter(AiCallLog.model_id == model_id, AiCallLog.created_at >= since)
        .group_by(func.date(AiCallLog.created_at))
        .all()
    )
    by_day = {str(r.day): {"total": int(r.total), "success": int(r.success or 0)} for r in rows}
    stats: list[dict] = []
    for offset in range(6, -1, -1):  # 6 天前 → 今天,共 7 天
        day = (datetime.now() - timedelta(days=offset)).strftime("%Y-%m-%d")
        day_stat = by_day.get(day, {"total": 0, "success": 0})
        stats.append({"date": day, "total": day_stat["total"], "success": day_stat["success"]})
    return stats


def _error_stats_7d(db: Session, model_id: int, since: datetime) -> list[dict]:
    """最近错误分布:success=0 的记录按 error_code 计数,前 10,按次数倒序。"""
    rows = (
        db.query(AiCallLog.error_code, func.count(AiCallLog.id).label("count"))
        .filter(
            AiCallLog.model_id == model_id,
            AiCallLog.created_at >= since,
            AiCallLog.success.is_(False),
        )
        .group_by(AiCallLog.error_code)
        .order_by(func.count(AiCallLog.id).desc())
        .limit(10)
        .all()
    )
    return [{"error_code": r[0] or "unknown", "count": int(r[1])} for r in rows]


def get_model_detail(db: Session, model_id: int) -> dict:
    """管理端详情:全量字段 + 近 7 天调用量/成功率 + 逐日统计 + 错误分布(查 ai_call_logs)。"""
    model = _get_model_or_404(db, model_id)
    since = datetime.now() - timedelta(days=7)
    total = (
        db.query(AiCallLog)
        .filter(AiCallLog.model_id == model_id, AiCallLog.created_at >= since)
        .count()
    )
    success = (
        db.query(AiCallLog)
        .filter(AiCallLog.model_id == model_id,
                AiCallLog.created_at >= since,
                AiCallLog.success.is_(True))
        .count()
    )
    success_rate = round(success / total, 4) if total > 0 else 0.0
    detail = model_to_admin(model)
    detail["call_stats_7d"] = {
        "total": total,
        "success": success,
        "success_rate": success_rate,
    }
    detail["daily_stats"] = _daily_stats_7d(db, model_id, since)
    detail["error_stats"] = _error_stats_7d(db, model_id, since)
    return detail
