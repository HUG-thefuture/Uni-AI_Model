"""任务相关请求体(WP04+WP05)。响应统一走 core/response.ok(),不再单独建模。"""
from pydantic import BaseModel, Field


class TextTaskCreate(BaseModel):
    """POST /tasks/text 请求体(SSE 流式对话)。"""

    session_id: int = Field(..., gt=0, description="会话 ID,需归属当前用户")
    model_id: int = Field(..., gt=0, description="模型 ID,需存在且 enabled")
    message: str = Field(..., min_length=1, max_length=4000, description="用户输入")


class ImageTaskParams(BaseModel):
    """图像任务可选参数。"""

    image_size: str | None = Field(default=None, description="尺寸,如 1024x1024,默认 1024x1024")
    num: int | None = Field(default=None, ge=1, le=4, description="生成数量 1..4,默认 1")
    image_url: str | None = Field(default=None, description="图生图参考图 URL(WP07 图生图预留)")
    negative_prompt: str | None = Field(default=None, max_length=2000, description="负面提示词")


class ImageTaskCreate(BaseModel):
    """POST /tasks/image 请求体(异步四态任务)。"""

    model_id: int = Field(..., gt=0, description="模型 ID,需存在且 enabled 且 model_type=image")
    prompt: str = Field(..., min_length=1, max_length=2000, description="生成提示词")
    params: ImageTaskParams | None = Field(default=None, description="可选参数")


# ---------- 声音/视频任务(WP07) ----------

class AudioCloneTaskCreate(BaseModel):
    """POST /tasks/audio/clone 请求体(异步四态任务)。

    sample_audio_url 可由 POST /uploads 返回的 url 填入。
    """

    model_id: int = Field(..., gt=0, description="模型 ID,需存在且 enabled 且 model_type=audio")
    voice_name: str = Field(..., min_length=1, max_length=100, description="音色名,如 alloy")
    sample_audio_url: str | None = Field(default=None, max_length=500, description="参考音频 URL")
    text: str = Field(..., min_length=1, max_length=5000, description="要合成的文本")
    duration_sec: int | None = Field(default=None, ge=1, description="参考音频时长(秒,提交方已知时传入)")


class AudioAsrTaskCreate(BaseModel):
    """POST /tasks/audio/asr 请求体(异步四态任务)。"""

    model_id: int = Field(..., gt=0, description="模型 ID,需存在且 enabled 且 model_type=audio")
    audio_url: str = Field(..., min_length=1, max_length=500, description="音频 URL(可来自 /uploads)")
    duration_sec: int | None = Field(default=None, ge=1, description="音频时长(秒,提交方已知时传入)")


class VideoTaskParams(BaseModel):
    """视频任务可选参数。"""

    resolution: str | None = Field(default=None, max_length=20, description="分辨率,如 1280x720")
    duration_sec: int | None = Field(default=None, ge=1, description="视频时长上限(秒)")
    negative_prompt: str | None = Field(default=None, max_length=2000, description="负面提示词")
    seed: int | None = Field(default=None, ge=0, description="随机种子")
    image_url: str | None = Field(default=None, max_length=500, description="图生视频首帧，可来自 /uploads")


class VideoTaskCreate(BaseModel):
    """POST /tasks/video 请求体(异步四态长耗时任务)。"""

    model_id: int = Field(..., gt=0, description="模型 ID,需存在且 enabled 且 model_type=video")
    text: str = Field(..., min_length=1, max_length=2000, description="视频文案,≤2000 字")
    params: VideoTaskParams | None = Field(default=None, description="可选参数(分辨率/时长上限)")
