"""MockProvider:完整实现,无 Key 环境全链路联调与演示兜底。

- 文本按「句」流式返回,sleep 模拟 2-5 秒总延迟;
- 图像/声音/视频返回内置样例文件 URL(可用 static 占位或公网样例);
- 不发起任何外部请求,行为与真实通路契约一致,前端无感知。
"""
import asyncio
import logging
import random
import re
import time
from typing import AsyncIterator

from app.providers.base import BaseProvider

logger = logging.getLogger("app.provider.mock")

# 样例素材 URL(演示用;上线前可替换为本站 static 路径)
MOCK_IMAGE_URL = "https://dummyimage.com/1024x1024/4f7cff/ffffff.png&text=Mock+Image"
MOCK_AUDIO_URL = "https://interactive-examples.mdn.mozilla.net/media/cc0-audio/t-rex-roar.mp3"
MOCK_VIDEO_URL = "https://interactive-examples.mdn.mozilla.net/media/cc0-videos/flower.mp4"


class MockProvider(BaseProvider):
    vendor = "mock"

    @staticmethod
    async def _simulate_latency(min_sec: float = 2.0, max_sec: float = 5.0) -> None:
        """模拟上游 2-5 秒延迟,让前端 loading/四态流转可被真实演练。"""
        await asyncio.sleep(random.uniform(min_sec, max_sec))

    async def generate_text(
        self, model, messages: list[dict], params: dict | None = None
    ) -> AsyncIterator[dict]:
        prompt = next(
            (m["content"] for m in reversed(messages) if m.get("role") == "user"), ""
        )
        reply = (
            f"【Mock 回复】你刚才说:「{prompt[:80]}」。"
            "当前处于无 Key 演示模式,接口链路(流式增量、四态任务、调用日志)均与线上模型一致。"
        )
        sentences = [s + ("。" if not s.endswith(("。", "!", "?", "!", "?")) else "")
                     for s in re.split(r"(?<=[。!?])", reply) if s]
        total = random.uniform(2.0, 5.0)
        per_sentence = total / max(1, len(sentences))
        for s in sentences:
            await asyncio.sleep(per_sentence)
            yield {"delta": s}
        yield {
            "done": True,
            "usage": {
                "prompt_tokens": len(prompt),
                "completion_tokens": len(reply),
                "total_tokens": len(prompt) + len(reply),
                "mock": True,
            },
        }

    async def generate_image(self, model, prompt: str, params: dict | None = None) -> dict:
        await self._simulate_latency()
        return {"image_url": MOCK_IMAGE_URL, "raw": {"mock": True, "prompt": prompt}}

    async def generate_audio_clone(self, model, params: dict | None = None) -> dict:
        await self._simulate_latency()
        return {"audio_url": MOCK_AUDIO_URL, "raw": {"mock": True}}

    async def generate_asr(self, model, audio_url: str, params: dict | None = None) -> dict:
        await self._simulate_latency()
        return {
            "text": "【Mock 识别结果】这是语音识别样例文本,与真实接口字段一致。",
            "raw": {"mock": True, "audio_url": audio_url},
        }

    async def generate_video(self, model, prompt: str, params: dict | None = None) -> dict:
        """长耗时任务:立即返回句柄,由上层任务服务轮询状态(模拟 4 态流转)。"""
        task_id = f"mock-video-{random.randint(100000, 999999)}"
        return {"task_id": task_id, "status": "processing", "raw": {"mock": True, "prompt": prompt}}

    async def health_check(self, model) -> dict:
        await asyncio.sleep(0.05)
        return {"ok": True, "latency_ms": 50}
