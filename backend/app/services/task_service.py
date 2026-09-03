"""异步任务统一执行器(WP05+WP07):四态 pending → processing → succeeded / failed。

- run_async_task(task_id):从 ai_tasks 读参数执行,按 task_type / model.model_type
  分派到 Provider 对应 generate_* 方法(text/image/audio_clone/asr/video 统一走此链路);
- 任何异常都在执行器内消化:失败 → billing.refund + error_message(中文)、cost 归 0,
  绝不抛到 asyncio 顶层(红线:失败绝不扣费);
- 超时兜底:外层 asyncio.wait_for(图像 120s,与 read_timeouts["image"] 一致),超时按失败处理;
- start_background_task:应用内存级后台执行(asyncio.create_task,强引用防 GC)。
"""
import asyncio
import json
import logging
import time
from datetime import datetime, timezone

from ..core.config import get_settings
from ..core.db import SessionLocal, run_db
from ..models.ai_call_log import AiCallLog
from ..models.ai_task import AiTask
from ..models.model import Model
from ..providers.exceptions import ProviderError
from ..providers.factory import get_provider
from ..services import billing

logger = logging.getLogger("app.task")

# 图像任务总超时兜底(秒);provider 内部已有 httpx read timeout(120s)
IMAGE_TOTAL_TIMEOUT = 120

# 后台任务强引用集合,防止 create_task 结果被 GC 回收
_background_tasks: set[asyncio.Task] = set()


def start_background_task(task_id: int) -> None:
    """在当前事件循环中启动后台执行(无事件循环时仅告警,任务留待外部执行)。"""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        logger.warning("任务 %s 当前无事件循环,未启动后台执行", task_id)
        return
    t = loop.create_task(run_async_task(task_id))
    _background_tasks.add(t)
    t.add_done_callback(_background_tasks.discard)


def _fail_task(db, task: AiTask | None, message: str, start: float) -> None:
    """失败收尾:释放冻结(费用归 0)、status=failed、error_message 中文。"""
    if task is None:
        return
    try:
        if task.cost_status == "frozen" and task.cost:
            billing.refund(db, task.user_id, task.cost, task_id=task.id)
            task.cost_status = "refunded"
            task.cost = 0
        task.status = "failed"
        task.error_message = (message or "任务执行失败,本次不扣费")[:500]
        task.latency_ms = int((time.monotonic() - start) * 1000)
        db.commit()
    except Exception:  # noqa: BLE001 收尾失败不能向上抛
        db.rollback()
        logger.exception("任务 %s 失败收尾异常", task.id)


async def _poll_video_result(provider, model, handle: dict) -> list[str]:
    """视频句柄轮询:上游查询接口本期未定(TODO 登记 docs/api.md)。

    - provider 若实现 query_video(model, handle)(Mock / Online 已实现)则按间隔调用,
      返回 {"status": "completed", "video_urls": [...] 或 "video_url": ...} 即成功;
    - 无查询能力时仅按配置间隔空轮询,超过 video_poll_max_sec
      判超时失败「视频生成超时,本次不扣费」。
    """
    s = get_settings()
    interval = max(0.05, s.video_poll_interval_sec)
    deadline = time.monotonic() + max(s.video_poll_max_sec, interval)
    query = getattr(provider, "query_video", None)
    while time.monotonic() < deadline:
        await asyncio.sleep(interval)
        if callable(query):
            poll = await query(model, handle)
            if poll.get("status") == "completed":
                urls = poll.get("video_urls") or ([poll["video_url"]] if poll.get("video_url") else [])
                if urls:
                    return urls
    raise ProviderError("provider_timeout", "视频生成超时,本次不扣费")


def _load_and_start(db, task_id: int) -> tuple[AiTask | None, Model | None, dict]:
    """加载任务/模型并置 processing(线程池内执行,不阻塞事件循环)。"""
    task = db.get(AiTask, task_id)
    if task is None:
        return None, None, {}
    model = db.get(Model, task.model_id)
    task.status = "processing"
    db.commit()
    params: dict = {}
    if task.params_json:
        try:
            params = json.loads(task.params_json)
        except ValueError:
            params = {}
    return task, model, params


def _finalize_success(db, task: AiTask, model: Model, start: float) -> None:
    """成功收尾:结算 + status=succeeded(线程池内执行)。"""
    billing.settle(db, task.user_id, task.cost, task_id=task.id, model_id=model.id)
    task.cost_status = "settled"
    task.status = "succeeded"
    task.error_message = None
    task.latency_ms = int((time.monotonic() - start) * 1000)
    db.commit()


async def run_async_task(task_id: int) -> None:
    """统一执行器:任何异常都在本函数内消化,绝不向 asyncio 顶层抛出。

    DB 读写策略:初始加载保持同步直调——后台任务可能在短生命周期事件循环
    (如测试 portal)中执行,首个 await 前先完成建流可避免任务被静默丢弃;
    成功收尾经 run_db 放线程池。_fail_task 与 finally 落库可能运行于取消路径,
    保持同步直调,避免二次取消丢失收尾。
    """
    db = SessionLocal()
    start = time.monotonic()
    task: AiTask | None = None
    provider = None
    success = False
    error_code: str | None = None
    try:
        task, model, params = _load_and_start(db, task_id)
        if task is None:
            logger.warning("任务 %s 不存在,跳过执行", task_id)
            return
        if model is None:
            raise ProviderError("model_not_found", "任务对应的模型不存在")
        provider = get_provider(model)
        task_type = task.task_type or model.model_type

        if task_type == "image" or model.model_type == "image":
            timeout = get_settings().read_timeouts.get("image", IMAGE_TOTAL_TIMEOUT)
            result = await asyncio.wait_for(
                provider.generate_image(model, task.prompt or "", params), timeout=timeout
            )
            urls = list(result.get("image_urls") or [])
            if not urls and result.get("image_url"):
                urls = [result["image_url"]]
            task.result_url = json.dumps(urls, ensure_ascii=False)
        elif task_type == "text":
            # 兜底通路(正常文本走 SSE 流式,不经此执行器):非流式一次取全
            result = await asyncio.wait_for(
                provider.generate_text_once(
                    model, [{"role": "user", "content": task.prompt or ""}], params
                ),
                timeout=get_settings().read_timeouts.get("text", 60),
            )
            task.result_text = result.get("content", "")
        elif task_type == "audio_clone":
            # 声音克隆:params_json 提供 voice_name/text,成功取 audio_url 落 result_url
            result = await asyncio.wait_for(
                provider.generate_audio_clone(model, params),
                timeout=get_settings().read_timeouts.get("audio", 300),
            )
            audio_url = result.get("audio_url")
            if not audio_url:
                raise ProviderError("provider_bad_response", "声音服务未返回音频地址")
            task.result_url = audio_url
        elif task_type == "asr":
            # 语音识别:params_json.audio_url(可来自 /uploads),成功取 text 落 result_text
            audio_url = params.get("audio_url") or task.prompt or ""
            result = await asyncio.wait_for(
                provider.generate_asr(model, audio_url, params),
                timeout=get_settings().read_timeouts.get("audio", 300),
            )
            task.result_text = result.get("text", "")
        elif task_type == "video":
            # 长文本转视频:先拿任务句柄;completed 直接取 video_url,
            # processing 则按 video_poll_interval_sec 轮询至 video_poll_max_sec(超时判 failed 不扣费)
            handle = await asyncio.wait_for(
                provider.generate_video(model, task.prompt or "", params),
                timeout=get_settings().read_timeouts.get("video", 300),
            )
            if handle.get("status") == "completed" and (handle.get("video_urls") or handle.get("video_url")):
                urls = handle.get("video_urls") or [handle["video_url"]]
                task.result_url = json.dumps(urls, ensure_ascii=False)
            else:
                task.result_url = json.dumps(
                    await _poll_video_result(provider, model, handle), ensure_ascii=False
                )
        else:
            raise ProviderError("not_implemented", "该任务类型暂未开放,请等待后续版本")

        # db 与 task 属于当前 worker 线程，不能交给 run_db 的另一个线程使用。
        _finalize_success(db, task, model, start)
        success = True
    except (asyncio.TimeoutError, TimeoutError):
        error_code = "provider_timeout"
        _fail_task(db, task, "生成超时,本次不扣费", start)
    except asyncio.CancelledError:
        # 事件循环关闭/任务被取消:按失败退费,不扣费;原样抛出以配合取消语义
        error_code = "cancelled"
        _fail_task(db, task, "生成中断,本次不扣费", start)
        raise
    except ProviderError as exc:
        error_code = exc.code
        _fail_task(db, task, exc.message_zh, start)
    except Exception as exc:  # noqa: BLE001 兜底:任何异常不得逃逸
        logger.exception("任务 %s 执行异常", task_id)
        error_code = "internal_error"
        _fail_task(db, task, "任务执行失败,本次不扣费", start)
    finally:
        try:
            if task is not None:
                db.add(AiCallLog(
                    request_id=task.request_id, user_id=task.user_id,
                    model_id=task.model_id,
                    provider=getattr(provider, "vendor", "unknown") if provider else "unknown",
                    latency_ms=int((time.monotonic() - start) * 1000),
                    success=success, error_code=error_code,
                ))
                db.commit()
        except Exception:  # noqa: BLE001 日志失败不影响主流程
            db.rollback()
            logger.exception("ai_call_logs 落库失败(task_id=%s)", task_id)
        db.close()


# ---------- 序列化 ----------

def elapsed_seconds(created_at: datetime | None) -> int:
    """processing 任务距 created_at 的秒数(下限 0;时区口径 TODO 登记 docs/api.md)。"""
    if created_at is None:
        return 0
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    return max(0, int((now - created_at).total_seconds()))


def task_to_item(task: AiTask) -> dict:
    """任务中心列表项。"""
    item = {
        "id": task.id,
        "task_type": task.task_type,
        "status": task.status,
        "prompt": task.prompt,
        "result_text": task.result_text,
        "result_url": task.result_url,
        "error_message": task.error_message,
        "cost": task.cost,
        "latency_ms": task.latency_ms,
        "created_at": task.created_at.isoformat() if task.created_at else None,
    }
    if task.status == "processing":
        item["elapsed_sec"] = elapsed_seconds(task.created_at)
    return item


def task_to_detail(task: AiTask) -> dict:
    """任务详情:媒体任务(image/audio_clone/video)把单个或 JSON 数组 result_url 统一为 result_urls。"""
    item = task_to_item(task)
    if task.task_type in {"image", "audio_clone", "video"} and task.result_url:
        try:
            urls = json.loads(task.result_url)
            item["result_urls"] = urls if isinstance(urls, list) else [task.result_url]
        except ValueError:
            item["result_urls"] = [task.result_url]
    return item
