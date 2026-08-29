"""LocalProvider:Ollama 本地模型(OpenAI 兼容路径 /v1)。

本工作包(WP01)只搭骨架:地址从 OLLAMA_BASE_URL 读取(默认 http://localhost:11434);
流式/探活等完整实现在 WP08(本地模型与启停接口)完成。
"""
import time
from typing import AsyncIterator

import httpx

from app.core.config import get_settings
from app.providers.base import BaseProvider


class LocalProvider(BaseProvider):
    vendor = "ollama"

    @property
    def base_url(self) -> str:
        return get_settings().ollama_base_url.rstrip("/")

    async def generate_text(
        self, model, messages: list[dict], params: dict | None = None
    ) -> AsyncIterator[dict]:
        raise NotImplementedError("Ollama 流式通路在 WP08 实现(POST {base}/v1/chat/completions)")
        yield  # pragma: no cover

    async def health_check(self, model) -> dict:
        """探活:GET {base}/api/tags,Ollama 就绪即可达。"""
        start = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=self._timeout("text")) as client:
                resp = await client.get(f"{self.base_url}/api/tags")
            return {"ok": resp.status_code < 400, "latency_ms": int((time.monotonic() - start) * 1000)}
        except httpx.HTTPError:
            return {"ok": False, "latency_ms": int((time.monotonic() - start) * 1000)}

    async def generate_image(self, model, prompt: str, params: dict | None = None) -> dict:
        raise NotImplementedError("本地模型不支持图像生成")

    async def generate_audio_clone(self, model, params: dict | None = None) -> dict:
        raise NotImplementedError("本地模型不支持声音克隆")

    async def generate_asr(self, model, audio_url: str, params: dict | None = None) -> dict:
        raise NotImplementedError("本地语音识别在 WP08 评估")

    async def generate_video(self, model, prompt: str, params: dict | None = None) -> dict:
        raise NotImplementedError("本地模型不支持视频生成")
