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

    # ---------- 图像(WP04)/ 声音 / 视频(WP07 实现) ----------

    async def generate_image(self, model, prompt: str, params: dict | None = None) -> dict:
        """文生图:POST /v1/images/generations(读取超时取 self._timeout("image") = 120s)。

        params 支持 image_size(默认 1024x1024)、num(1..4,默认 1,映射 batch_size)。
        返回与 MockProvider 统一的结构 {"image_urls": [str], "raw": {...}}:
        - 上游返回 {"images":[{"url":...}]} 时直接透传 URL;
        - 返回 {"images":[{"b64_json":...}]} 时解码保存到 settings.upload_dir,
          返回本地 /static/<文件名> URL。
        """
        import base64
        import uuid as _uuid
        from pathlib import Path

        key = self.require_config(get_settings().siliconflow_api_key, "SILICONFLOW_API_KEY")
        params = params or {}
        image_size = params.get("image_size") or "1024x1024"
        try:
            batch_size = int(params.get("num") or 1)
        except (TypeError, ValueError):
            batch_size = 1
        batch_size = max(1, min(4, batch_size))
        body = {
            "model": model.model_code,
            "prompt": prompt,
            "image_size": image_size,
            "batch_size": batch_size,
        }

        def validate(resp: httpx.Response) -> None:
            if resp.status_code >= 400:
                raise self._map_http_error(resp.status_code, resp.text)

        resp = await self._post_with_retry(
            f"{BASE_URL}/v1/images/generations",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json_body=body,
            model_type="image",
            validate=validate,
        )
        data = resp.json()
        upload_dir = Path(get_settings().upload_dir)
        upload_dir.mkdir(parents=True, exist_ok=True)
        urls: list[str] = []
        for item in data.get("images") or []:
            if item.get("url"):
                urls.append(str(item["url"]))
            elif item.get("b64_json"):
                filename = f"img_{_uuid.uuid4().hex}.png"
                try:
                    (upload_dir / filename).write_bytes(base64.b64decode(item["b64_json"]))
                except (ValueError, OSError) as exc:
                    raise ProviderError(
                        "provider_bad_response", "图像保存失败,请稍后重试", str(exc)
                    ) from exc
                urls.append(f"/static/{filename}")
        if not urls:
            raise ProviderError(
                "provider_bad_response", "模型服务返回格式异常,未包含图像", resp.text[:500]
            )
        return {"image_urls": urls, "raw": data}

    async def generate_audio_clone(self, model, params: dict | None = None) -> dict:
        raise NotImplementedError("声音克隆在 WP07 实现")

    async def generate_asr(self, model, audio_url: str, params: dict | None = None) -> dict:
        raise NotImplementedError("语音识别在 WP07 实现")

    async def generate_video(self, model, prompt: str, params: dict | None = None) -> dict:
        raise NotImplementedError("视频任务在 WP07 实现")
