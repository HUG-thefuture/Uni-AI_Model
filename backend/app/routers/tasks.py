"""任务路由(WP04+WP05+WP07):SSE 流式文本对话 + 图像/声音/视频四态异步任务 + 任务中心。

路径不含 /api 前缀,main.py 统一挂 /api 与 /api/v1。
SSE 响应头:Cache-Control: no-cache、X-Accel-Buffering: no(禁 Nginx 缓冲)。
"""
import json

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ..core.db import get_db, run_db
from ..core.deps import get_current_user
from ..core.request_id import current_request_id
from ..core.response import APIError, ok
from ..models.ai_task import AiTask
from ..models.model import Model
from ..models.support import User
from ..schemas.task import (
    AudioAsrTaskCreate,
    AudioCloneTaskCreate,
    ImageTaskCreate,
    TextTaskCreate,
    VideoTaskCreate,
)
from ..services import av_service, billing, chat_service, task_service

router = APIRouter(tags=["tasks"])


# ---------- 同步 DB 辅助函数(经 run_db 放线程池执行,不阻塞事件循环) ----------

def _create_text_task(db: Session, body: TextTaskCreate, user: User):
    """建流前完成全部校验(失败直接 raise,不进入流):
    模型存在且 enabled → 余额冻结 → 会话归属 → 创建 ai_tasks(processing/frozen)、
    写 user 消息;成功收尾/失败释放由 chat_service.stream_text_reply 负责。"""
    model = chat_service.get_enabled_model(db, body.model_id)
    if model.model_type != "text":
        raise APIError(409, "该模型不支持文本对话")
    session = chat_service.get_owned_session(db, user.id, body.session_id)
    billing.freeze(db, user.id, model.price_per_call)  # 余额不足 409「积分不足,请先充值」
    task = AiTask(
        request_id=current_request_id(), user_id=user.id, model_id=model.id,
        task_type="text", prompt=body.message,
        status="processing", cost_status="frozen", cost=model.price_per_call,
    )
    db.add(task)
    chat_service.add_user_message(db, session, body.message, model.id)
    db.commit()
    db.refresh(task)
    return model, session, task


def _submit_image_task(db: Session, body: ImageTaskCreate, user: User, request_id: str) -> AiTask:
    """图像任务提交:模型校验 → 同 request_id 去重 409 → 冻结 → 建 pending 任务。"""
    model = db.get(Model, body.model_id)
    if model is None:
        raise APIError(404, "模型不存在")
    if model.status != "enabled":
        raise APIError(409, "模型维护中,暂不可调用")
    if model.model_type != "image":
        raise APIError(409, "该模型不支持图像生成")
    dup = (
        db.query(AiTask)
        .filter(AiTask.request_id == request_id, AiTask.user_id == user.id)
        .first()
    )
    if dup is not None:
        raise APIError(409, "请勿重复提交")
    params = body.params.model_dump(exclude_none=True) if body.params else {}
    billing.freeze(db, user.id, model.price_per_call)
    task = AiTask(
        request_id=request_id, user_id=user.id, model_id=model.id,
        task_type="image", prompt=body.prompt, params_json=json.dumps(params, ensure_ascii=False),
        status="pending", cost_status="frozen", cost=model.price_per_call,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def _retry_task(db: Session, task_id: int, user: User) -> AiTask:
    """重试校验与重置:仅 failed 的异步任务;重新冻结后置回 pending。"""
    task = db.get(AiTask, task_id)
    if task is None:
        raise APIError(404, "任务不存在")
    if task.user_id != user.id:
        raise APIError(403, "无权限操作该任务")
    if task.task_type == "text":
        raise APIError(409, "请在会话中重新发送")
    if task.status != "failed":
        raise APIError(409, "仅失败任务可以重试")
    model = db.get(Model, task.model_id)
    if model is None or model.status != "enabled":
        raise APIError(409, "模型维护中,暂不可调用")
    billing.freeze(db, user.id, model.price_per_call)  # 重新冻结
    task.status = "pending"
    task.error_message = None
    task.result_text = None
    task.result_url = None
    task.cost = model.price_per_call
    task.cost_status = "frozen"
    task.latency_ms = None
    db.commit()
    db.refresh(task)
    return task


# ---------- 文本:SSE 流式对话 ----------

@router.post("/tasks/text")
async def create_text_task(body: TextTaskCreate,
                           user: User = Depends(get_current_user),
                           db: Session = Depends(get_db)):
    """建流前校验/冻结/建任务在线程池完成,随后进入流式透传。"""
    model, session, task = await run_db(_create_text_task, db, body, user)
    return StreamingResponse(
        chat_service.stream_text_reply(
            user_id=user.id, model=model, session_id=session.id, task_id=task.id,
            cost=model.price_per_call, request_id=task.request_id, prompt=body.message,
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ---------- 图像:异步四态任务 ----------

@router.post("/tasks/image")
async def create_image_task(body: ImageTaskCreate,
                            user: User = Depends(get_current_user),
                            db: Session = Depends(get_db)):
    """提交图像任务:创建 pending 任务并冻结积分,后台 asyncio.create_task 执行,
    立即返回 {task_id, status:"pending"};同 request_id 重复提交 409。"""
    task = await run_db(_submit_image_task, db, body, user, current_request_id())
    task_service.start_background_task(task.id)
    return ok({"task_id": task.id, "status": task.status})


# ---------- 声音/视频:异步四态任务(WP07,复用统一执行器) ----------

@router.post("/tasks/audio/clone")
async def create_audio_clone_task(body: AudioCloneTaskCreate,
                                  user: User = Depends(get_current_user),
                                  db: Session = Depends(get_db)):
    """声音克隆:校验模型(audio/enabled)与时长上限 → 冻结 → pending 任务,
    立即返回 {task_id, status:"pending"};同 request_id 重复提交 409。"""
    model = await run_db(av_service.get_audio_model, db, body.model_id)
    params = {
        "voice_name": body.voice_name,
        "text": body.text,
        "sample_audio_url": body.sample_audio_url,
        "duration_sec": body.duration_sec,
    }
    params = {k: v for k, v in params.items() if v is not None}
    task = await run_db(
        av_service.submit_av_task, db, user, model, "audio_clone", body.text, params,
        current_request_id(),
    )
    task_service.start_background_task(task.id)
    return ok({"task_id": task.id, "status": task.status})


@router.post("/tasks/audio/asr")
async def create_audio_asr_task(body: AudioAsrTaskCreate,
                                user: User = Depends(get_current_user),
                                db: Session = Depends(get_db)):
    """语音识别:校验同声音克隆;params_json 存 audio_url 供执行器下载转写。"""
    model = await run_db(av_service.get_audio_model, db, body.model_id)
    params = {"audio_url": body.audio_url}
    if body.duration_sec is not None:
        params["duration_sec"] = body.duration_sec
    task = await run_db(
        av_service.submit_av_task, db, user, model, "asr", body.audio_url, params,
        current_request_id(),
    )
    task_service.start_background_task(task.id)
    return ok({"task_id": task.id, "status": task.status})


@router.post("/tasks/video")
async def create_video_task(body: VideoTaskCreate,
                            user: User = Depends(get_current_user),
                            db: Session = Depends(get_db)):
    """长文本转视频:文本 ≤2000 字(超长 400)→ 冻结 → pending 任务,
    后台提交 SiliconFlow 并轮询；图生视频必须选择 I2V 模型。"""
    model = await run_db(av_service.get_video_model, db, body.model_id)
    params = body.params.model_dump(exclude_none=True) if body.params else {}
    if params.get("image_url") and "I2V" not in model.model_code.upper():
        raise APIError(409, "上传首帧后请在模型广场选择图生视频模型")
    task = await run_db(
        av_service.submit_av_task, db, user, model, "video", body.text, params,
        current_request_id(),
    )
    task_service.start_background_task(task.id)
    return ok({"task_id": task.id, "status": task.status})


# ---------- 任务中心 ----------

@router.get("/tasks")
def list_tasks(page: int = Query(1, ge=1),
               page_size: int = Query(10, ge=1, le=100),
               task_type: str | None = Query(None, description="text/image/audio_clone/asr/video"),
               user: User = Depends(get_current_user),
               db: Session = Depends(get_db)):
    """我的任务分页;processing 任务附 elapsed_sec(距创建秒数)。"""
    q = db.query(AiTask).filter(AiTask.user_id == user.id)
    if task_type:
        q = q.filter(AiTask.task_type == task_type)
    q = q.order_by(AiTask.id.desc())
    total = q.count()
    rows = q.offset((page - 1) * page_size).limit(page_size).all()
    return ok({
        "total": total, "page": page, "page_size": page_size,
        "items": [task_service.task_to_item(t) for t in rows],
    })


@router.get("/tasks/{task_id}")
def get_task(task_id: int,
             user: User = Depends(get_current_user),
             db: Session = Depends(get_db)):
    """任务详情;他人任务 403;image 任务解析 result_urls。"""
    task = db.get(AiTask, task_id)
    if task is None:
        raise APIError(404, "任务不存在")
    if task.user_id != user.id:
        raise APIError(403, "无权限查看该任务")
    return ok(task_service.task_to_detail(task))


@router.post("/tasks/{task_id}/retry")
async def retry_task(task_id: int,
                     user: User = Depends(get_current_user),
                     db: Session = Depends(get_db)):
    """重试:仅 failed 的异步任务可重试(文本任务为同步流式,提示回会话重发)。"""
    task = await run_db(_retry_task, db, task_id, user)
    task_service.start_background_task(task.id)
    return ok({"task_id": task.id, "status": task.status})
