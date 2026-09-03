"""OnlineProvider:对接硅基流动(OpenAI 兼容协议)。

- 密钥从环境变量 SILICONFLOW_API_KEY 读取,绝不硬编码、绝不入库;
- 本工作包(WP01)实现 generate_text 的流式与非流式通路(POST /v1/chat/completions,
  stream=true 时解析 SSE 增量),图像/声音/视频方法留待 WP04/WP07 实现。
"""
import asyncio
import json
import logging
import time
from typing import AsyncIterator

import httpx

from ..core.config import get_settings
from .base import BaseProvider
from .exceptions import ProviderError

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

    # ---------- 声音 / 视频(WP07) ----------

    async def _download_audio(self, audio_url: str) -> tuple[bytes, str]:
        """按 URL 取音频字节:本地 /static/ 路径读 upload_dir,http(s) 直接下载。

        返回 (字节, 文件名);下载失败/文件缺失统一转 ProviderError。
        """
        from pathlib import Path

        if audio_url.startswith("/static/"):
            filename = Path(audio_url).name  # 只取文件名,防目录穿越
            path = Path(get_settings().upload_dir) / filename
            if not path.is_file():
                raise ProviderError("invalid_audio", "音频文件不存在,请重新上传", audio_url)
            return path.read_bytes(), filename
        try:
            async with httpx.AsyncClient(timeout=self._timeout("audio")) as client:
                resp = await client.get(audio_url)
                resp.raise_for_status()
                name = audio_url.rsplit("/", 1)[-1] or "audio.mp3"
                return resp.content, name
        except httpx.HTTPError as exc:
            raise ProviderError("audio_download_failed", "音频下载失败,请检查音频地址", str(exc)) from exc

    async def _post_multipart_with_retry(
        self, url: str, *, headers: dict, files: dict, data: dict | None, model_type: str
    ) -> httpx.Response:
        """multipart POST(语音识别上传用):重试策略与 _post_with_retry 一致。"""
        s = get_settings()
        retries = max(0, s.provider_max_retries)
        last_exc: Exception | None = None
        for attempt in range(retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self._timeout(model_type)) as client:
                    resp = await client.post(url, headers=headers, files=files, data=data)
                if resp.status_code >= 400:
                    raise self._map_http_error(resp.status_code, resp.text)  # 鉴权/参数类不重试
                if resp.status_code in (429, 500, 502, 503, 504):
                    raise httpx.HTTPStatusError(
                        f"上游 {resp.status_code}", request=resp.request, response=resp
                    )
                return resp
            except ProviderError:
                raise
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                if attempt < retries:
                    delay = 2 ** attempt
                    logger.warning("上传调用失败(第 %s 次),%.0fs 后重试: %s", attempt + 1, delay, exc)
                    await asyncio.sleep(delay)
        raise self._translate(last_exc or Exception("unknown"))

    async def generate_audio_clone(self, model, params: dict | None = None) -> dict:
        """声音克隆:POST /v1/audio/speech,响应音频二进制落盘 upload_dir。

        params 需含 text(合成文本)与可选 voice_name(默认 alloy);
        返回 {"audio_url": "/static/clone-<request_id>.mp3", "raw": {...}}。
        """
        import uuid as _uuid
        from pathlib import Path

        from ..core.request_id import current_request_id

        key = self.require_config(get_settings().siliconflow_api_key, "SILICONFLOW_API_KEY")
        params = params or {}
        text = (params.get("text") or "").strip()
        if not text:
            raise ProviderError("invalid_params", "声音克隆缺少合成文本")
        body = {
            "model": model.model_code,
            "input": text,
            "voice": params.get("voice_name", "alloy"),
            "response_format": "mp3",
        }

        def validate(resp: httpx.Response) -> None:
            if resp.status_code >= 400:
                raise self._map_http_error(resp.status_code, resp.text)

        resp = await self._post_with_retry(
            f"{BASE_URL}/v1/audio/speech",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json_body=body,
            model_type="audio",
            validate=validate,
        )
        if not resp.content:
            raise ProviderError("provider_bad_response", "声音服务未返回音频内容", resp.text[:200])
        filename = f"clone-{current_request_id()}.mp3"
        upload_dir = Path(get_settings().upload_dir)
        upload_dir.mkdir(parents=True, exist_ok=True)
        try:
            (upload_dir / filename).write_bytes(resp.content)
        except OSError as exc:
            raise ProviderError("provider_bad_response", "音频保存失败,请稍后重试", str(exc)) from exc
        return {"audio_url": f"/static/{filename}", "raw": {"mock_saved": True, "size": len(resp.content)}}

    async def generate_asr(self, model, audio_url: str, params: dict | None = None) -> dict:
        """语音识别:先按 audio_url 取音频字节,再 multipart 上传 /v1/audio/transcriptions。

        返回 {"text": 转写文本, "raw": {...}};鉴权失败等 4xx 走 _map_http_error。
        """
        key = self.require_config(get_settings().siliconflow_api_key, "SILICONFLOW_API_KEY")
        audio_bytes, filename = await self._download_audio(audio_url)
        files = {"file": (filename or "audio.mp3", audio_bytes)}
        data = {"model": model.model_code}
        resp = await self._post_multipart_with_retry(
            f"{BASE_URL}/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {key}"},
            files=files,
            data=data,
            model_type="audio",
        )
        result = resp.json()
        text = result.get("text")
        if text is None:
            raise ProviderError("provider_bad_response", "语音识别服务返回格式异常", resp.text[:500])
        return {"text": str(text), "raw": result}

    async def generate_video(self, model, prompt: str, params: dict | None = None) -> dict:
        """长文本转视频:POST /v1/video/submit 提交任务句柄,状态轮询由 task_service 负责。

        TODO:上游视频接口路径/报文本期未定,若 404/未实现则抛 provider_not_ready,
        线上模型视频任务将 failed 不扣费,由 Mock 模型兜底演示全链路。
        """
        key = self.require_config(get_settings().siliconflow_api_key, "SILICONFLOW_API_KEY")
        body = {"model": model.model_code, "prompt": prompt}
        if params:
            body.update(params)  # resolution / duration 等透传
        try:
            resp = await self._post_with_retry(
                f"{BASE_URL}/v1/video/submit",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json_body=body,
                model_type="video",
                validate=lambda r: (
                    self._map_http_error(r.status_code, r.text)
                    if r.status_code >= 400
                    else None
                ),
            )
            data = resp.json()
        except (httpx.HTTPError, ProviderError) as exc:
            # 上游未实现/404/网络不可达:统一按「接口未就绪」处理,任务失败不扣费
            raise ProviderError(
                "provider_not_ready", "上游视频接口暂不可用,请使用 Mock 模型演示", str(exc)
            ) from exc
        upstream_id = data.get("requestId") or data.get("task_id") or data.get("id") or data.get("request_id")
        if not upstream_id:
            raise ProviderError(
                "provider_bad_response", "视频服务未返回任务句柄", resp.text[:500]
            )
        return {"task_id": str(upstream_id), "status": "processing", "raw": data}

    async def query_video(self, model, handle: dict) -> dict:
        """查询 SiliconFlow 视频任务状态,统一为执行器使用的 completed/processing 语义。"""
        key = self.require_config(get_settings().siliconflow_api_key, "SILICONFLOW_API_KEY")
        request_id = handle.get("task_id") or handle.get("requestId")
        if not request_id:
            raise ProviderError("provider_bad_response", "视频服务未返回任务标识")
        resp = await self._post_with_retry(
            f"{BASE_URL}/v1/video/status",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json_body={"requestId": request_id}, model_type="video",
            validate=lambda r: self._map_http_error(r.status_code, r.text) if r.status_code >= 400 else None,
        )
        data = resp.json()
        status = str(data.get("status") or "")
        if status == "Succeed":
            videos = ((data.get("results") or {}).get("videos") or [])
            urls = [item.get("url") for item in videos if isinstance(item, dict) and item.get("url")]
            if not urls:
                raise ProviderError("provider_bad_response", "视频服务未返回视频地址", resp.text[:500])
            return {"status": "completed", "video_url": urls[0], "video_urls": urls}
        if status == "Failed":
            raise ProviderError("provider_failed", str(data.get("reason") or "视频生成失败"))
        return {"status": "processing"}
