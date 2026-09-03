"""OpenAICompatProvider:通用 OpenAI 兼容供应商适配器。

用于后台自定义供应商:base_url(endpoint) 与 api_key 存于 models 表,本 Provider
从模型行读取配置,按 OpenAI 兼容协议调用(chat/completions 流式/非流式、
images/generations 文生图)。内置供应商(siliconflow/dashscope)仍走各自 Provider,
本 Provider 仅作为 vendor 不在内置注册表时的通用回退。
"""
import json
import logging
import time
from typing import AsyncIterator

import httpx

from .base import BaseProvider
from .exceptions import ProviderError

logger = logging.getLogger("app.provider.openai_compat")


class OpenAICompatProvider(BaseProvider):
    vendor = "openai_compat"  # 通用回退供应商;实际 vendor 取模型行

    # ---------- 配置 ----------

    def _base_url(self, model) -> str:
        endpoint = getattr(model, "endpoint", None)
        if not endpoint:
            raise ProviderError(
                "provider_not_configured", "自定义供应商未配置 endpoint(base_url)"
            )
        return str(endpoint).rstrip("/")

    def _api_key(self, model) -> str:
        key = getattr(model, "api_key", None)
        if not key:
            raise ProviderError(
                "provider_not_configured", "自定义供应商未配置 api_key,请先在后台管理补充"
            )
        return str(key)

    def _headers(self, model, *, extra: dict | None = None) -> dict:
        h = {"Authorization": f"Bearer {self._api_key(model)}", "Content-Type": "application/json"}
        if extra:
            h.update(extra)
        return h

    # ---------- 文本(OpenAI 兼容) ----------

    async def generate_text(
        self, model, messages: list[dict], params: dict | None = None
    ) -> AsyncIterator[dict]:
        """流式对话:POST {base_url}/chat/completions (stream=true)。"""
        body = {
            "model": model.model_code,
            "messages": messages,
            "stream": True,
            **self.model_params(model, {"temperature": 0.7, "max_tokens": 1024}),
        }
        client, resp = await self._open_stream_with_retry(
            f"{self._base_url(model)}/chat/completions",
            headers=self._headers(model),
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
        """非流式对话:一次拿到完整结果。"""
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
            f"{self._base_url(model)}/chat/completions",
            headers=self._headers(model),
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
                model, [{"role": "user", "content": "ping"}], params={"max_tokens": 1}
            )
            return {"ok": True, "latency_ms": int((time.monotonic() - start) * 1000)}
        except ProviderError:
            return {"ok": False, "latency_ms": int((time.monotonic() - start) * 1000)}

    # ---------- 文生图(OpenAI 兼容 images/generations) ----------

    async def generate_image(self, model, prompt: str, params: dict | None = None) -> dict:
        """文生图:POST {base_url}/images/generations(部分供应商支持,失败抛明确错误)。"""
        import base64
        import uuid as _uuid

        from ..core.config import get_settings

        params = params or {}
        size = params.get("image_size") or "1024x1024"
        try:
            n = int(params.get("num") or 1)
        except (TypeError, ValueError):
            n = 1
        n = max(1, min(4, n))
        body = {"model": model.model_code, "prompt": prompt, "size": size, "n": n}

        def validate(resp: httpx.Response) -> None:
            if resp.status_code >= 400:
                raise self._map_http_error(resp.status_code, resp.text)

        resp = await self._post_with_retry(
            f"{self._base_url(model)}/images/generations",
            headers=self._headers(model),
            json_body=body,
            model_type="image",
            validate=validate,
        )
        data = resp.json()
        urls: list[str] = []
        upload_dir = get_settings().upload_path
        upload_dir.mkdir(parents=True, exist_ok=True)
        for item in data.get("data") or []:
            if item.get("url"):
                local = await self._download_image(item["url"], upload_dir)
                if local:
                    urls.append(local)
            elif item.get("b64_json"):
                try:
                    raw = base64.b64decode(item["b64_json"])
                except (ValueError, TypeError):
                    continue
                filename = f"ocimg_{_uuid.uuid4().hex}.png"
                (upload_dir / filename).write_bytes(raw)
                urls.append(f"/static/{filename}")
        if not urls:
            raise ProviderError("provider_bad_response", "文生图服务未返回图像", resp.text[:500])
        return {"image_urls": urls, "raw": data}

    async def _download_image(self, url: str, upload_dir) -> str | None:
        import uuid as _uuid

        try:
            async with httpx.AsyncClient(timeout=self._timeout("image"), follow_redirects=True) as c:
                r = await c.get(url)
                r.raise_for_status()
                data = r.content
        except httpx.HTTPError as exc:
            logger.warning("文生图结果下载失败: %s", exc)
            return None
        filename = f"ocimg_{_uuid.uuid4().hex}.png"
        (upload_dir / filename).write_bytes(data)
        return f"/static/{filename}"

    # ---------- 未实现的能力 ----------

    async def generate_audio_clone(self, model, params: dict | None = None) -> dict:
        raise ProviderError("provider_not_ready", "该自定义供应商未接入语音合成能力")

    async def generate_asr(self, model, audio_url: str, params: dict | None = None) -> dict:
        raise ProviderError("provider_not_ready", "该自定义供应商未接入语音识别能力")

    async def generate_video(self, model, prompt: str, params: dict | None = None) -> dict:
        raise ProviderError("provider_not_ready", "该自定义供应商未接入视频能力")