"""开放平台路由(WP06):API Key 鉴权 + OpenAI 兼容对话接口。

- 路径不含 /api 前缀,main.py 统一挂 /api 与 /api/v1;
  叠加别名 /v1/chat/completions,使 /api/v1/chat/completions 亦可调用;
- 本路由直接返回 OpenAI 兼容结构(不包统一响应壳),仅鉴权/限流等失败走 APIError 统一结构;
- 扣费铁律:预扣冻结 → 调用 → 成功结算 → 失败释放,失败一律不扣费;
- 每次调用写 ai_call_logs(Provider 层)与 api_usage_logs(Key 维度统计);
- SSE 生成器内不使用请求级 db(可能已关闭),自建 app.core.db.SessionLocal();
- 异步上下文中的落库经 app.core.db.run_db 放线程池执行,断连收尾(CancelledError/
  GeneratorExit 分支)保持同步直调,避免二次取消丢失收尾。
"""
import asyncio
import json
import logging
import time
from typing import AsyncIterator

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.api_key_auth import require_api_key
from app.core.config import get_settings
from app.core.db import SessionLocal, get_db, run_db
from app.core.request_id import current_request_id
from app.core.response import APIError
from app.models.ai_call_log import AiCallLog
from app.models.ai_task import AiTask
from app.models.model import Model
from app.models.support import ApiUsageLog, User
from app.providers.factory import get_provider
from app.services import billing
from app.services.rate_limiter import rate_limiter

logger = logging.getLogger("app.openapi")

router = APIRouter(tags=["openapi"])


# ---------- 请求体(OpenAI 兼容子集) ----------

class OpenAIChatMessage(BaseModel):
    role: str
    content: str


class OpenAIChatBody(BaseModel):
    model: str
    messages: list[OpenAIChatMessage]
    stream: bool = False
    max_tokens: int | None = None
    temperature: float | None = None


# ---------- 工具 ----------

def _sse(payload: dict) -> str:
    """SSE 单帧:`data: {json}\\n\\n`。"""
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _estimate_tokens(text: str) -> int:
    """无 usage 时按字符数粗略估算(中英混合约 2 字符/token)。"""
    return max(1, len(text or "") // 2)


def _build_params(body: OpenAIChatBody) -> dict:
    params: dict = {}
    if body.temperature is not None:
        params["temperature"] = body.temperature
    if body.max_tokens is not None:
        params["max_tokens"] = body.max_tokens
    return params


def _write_call_log(db: Session, *, request_id: str, user_id: int | None, model_id: int | None,
                    vendor: str, start: float, success: bool, error_code: str | None) -> None:
    """ai_call_logs 落库:失败不影响主流程。"""
    try:
        db.add(AiCallLog(
            request_id=request_id, user_id=user_id, model_id=model_id, provider=vendor,
            latency_ms=int((time.monotonic() - start) * 1000), success=success,
            error_code=error_code,
        ))
        db.commit()
    except Exception:  # noqa: BLE001
        db.rollback()
        logger.exception("ai_call_logs 落库失败(request_id=%s)", request_id)


def _write_usage_log(db: Session, *, key_id: int | None, user_id: int | None, path: str,
                     model_id: int | None, status_code: int, latency_ms: int) -> None:
    """api_usage_logs 落库(Key 维度统计):失败不影响主流程。"""
    try:
        db.add(ApiUsageLog(
            key_id=key_id, user_id=user_id, path=path[:200], model_id=model_id,
            status_code=status_code, latency_ms=latency_ms,
        ))
        db.commit()
    except Exception:  # noqa: BLE001
        db.rollback()
        logger.exception("api_usage_logs 落库失败(key_id=%s)", key_id)


def _mark_task_failed(db: Session, task: AiTask | None, user_id: int, cost: int,
                      error_message: str) -> None:
    """失败释放:冻结退回、任务 failed(cost=0、cost_status=refunded)。"""
    if task is not None:
        if task.cost_status == "frozen" and cost:
            billing.refund(db, user_id, cost, task_id=task.id)
            task.cost = 0
            task.cost_status = "refunded"
        task.status = "failed"
        task.error_message = error_message[:500]
    db.commit()


def _get_text_model_by_code(db: Session, model_code: str) -> Model:
    """按 model_code 取文本模型:404 / 维护中 409。"""
    model = db.query(Model).filter(Model.model_code == model_code).one_or_none()
    if model is None or model.model_type != "text":
        raise APIError(404, "模型不存在")
    if model.status != "enabled":
        raise APIError(409, "模型维护中,暂不可调用")
    return model


def _create_openai_task(db: Session, *, request_id: str, user_id: int, model: Model,
                        prompt: str, params: dict, cost: int) -> AiTask:
    """建任务 + 预扣冻结(freeze 失败抛 409 时任务未提交,自动丢弃)。"""
    task = AiTask(
        request_id=request_id, user_id=user_id, model_id=model.id, task_type="text",
        prompt=prompt, params_json=json.dumps(params, ensure_ascii=False) if params else None,
        status="processing", cost_status="frozen", cost=cost,
    )
    db.add(task)
    db.flush()
    billing.freeze(db, user_id, cost, task_id=task.id)
    db.commit()
    return task


def _finish_success(db: Session, *, task: AiTask, key_id: int, api_key_id: int | None,
                    path: str, model: Model, vendor: str, request_id: str,
                    start: float, content: str, cost: int) -> None:
    """成功结算:任务 succeeded + settle + ai_call_logs/api_usage_logs 落库。"""
    latency_ms = int((time.monotonic() - start) * 1000)
    task.status = "succeeded"
    task.result_text = content
    task.cost_status = "settled"
    task.latency_ms = latency_ms
    db.commit()
    billing.settle(db, key_id, cost, task_id=task.id, model_id=model.id)
    db.commit()
    _write_call_log(db, request_id=request_id, user_id=key_id, model_id=model.id,
                    vendor=vendor, start=start, success=True, error_code=None)
    _write_usage_log(db, key_id=api_key_id, user_id=key_id, path=path,
                     model_id=model.id, status_code=200, latency_ms=latency_ms)


def _finish_failure(db: Session, *, task_id: int, key_id: int, api_key_id: int | None,
                    path: str, model_id: int | None, vendor: str, request_id: str,
                    start: float, cost: int, message: str, error_code: str) -> None:
    """失败收尾:释放冻结、任务 failed + 日志落库(不扣费)。"""
    latency_ms = int((time.monotonic() - start) * 1000)
    _mark_task_failed(db, db.get(AiTask, task_id), key_id, cost, message)
    _write_call_log(db, request_id=request_id, user_id=key_id, model_id=model_id,
                    vendor=vendor, start=start, success=False, error_code=str(error_code))
    _write_usage_log(db, key_id=api_key_id, user_id=key_id, path=path, model_id=model_id,
                     status_code=502, latency_ms=latency_ms)


async def _generate_once(provider, model, messages: list[dict], params: dict) -> dict:
    """非流式调用:优先 generate_text_once;Mock 等未实现时聚合流式结果。

    返回 {"content": str, "usage": {...}}。
    """
    if hasattr(provider, "generate_text_once"):
        result = await provider.generate_text_once(model, messages, params)
        return {"content": result.get("content", ""), "usage": result.get("usage") or {}}
    reply: list[str] = []
    usage: dict = {}
    async for chunk in provider.generate_text(model, messages, params):
        if chunk.get("done"):
            usage = chunk.get("usage") or {}
            break
        if chunk.get("delta"):
            reply.append(chunk["delta"])
    return {"content": "".join(reply), "usage": usage}


# ---------- 路由 ----------

@router.post("/chat/completions")
@router.post("/v1/chat/completions")  # OpenAI 风格别名:/api/v1/chat/completions
async def chat_completions(
    request: Request,
    body: OpenAIChatBody,
    key: User = Depends(require_api_key),
    db: Session = Depends(get_db),
):
    """OpenAI 兼容对话接口(Key 鉴权 + 限流 + 冻结/结算/释放扣费铁律)。"""
    # 限流:单 Key 每分钟窗口计数
    if not await rate_limiter.check(request.state.api_key_id):
        raise APIError(429, "请求过于频繁,请稍后重试")

    # 模型校验:按 model_code(DB 操作经 run_db 放线程池,不阻塞事件循环)
    model = await run_db(_get_text_model_by_code, db, body.model)

    messages = [{"role": m.role, "content": m.content} for m in body.messages]
    prompt = next((m["content"] for m in reversed(messages) if m.get("role") == "user"), "")
    params = _build_params(body)
    cost = int(model.price_per_call or 0)
    request_id = current_request_id()
    chatcmpl_id = f"chatcmpl-{request_id}"
    start = time.monotonic()

    task = await run_db(
        _create_openai_task, db, request_id=request_id, user_id=key.id,
        model=model, prompt=prompt, params=params, cost=cost,
    )

    # ---------- 非流式 ----------
    if not body.stream:
        provider = get_provider(model)
        try:
            async with asyncio.timeout(get_settings().sse_total_timeout):
                result = await _generate_once(provider, model, messages, params)
        except Exception as exc:  # noqa: BLE001 含 ProviderError / 超时
            is_timeout = isinstance(exc, TimeoutError)
            error_code = getattr(exc, "code", None) or (
                "provider_timeout" if is_timeout else "internal_error"
            )
            message = "生成超时,本次不扣费" if is_timeout else "生成失败,本次不扣费"
            await run_db(
                _finish_failure, db, task_id=task.id, key_id=key.id,
                api_key_id=request.state.api_key_id, path=request.url.path,
                model_id=model.id, vendor=provider.vendor, request_id=request_id,
                start=start, cost=cost, message=message, error_code=str(error_code),
            )
            raise APIError(502, "生成失败,本次不扣费")

        content = result["content"]
        usage = result.get("usage") or {}
        prompt_tokens = int(usage.get("prompt_tokens") or _estimate_tokens(prompt))
        completion_tokens = int(usage.get("completion_tokens") or _estimate_tokens(content))
        latency_ms = int((time.monotonic() - start) * 1000)

        await run_db(
            _finish_success, db, task=task, key_id=key.id,
            api_key_id=request.state.api_key_id, path=request.url.path,
            model=model, vendor=provider.vendor, request_id=request_id,
            start=start, content=content, cost=cost,
        )
        return {
            "id": chatcmpl_id,
            "object": "chat.completion",
            "created": int(time.time()),
            "model": model.model_code,
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }],
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
            },
        }

    # ---------- 流式 ----------
    provider = get_provider(model)

    async def stream_gen() -> AsyncIterator[str]:
        # SSE 生成器生命周期长于请求,自建会话,不用请求级 db;
        # 落库经 run_db 放线程池;断连(CancelledError/GeneratorExit)分支保持同步直调
        sdb = SessionLocal()
        gen_start = time.monotonic()
        reply: list[str] = []
        usage: dict = {}
        success = False
        error_code: str | None = None
        try:
            async with asyncio.timeout(get_settings().sse_total_timeout):
                async for chunk in provider.generate_text(model, messages, params):
                    if chunk.get("done"):
                        usage = chunk.get("usage") or {}
                        break
                    delta = chunk.get("delta") or ""
                    if delta:
                        reply.append(delta)
                        yield _sse({
                            "id": chatcmpl_id, "object": "chat.completion.chunk",
                            "model": model.model_code,
                            "choices": [{"index": 0, "delta": {"content": delta}}],
                        })

            text = "".join(reply)
            stask = await run_db(sdb.get, AiTask, task.id)
            await run_db(
                _finish_success, sdb, task=stask, key_id=key.id,
                api_key_id=request.state.api_key_id, path=request.url.path,
                model=model, vendor=provider.vendor, request_id=request_id,
                start=gen_start, content=text, cost=cost,
            )
            success = True
            yield _sse({
                "id": chatcmpl_id, "object": "chat.completion.chunk",
                "model": model.model_code,
                "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
            })
            yield "data: [DONE]\n\n"
        except (asyncio.CancelledError, GeneratorExit):
            # 客户端断连:按失败处理(不扣费),不可再 yield;
            # 取消路径内不再 await(二次取消会丢失收尾),保持同步直调
            _mark_task_failed(sdb, sdb.get(AiTask, task.id), key.id, cost, "生成中断,本次不扣费")
            _write_call_log(sdb, request_id=request_id, user_id=key.id, model_id=model.id,
                            vendor=provider.vendor, start=gen_start, success=False,
                            error_code="client_disconnected")
            _write_usage_log(sdb, key_id=request.state.api_key_id, user_id=key.id,
                             path=request.url.path, model_id=model.id, status_code=502,
                             latency_ms=int((time.monotonic() - gen_start) * 1000))
            raise
        except Exception as exc:  # noqa: BLE001 含 ProviderError / 超时
            is_timeout = isinstance(exc, TimeoutError)
            error_code = str(getattr(exc, "code", None) or (
                "provider_timeout" if is_timeout else "internal_error"
            ))
            message = "生成超时,本次不扣费" if is_timeout else "生成失败,本次不扣费"
            await run_db(
                _finish_failure, sdb, task_id=task.id, key_id=key.id,
                api_key_id=request.state.api_key_id, path=request.url.path,
                model_id=model.id, vendor=provider.vendor, request_id=request_id,
                start=gen_start, cost=cost, message=message, error_code=error_code,
            )
            yield _sse({"error": {"message": "生成失败,本次不扣费"}})
            yield "data: [DONE]\n\n"
        finally:
            sdb.close()

    return StreamingResponse(
        stream_gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
