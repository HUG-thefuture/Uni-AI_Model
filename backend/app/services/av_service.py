"""声音/视频任务业务逻辑 + 上传校验(WP07)。

- 模型校验:存在(404)/ enabled(409 维护中)/ model_type 匹配(409 不支持该类任务);
- 时长校验:提交方若已知时长(duration_sec),超过 model.max_duration_sec 直接 400
  (本期不做 ffprobe 实测,登记 TODO docs/api.md);
- 提交通道:与图像任务同一条四态链路 —— 同 request_id 幂等 409 → billing.freeze 冻结 →
  建 ai_tasks(pending/frozen)→ start_background_task 后台执行;
- 上传校验:扩展名白名单 + 10MB 上限 + 文件头魔数,三者全过才落盘。
"""
import asyncio
import json
import uuid
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy.orm import Session

from ..core.config import get_settings
from ..core.request_id import current_request_id
from ..core.response import APIError
from ..models.ai_task import AiTask
from ..models.model import Model
from ..models.support import User
from ..services import billing, pricing

# ---------- 上传常量 ----------
MAX_UPLOAD_SIZE = 10 * 1024 * 1024  # 10MB
ALLOWED_EXTENSIONS = {"mp3", "wav", "m4a", "png", "jpg"}


def _magic_ok(ext: str, head: bytes) -> bool:
    """简易魔数校验(文件头前 16 字节足够)。"""
    if ext == "mp3":
        # ID3v2 标签,或 MPEG 帧同步字 0xFFEx(11 位同步 + layer/version 任意)
        return head.startswith(b"ID3") or (len(head) >= 2 and head[0] == 0xFF and head[1] & 0xE0 == 0xE0)
    if ext == "wav":
        return head.startswith(b"RIFF")
    if ext == "png":
        return head.startswith(b"\x89PNG")
    if ext == "jpg":
        return head.startswith(b"\xFF\xD8")
    if ext == "m4a":
        # ISO-BMFF:偏移 4 起为 "ftyp" 品牌盒
        return len(head) >= 8 and head[4:8] == b"ftyp"
    return False


async def save_upload(file: UploadFile) -> dict:
    """校验并落盘上传文件,返回 {"url", "filename", "size"}。

    - 扩展名不在白名单 → 400「不支持的文件类型」;
    - 超过 10MB → 400「文件超过 10MB 限制」;
    - 魔数不符 → 400「文件内容与类型不符」;
    - 文件名加 uuid 前缀防覆盖,保存到 settings.upload_dir,经 /static 访问。
    """
    raw_name = Path(file.filename or "").name  # 去路径,防目录穿越
    ext = raw_name.rsplit(".", 1)[-1].lower() if "." in raw_name else ""
    if ext not in ALLOWED_EXTENSIONS:
        raise APIError(400, "不支持的文件类型")

    # 多读 1 字节用于判断超限
    content = await file.read(MAX_UPLOAD_SIZE + 1)
    if len(content) > MAX_UPLOAD_SIZE:
        raise APIError(400, "文件超过 10MB 限制")
    if not content:
        raise APIError(400, "文件内容为空")
    if not _magic_ok(ext, content[:16]):
        raise APIError(400, "文件内容与类型不符")

    filename = f"{uuid.uuid4().hex[:12]}-{raw_name}"
    upload_dir = Path(get_settings().upload_dir)
    await asyncio.to_thread(upload_dir.mkdir, parents=True, exist_ok=True)
    await asyncio.to_thread((upload_dir / filename).write_bytes, content)
    return {"url": f"/static/{filename}", "filename": filename, "size": len(content)}


# ---------- 模型与任务校验 ----------

def get_audio_model(db: Session, model_id: int) -> Model:
    """声音类任务(克隆/识别)模型校验。"""
    return _get_model_of_type(db, model_id, "audio", "该模型不支持声音任务")


def get_video_model(db: Session, model_id: int) -> Model:
    """视频任务模型校验。"""
    return _get_model_of_type(db, model_id, "video", "该模型不支持视频任务")


def _get_model_of_type(db: Session, model_id: int, model_type: str, mismatch_msg: str) -> Model:
    model = db.get(Model, model_id)
    if model is None:
        raise APIError(404, "模型不存在")
    if model.status != "enabled":
        raise APIError(409, "模型维护中,暂不可调用")
    if model.model_type != model_type:
        raise APIError(409, mismatch_msg)
    return model


def check_duration(params: dict, model: Model) -> None:
    """提交方已知时长时的上限校验(实测依赖 ffprobe,TODO 登记 docs/api.md)。"""
    duration = params.get("duration_sec")
    limit = model.max_duration_sec
    if duration is not None and limit is not None and int(duration) > int(limit):
        raise APIError(400, "音频时长超过模型上限")


def submit_av_task(db: Session, user: User, model: Model, task_type: str,
                   prompt: str | None, params: dict) -> AiTask:
    """四态提交通道:幂等 409 → 冻结 → 建 pending 任务,与图像任务同链路。

    只做落库,不启动后台执行——本函数会被路由经 run_db 放线程池调用,
    线程内没有事件循环;start_background_task 由调用方在事件循环上调用。
    """
    dup = (
        db.query(AiTask)
        .filter(AiTask.request_id == current_request_id(), AiTask.user_id == user.id)
        .first()
    )
    if dup is not None:
        raise APIError(409, "请勿重复提交")
    check_duration(params, model)
    frozen = pricing.per_call_sell_micro(model)  # 视频=元/条,音频=元/次,已含加价
    billing.freeze(db, user.id, frozen)  # 余额不足 409「余额不足,请先充值」
    task = AiTask(
        request_id=current_request_id(), user_id=user.id, model_id=model.id,
        task_type=task_type, prompt=prompt,
        params_json=json.dumps(params, ensure_ascii=False),
        status="pending", cost_status="frozen", cost=frozen,
        frozen_cost=frozen,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task
