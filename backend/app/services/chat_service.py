"""会话与消息服务(WP04):会话 CRUD、历史上下文、SSE 流式文本回复。

约定:
- 会话标题:创建时「新会话」,首条消息落库后更新为前 20 字;
- 历史上下文:取最近 20 条消息按时间正序拼 messages;
- 流式回复:逐段透传 Provider 的 AsyncIterator,禁止攒整段;
- 扣费铁律:路由层已冻结 → 成功结算 / 失败释放(超时、断连、异常一律不扣费);
- 每次调用在 finally 中写 ai_call_logs(流式不便包 log_provider_call,手动落库)。
"""
import asyncio
import json
import logging
import time
from typing import AsyncIterator

from sqlalchemy.orm import Session

from ..core.config import get_settings
from ..core.db import SessionLocal, run_db
from ..core.response import APIError
from ..models.ai_call_log import AiCallLog
from ..models.ai_task import AiTask
from ..models.model import Model
from ..models.support import ChatMessage, ChatSession
from ..providers.exceptions import ProviderError
from ..providers.factory import get_provider
from ..services import billing, pricing

logger = logging.getLogger("app.chat")

HISTORY_LIMIT = 20  # 历史上下文条数上限


# ---------- 会话与消息 ----------

def get_enabled_model(db: Session, model_id: int) -> Model:
    """模型存在且 enabled,否则 404 / 409「模型维护中,暂不可调用」。"""
    model = db.get(Model, model_id)
    if model is None:
        raise APIError(404, "模型不存在")
    if model.status != "enabled":
        raise APIError(409, "模型维护中,暂不可调用")
    return model


def get_owned_session(db: Session, user_id: int, session_id: int) -> ChatSession:
    """会话存在且归属当前用户,否则 404 / 403。"""
    session = db.get(ChatSession, session_id)
    if session is None:
        raise APIError(404, "会话不存在")
    if session.user_id != user_id:
        raise APIError(403, "无权限访问该会话")
    return session


def create_session(db: Session, user_id: int, model: Model) -> ChatSession:
    session = ChatSession(user_id=user_id, title="新会话", model_id=model.id)
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def list_sessions(db: Session, user_id: int, page: int, page_size: int) -> tuple[int, list[ChatSession]]:
    """我的会话,按 updated_at 倒序分页。"""
    q = (
        db.query(ChatSession)
        .filter(ChatSession.user_id == user_id)
        .order_by(ChatSession.updated_at.desc(), ChatSession.id.desc())
    )
    total = q.count()
    rows = q.offset((page - 1) * page_size).limit(page_size).all()
    return total, rows


def list_messages(db: Session, session_id: int) -> list[ChatMessage]:
    """历史消息,按 created_at(同秒用 id 兜底)正序。"""
    return (
        db.query(ChatMessage)
        .filter(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.asc(), ChatMessage.id.asc())
        .all()
    )


def recent_messages(db: Session, session_id: int, limit: int = HISTORY_LIMIT) -> list[dict]:
    """最近 limit 条消息(含刚写入的用户消息),转成 OpenAI 兼容 messages,正序。"""
    rows = (
        db.query(ChatMessage)
        .filter(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.id.desc())
        .limit(limit)
        .all()
    )
    rows.reverse()
    return [{"role": r.role, "content": r.content} for r in rows]


def add_user_message(db: Session, session: ChatSession, content: str, model_id: int) -> None:
    """写 user 消息;首条消息更新会话标题为前 20 字。"""
    first = db.query(ChatMessage).filter(ChatMessage.session_id == session.id).count() == 0
    db.add(ChatMessage(session_id=session.id, role="user", content=content, model_id=model_id))
    if first:
        session.title = (content or "").strip()[:20] or "新会话"


def estimate_tokens(prompt: str, reply: str) -> int:
    """无 usage 时按字符数粗略估算(中英混合约 2 字符/token);口径统一到 pricing。"""
    return pricing.estimate_tokens((prompt or "") + (reply or ""))


# ---------- SSE 流式文本回复 ----------

def sse_frame(payload: dict) -> str:
    """SSE 单帧:`data: {json}\\n\\n`。"""
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _timeout_exc(exc: Exception) -> bool:
    return isinstance(exc, (TimeoutError, asyncio.TimeoutError))


def _mark_text_failed(db: Session, task_id: int, user_id: int, exc: Exception, start: float) -> None:
    """流式失败:释放冻结、任务标 failed(费用归 0、cost_status=refunded)。

    已结算(settled)的任务不翻状态:回复已落库、资金已扣,断连只影响投递不影响账务。
    """
    task = db.get(AiTask, task_id)
    if task is None:
        return
    if task.cost_status != "frozen":
        return
    frozen = task.frozen_cost or task.cost or 0
    if frozen:
        billing.refund(db, user_id, frozen, task_id=task_id, model_id=task.model_id)
    task.frozen_cost = 0
    task.cost = 0
    task.cost_status = "refunded"
    task.status = "failed"
    if _timeout_exc(exc):
        task.error_message = "生成超时,本次不扣费"
    else:
        task.error_message = (getattr(exc, "message_zh", None) or "生成失败,本次不扣费")[:500]
    task.latency_ms = int((time.monotonic() - start) * 1000)
    db.commit()


def _write_call_log(db: Session, *, request_id: str, user_id: int, model, provider,
                    start: float, success: bool, error_code: str | None,
                    prompt_tokens: int | None = None, completion_tokens: int | None = None) -> None:
    try:
        db.add(AiCallLog(
            request_id=request_id, user_id=user_id, model_id=getattr(model, "id", None),
            provider=getattr(provider, "vendor", "unknown"),
            latency_ms=int((time.monotonic() - start) * 1000),
            success=success, error_code=error_code,
            prompt_tokens=prompt_tokens, completion_tokens=completion_tokens,
            total_tokens=(prompt_tokens + completion_tokens)
            if prompt_tokens is not None and completion_tokens is not None else None,
        ))
        db.commit()
    except Exception:  # noqa: BLE001 日志失败不影响主流程
        db.rollback()
        logger.exception("ai_call_logs 落库失败(request_id=%s)", request_id)


def _persist_reply(db: Session, *, session_id: int, model, text: str,
                   prompt_tokens: int, completion_tokens: int,
                   task_id: int, user_id: int, frozen: int, start: float) -> int:
    """成功收尾:写 assistant 消息 + 任务 succeeded + 按实际用量结算(线程池内执行)。

    返回最终结算金额(微元;按 token 计费为实际费用,按次计费为单价),供 done 事件换算元展示。
    """
    total_tokens = prompt_tokens + completion_tokens
    db.add(ChatMessage(session_id=session_id, role="assistant", content=text,
                       model_id=model.id, tokens_used=total_tokens))
    task = db.get(AiTask, task_id)
    actual_micro = pricing.cost_micro(model, prompt_tokens, completion_tokens)
    if actual_micro is None:
        # 按次计费:结算售价单价(成本×加价,微元)
        cost = pricing.per_call_sell_micro(model)
        billing.settle(db, user_id, cost, task_id=task_id, model_id=model.id)
    else:
        # 按 token 计费:实际结算,多退少不补,尾差进累积器
        cost = billing.settle_usage(db, user_id, frozen=frozen, actual_micro=actual_micro,
                                    task_id=task_id, model_id=model.id)
    if task is not None:
        task.status = "succeeded"
        task.result_text = text
        task.cost_status = "settled"
        task.cost = cost
        task.frozen_cost = frozen
        task.prompt_tokens = prompt_tokens
        task.completion_tokens = completion_tokens
        task.latency_ms = int((time.monotonic() - start) * 1000)
    db.commit()
    return cost


async def stream_text_reply(*, user_id: int, model, session_id: int, task_id: int,
                            frozen: int, request_id: str, prompt: str) -> AsyncIterator[str]:
    """SSE 流式回复生成器(建流前的校验/冻结/建任务已由路由完成)。

    事件:
    - data: {"delta": "..."}          逐段增量(直接透传 Provider);
    - data: {"done": true, "task_id": N, "cost": N, "tokens": N}  正常结束(已按实际用量结算);
    - data: {"error": {"code": "...", "message": "生成失败,本次不扣费"}}  失败结束(已退费)。
    计费:按 token 模型按上游真实 usage 结算(缺失时估算),多退少不补;
    超时控制:首字节 sse_first_byte_timeout 秒,总时长 sse_total_timeout 秒。
    落库经 run_db 放线程池;断连(CancelledError/GeneratorExit)分支保持同步直调,
    避免二次取消丢失收尾。
    """
    s = get_settings()
    provider = get_provider(model)
    db = SessionLocal()
    start = time.monotonic()
    deadline = start + s.sse_total_timeout
    reply: list[str] = []
    usage: dict = {}
    success = False
    error_code: str | None = None
    settled_cost: int | None = None
    prompt_tokens = completion_tokens = None
    stream = None
    try:
        # 建流前的取历史/生成器构建也可能抛错(DB 异常/未知供应商),纳入 try 保证冻结可退
        history = await run_db(recent_messages, db, session_id)
        stream = provider.generate_text(model, history).__aiter__()
        chunk = None
        got_first = False
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("sse_total_timeout")
            timeout = min(s.sse_first_byte_timeout if not got_first else remaining, remaining)
            try:
                chunk = await asyncio.wait_for(anext(stream), timeout=timeout)
            except StopAsyncIteration:
                break
            got_first = True
            if chunk.get("done"):
                usage = chunk.get("usage") or {}
                break
            delta = chunk.get("delta") or ""
            if delta:
                reply.append(delta)
                yield sse_frame({"delta": delta})

        text = "".join(reply)
        history_chars = len(prompt) + sum(len(m.get("content") or "") for m in history)
        prompt_tokens = int(usage.get("prompt_tokens") or pricing.estimate_tokens_from_chars(history_chars))
        completion_tokens = int(usage.get("completion_tokens") or pricing.estimate_tokens(text))
        settled_cost = await run_db(
            _persist_reply, db, session_id=session_id, model=model, text=text,
            prompt_tokens=prompt_tokens, completion_tokens=completion_tokens,
            task_id=task_id, user_id=user_id, frozen=frozen, start=start,
        )
        success = True
        yield sse_frame({
            "done": True, "task_id": task_id, "cost": pricing.to_yuan(settled_cost),
            "tokens": prompt_tokens + completion_tokens,
            "prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens,
        })
    except (asyncio.CancelledError, GeneratorExit):
        # 客户端断连/任务被取消:按失败处理(不扣费),不可再 yield,清理后原样抛出;
        # 取消路径内不再 await(二次取消会丢失收尾),保持同步直调
        _mark_text_failed(db, task_id, user_id,
                          ProviderError("client_disconnected", "生成中断,本次不扣费"), start)
        raise
    except Exception as exc:  # noqa: BLE001 含 ProviderError / 上游超时
        error_code = getattr(exc, "code", None)
        if _timeout_exc(exc):
            error_code = error_code or "provider_timeout"
        else:
            error_code = error_code or "internal_error"
        await run_db(_mark_text_failed, db, task_id, user_id, exc, start)
        message = "生成超时,本次不扣费" if _timeout_exc(exc) else "生成失败,本次不扣费"
        yield sse_frame({"error": {"code": str(error_code), "message": message}})
    finally:
        _write_call_log(db, request_id=request_id, user_id=user_id, model=model,
                        provider=provider, start=start, success=success, error_code=error_code,
                        prompt_tokens=prompt_tokens, completion_tokens=completion_tokens)
        if stream is not None:
            try:
                await stream.aclose()
            except Exception:  # noqa: BLE001
                pass
        db.close()
