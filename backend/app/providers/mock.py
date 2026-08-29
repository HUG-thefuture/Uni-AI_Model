"""MockProvider:完整实现,无 Key 环境全链路联调与演示兜底。

- 文本按「句」流式返回,sleep 模拟 2-5 秒总延迟;
- 图像/声音/视频返回内置样例文件 URL(可用 static 占位或公网样例);
- 不发起任何外部请求,行为与真实通路契约一致,前端无感知;
- 显式延迟(WP09,测试/演示用):params["mock_delay_sec"] 覆盖随机延迟,
  其次读 models.config_json 里的 mock_delay_sec,再次读全局 Settings.mock_delay_sec;
  三处都未设置时保持 2-5 秒随机(兼容既有测试对 random.uniform 的压缩)。
"""
import asyncio
import json
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

# 最小可用 MP3 字节(ID3v2 头 + 一帧 MPEG 同步字):供 Mock 克隆音频落盘 /static 使用
MOCK_MP3_BYTES = b"ID3\x03\x00\x00\x00\x00\x00\x00" + b"\xff\xfb\x90\x64" + b"\x00" * 128


class MockProvider(BaseProvider):
    vendor = "mock"

    @classmethod
    def _explicit_delay(cls, model, params: dict | None) -> float | None:
        """解析显式延迟(秒):params["mock_delay_sec"] → model.config_json → 全局配置。

        返回 None 表示未设置(走默认随机延迟);非法值一律忽略,绝不抛异常。
        """
        raw = (params or {}).get("mock_delay_sec")
        if raw is None and getattr(model, "config_json", None):
            try:
                cfg = json.loads(model.config_json)
                if isinstance(cfg, dict):
                    raw = cfg.get("mock_delay_sec")
            except (ValueError, TypeError):
                raw = None
        if raw is None:
            try:
                from app.core.config import get_settings

                raw = get_settings().mock_delay_sec
            except Exception:  # noqa: BLE001 配置未就绪时按未设置处理
                raw = None
        try:
            delay = float(raw) if raw is not None else None
        except (TypeError, ValueError):
            return None
        if delay is None or delay < 0:
            return None
        return delay

    async def _simulate_latency(
        self, model=None, params: dict | None = None,
        min_sec: float = 2.0, max_sec: float = 5.0,
    ) -> None:
        """模拟上游延迟:显式 mock_delay_sec 优先,否则 2-5 秒随机
        (默认分支仍走 random.uniform,兼容测试对该函数的压缩 monkeypatch)。"""
        delay = self._explicit_delay(model, params)
        if delay is not None:
            await asyncio.sleep(delay)
        else:
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
        explicit = self._explicit_delay(model, params)
        total = explicit if explicit is not None else random.uniform(2.0, 5.0)
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
        """返回 2-4 张样例图(数量取 params["num"],默认 2,钳制 1..4)。

        与 OnlineProvider 统一返回 {"image_urls": [str], "raw": {...}};
        另保留 image_url(首图)键以兼容旧调用方。
        """
        params = params or {}
        await self._simulate_latency(model, params)
        try:
            num = int(params.get("num") or 2)
        except (TypeError, ValueError):
            num = 2
        num = max(1, min(4, num))
        urls = [MOCK_IMAGE_URL for _ in range(num)]
        return {
            "image_urls": urls,
            "image_url": urls[0],
            "raw": {"mock": True, "prompt": prompt, "num": num},
        }

    async def generate_audio_clone(self, model, params: dict | None = None) -> dict:
        """与 OnlineProvider 契约一致:合成音频落盘 upload_dir,返回 /static/ URL;
        落盘失败(只读盘等)时退回公网样例 URL。"""
        await self._simulate_latency(model, params, min_sec=3.0, max_sec=8.0)
        try:
            import uuid as _uuid
            from pathlib import Path

            from app.core.config import get_settings

            upload_dir = Path(get_settings().upload_dir)
            upload_dir.mkdir(parents=True, exist_ok=True)
            filename = f"clone-mock-{_uuid.uuid4().hex[:12]}.mp3"
            (upload_dir / filename).write_bytes(MOCK_MP3_BYTES)
            return {"audio_url": f"/static/{filename}", "raw": {"mock": True}}
        except OSError:
            return {"audio_url": MOCK_AUDIO_URL, "raw": {"mock": True}}

    async def generate_asr(self, model, audio_url: str, params: dict | None = None) -> dict:
        await self._simulate_latency(model, params)
        return {
            "text": "【Mock 识别结果】这是语音识别样例文本,与真实接口字段一致。",
            "raw": {"mock": True, "audio_url": audio_url},
        }

    async def generate_video(self, model, prompt: str, params: dict | None = None) -> dict:
        """长耗时任务:立即返回句柄,由上层任务服务轮询状态(模拟 4 态流转)。"""
        task_id = f"mock-video-{random.randint(100000, 999999)}"
        return {"task_id": task_id, "status": "processing", "raw": {"mock": True, "prompt": prompt}}

    async def query_video(self, model, handle: dict) -> dict:
        """视频句柄完成机制:sleep 3-5s 后返回 completed 语义,供 task_service 轮询。
        (generate_video 保持句柄语义以兼容既有验收;线上模型无本方法 → 轮询超时判 failed。)"""
        await self._simulate_latency(min_sec=3.0, max_sec=5.0)
        return {
            "task_id": handle.get("task_id"),
            "status": "completed",
            "video_url": MOCK_VIDEO_URL,
            "raw": {"mock": True, "polled": True},
        }

    async def health_check(self, model) -> dict:
        await asyncio.sleep(0.05)
        return {"ok": True, "latency_ms": 50}
