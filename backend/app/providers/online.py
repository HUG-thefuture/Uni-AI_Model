"""OnlineProvider:对接硅基流动(OpenAI 兼容协议)。

- 密钥从环境变量 SILICONFLOW_API_KEY 读取,绝不硬编码、绝不入库;
- 本工作包(WP01)实现 generate_text 的流式与非流式通路(POST /v1/chat/completions,
  stream=true 时解析 SSE 增量),图像/声音/视频方法留待 WP04/WP07 实现。
"""
import json
import logging
import time
from typing import AsyncIterator

import httpx

from app.core.config import get_settings
from app.providers.base import BaseProvider
from app.providers.exceptions import ProviderError

logger = logging.getLogger("app.provider.online")

BASE_URL = "https://api.siliconflow.cn"


class OnlineProvider(BaseProvider):
    vendor = "siliconflow"

    # ---------- 文本 ----------

    async def generate_text(
        self, model, messages: list[dict], params: dict | None = None
    ) -> AsyncIterator[dict]:
        """流式对话。yield {"delta": str} ... 最后 yield {"done": True, "usage": {...}}。"""
        key = self.require_config(get_settings().siliconflow_api_key, "SILICONFLOW_API_KEY")
        body = {
            "model": model.model_code,
            "messages": messages,
            "stream": True,
            **self.model_params(model, {"temperature": 0.7, "max_tokens": 1024}),
        }
        client, resp = await self._open_stream_with_retry(
            f"{BASE_URL}/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json_body=body,
            model_type="text",
        )
        usage: dict = {}
        try:
            async for line in resp.aiter_lines():
                if not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if payload == "[DONE]":
                    break
                try:
                    chunk = json.loads(payload)
                except ValueError:
                    logger.warning("SSE 增量解析失败,跳过: %s", payload[:200])
                    continue
                if chunk.get("usage"):
                    usage = chunk["usage"]
                for choice in chunk.get("choices", []):
                    delta = choice.get("delta", {}).get("content")
                    if delta:
                        yield {"delta": delta}
            yield {"done": True, "usage": usage}
        finally:
            await resp.aclose()
            await client.aclose()

    async def generate_text_once(
        self, model, messages: list[dict], params: dict | None = None
    ) -> dict:
        """非流式对话:一次拿到完整结果,便于验证与 health_check 类场景。

        返回 {"content": str, "usage": {...}, "raw": {...}}。
        """
        key = self.require_config(get_settings().siliconflow_api_key, "SILICONFLOW_API_KEY")
        body = {
            "model": model.model_code,
            "messages": messages,
            "stream": False,
            **self.model_params(model, {"temperature": 0.7, "max_tokens": 1024}),
        }

        def validate(resp: httpx.Response) -> None:
            if resp.status_code >= 400:
                raise self._map_http_error(resp.status_code, resp.text)

        resp = await self._post_with_retry(
            f"{BASE_URL}/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json_body=body,
            model_type="text",
            validate=validate,
        )
        data = resp.json()
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError("provider_bad_response", "模型服务返回格式异常", resp.text[:500]) from exc
        return {"content": content, "usage": data.get("usage", {}), "raw": data}

    async def health_check(self, model) -> dict:
        """用一条 1 token 的最小请求探活。"""
        start = time.monotonic()
        try:
            await self.generate_text_once(
                model,
                [{"role": "user", "content": "ping"}],
                params={"max_tokens": 1},
            )
            return {"ok": True, "latency_ms": int((time.monotonic() - start) * 1000)}
        except ProviderError:
            return {"ok": False, "latency_ms": int((time.monotonic() - start) * 1000)}

    # ---------- 图像 / 声音 / 视频(WP04 / WP07 实现) ----------

    async def generate_image(self, model, prompt: str, params: dict | None = None) -> dict:
        raise NotImplementedError("图像通路在 WP04 实现 siliconflow /v1/images/generations")

    async def generate_audio_clone(self, model, params: dict | None = None) -> dict:
        raise NotImplementedError("声音克隆在 WP07 实现")

    async def generate_asr(self, model, audio_url: str, params: dict | None = None) -> dict:
        raise NotImplementedError("语音识别在 WP07 实现")

    async def generate_video(self, model, prompt: str, params: dict | None = None) -> dict:
        raise NotImplementedError("视频任务在 WP07 实现")
