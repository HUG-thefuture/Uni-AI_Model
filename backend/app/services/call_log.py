"""调用日志:每次 Provider 调用统一记录到 ai_call_logs(排障与统计依据)。

用法(在路由/服务层包裹一次 Provider 调用):

    log_id, error = await log_provider_call(
        db, request_id=..., user_id=..., model=model, provider=provider,
        func=lambda: provider.generate_text_once(model, messages),
    )
"""
import logging
import time
from typing import Any, Awaitable, Callable

from sqlalchemy.orm import Session

from app.core.db import run_db
from app.models.ai_call_log import AiCallLog
from app.providers.exceptions import ProviderError

logger = logging.getLogger("app.call_log")


def _write_log(db: Session, *, request_id: str, user_id: int | None, model, provider,
               latency_ms: int, success: bool, error_code: str | None) -> None:
    try:
        db.add(
            AiCallLog(
                request_id=request_id,
                user_id=user_id,
                model_id=getattr(model, "id", None),
                provider=getattr(provider, "vendor", "unknown"),
                latency_ms=latency_ms,
                success=success,
                error_code=error_code,
            )
        )
        db.commit()
    except Exception:  # noqa: BLE001 日志失败不影响主流程
        db.rollback()
        logger.exception("ai_call_logs 落库失败(request_id=%s)", request_id)


async def log_provider_call(
    db: Session,
    *,
    request_id: str,
    model,
    provider,
    func: Callable[[], Awaitable[Any]],
    user_id: int | None = None,
) -> tuple[Any, ProviderError | None]:
    """执行一次 Provider 调用并落库 ai_call_logs。

    返回 (result, error):成功时 error 为 None;失败时 result 为 None 且错误已落库,
    由调用方决定如何转换为统一响应(路由层负责)。
    """
    start = time.monotonic()
    result: Any = None
    error: ProviderError | None = None
    try:
        result = await func()
        return result, None
    except ProviderError as exc:
        error = exc
        raise
    except Exception as exc:  # noqa: BLE001
        error = ProviderError("provider_unknown", "模型服务调用失败,请稍后重试", str(exc))
        raise error from exc
    finally:
        latency_ms = int((time.monotonic() - start) * 1000)
        # 落库放线程池,不阻塞事件循环;失败已在 _write_log 内吞掉
        await run_db(_write_log, db, request_id=request_id, user_id=user_id,
                     model=model, provider=provider, latency_ms=latency_ms,
                     success=error is None,
                     error_code=error.code if error else None)
