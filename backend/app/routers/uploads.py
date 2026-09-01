"""文件上传路由(WP07):POST /uploads(multipart)。

路径不含 /api 前缀,main.py 统一挂 /api 与 /api/v1。
校验链:扩展名白名单(mp3/wav/m4a/png/jpg)→ 10MB 上限 → 文件头魔数;
通过后以 uuid 前缀文件名落盘 settings.upload_dir,经 /static 访问。
"""
from fastapi import APIRouter, Depends, UploadFile

from ..core.deps import get_current_user
from ..core.response import ok
from ..models.support import User
from ..services import av_service

router = APIRouter(tags=["uploads"])


@router.post("/uploads")
async def upload_file(file: UploadFile,
                      user: User = Depends(get_current_user)):
    """上传音频/图片素材,返回 {url, filename, size};url 可直接填入声音/识别任务。"""
    result = await av_service.save_upload(file)
    return ok(result)
