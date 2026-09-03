"""DashScopeProvider:对接阿里云百炼(DashScope),使用 OpenAI 兼容 + 原协议混合通路。

设计原则(与 OnlineProvider 对齐):
- 密钥从环境变量 DASHSCOPE_API_KEY 读取,绝不硬编码、绝不入库;
- 文本走 OpenAI 兼容模式(Base:https://dashscope.aliyuncs.com/compatible-mode/v1),
  与硅基流动协议一致,复用同一套流式/非流式解析;
- 图像(通义万相 wanx)、语音(qwen-tts / paraformer)走百炼原协议
  (https://dashscope.aliyuncs.com/api/v1/...),文生图为异步提交 + 任务轮询;
- 所有异常统一转 ProviderError,禁止泄漏原始堆栈。

免费额度模型:
  - 文本:qwen-plus / qwen-turbo / qwen-flash
  - 文生图:wanx2.1-t2i-turbo
  - 语音合成:qwen-tts
  - 语音识别:paraformer-realtime-v2
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

logger = logging.getLogger("app.provider.dashscope")

# OpenAI 兼容端点(文本)
OPENAI_BASE = "https://dashscope.aliyuncs.com/compatible-mode/v1"
# 原协议端点(图像/语音)
NATIVE_BASE = "https://dashscope.aliyuncs.com/api/v1"

# 文生图异步提交/查询
IMAGE_SUBMIT_URL = f"{NATIVE_BASE}/services/aigc/text2image/image-synthesis"
TASK_QUERY_URL = f"{NATIVE_BASE}/tasks"
# 语音合成(qwen-tts,原协议)
TTS_URL = f"{NATIVE_BASE}/services/aigc/multimodal-generation/generation"
# 语音识别(paraformer,multipart 二进制上传)
ASR_URL = f"{NATIVE_BASE}/services/audio/asr/transcription"


class DashScopeProvider(BaseProvider):
    vendor = "dashscope"

    # ---------- 密钥 ----------

    def _key(self) -> str:
        return self.require_config(get_settings().dashscope_api_key, "DASHSCOPE_API_KEY")

    def _headers(self, *, extra: dict | None = None) -> dict:
        h = {"Authorization": f"Bearer {self._key()}", "Content-Type": "application/json"}
        if extra:
            h.update(extra)
        return h

    async def _get_json(self, url: str, model_type: str) -> dict:
        """GET 请求(带重试),用于查询异步任务状态;返回解析后的 JSON。"""
        s = get_settings()
        retries = max(0, s.provider_max_retries)
        last_exc: Exception | None = None
        for attempt in range(retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self._timeout(model_type)) as client:
                    resp = await client.get(url, headers=self._headers())
                if resp.status_code >= 400:
                    raise self._map_http_error(resp.status_code, resp.text)
                return resp.json()
            except ProviderError:
                raise
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                if attempt < retries:
                    await asyncio.sleep(2 ** attempt)
        raise self._translate(last_exc or Exception("unknown"))

    # ---------- 文本(OpenAI 兼容) ----------

    async def generate_text(
        self, model, messages: list[dict], params: dict | None = None
    ) -> AsyncIterator[dict]:
        """流式对话。yield {"delta": str} ... 最后 yield {"done": True, "usage": {...}}。"""
        body = {
            "model": model.model_code,
            "messages": messages,
            "stream": True,
            **self.model_params(model, {"temperature": 0.7, "max_tokens": 1024}),
        }
        client, resp = await self._open_stream_with_retry(
            f"{OPENAI_BASE}/chat/completions",
            headers=self._headers(),
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
        """非流式对话:一次拿到完整结果,返回 {"content", "usage", "raw"}。"""
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
            f"{OPENAI_BASE}/chat/completions",
            headers=self._headers(),
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

    # ---------- 文生图(wanx 异步提交 + 轮询) ----------

    async def generate_image(self, model, prompt: str, params: dict | None = None) -> dict:
        """文生图:异步提交 wanx 任务,内部轮询至 SUCCEEDED 后返回 {"image_urls": [...]}。

        - 提交需 X-DashScope-Async: enable,返回 output.task_id;
        - GET /api/v1/tasks/{task_id} 轮询 task_status(SUCCEEDED / FAILED / PENDING / RUNNING);
        - 结果图 URL 落到 upload_dir 本地化(OSS 签名 URL 会过期),返回 /static/<名>。
        """
        import base64
        import uuid as _uuid

        params = params or {}
        try:
            n = int(params.get("num") or 1)
        except (TypeError, ValueError):
            n = 1
        n = max(1, min(4, n))
        size = params.get("image_size") or "1024*1024"
        body = {
            "model": model.model_code,
            "input": {"prompt": prompt},
            "parameters": {"size": size, "n": n},
        }

        def validate(resp: httpx.Response) -> None:
            if resp.status_code >= 400:
                raise self._map_http_error(resp.status_code, resp.text)

        resp = await self._post_with_retry(
            IMAGE_SUBMIT_URL,
            headers=self._headers(extra={"X-DashScope-Async": "enable"}),
            json_body=body,
            model_type="image",
            validate=validate,
        )
        data = resp.json()
        task_id = (data.get("output") or {}).get("task_id")
        if not task_id:
            raise ProviderError("provider_bad_response", "文生图服务未返回任务句柄", resp.text[:500])

        result = await self._poll_image_task(task_id)
        # 把远端图下载落盘,避免 OSS 签名 URL 过期
        urls: list[str] = []
        upload_dir = get_settings().upload_path
        upload_dir.mkdir(parents=True, exist_ok=True)
        for src in result.get("results", []):
            url = src.get("url")
            if not url:
                continue
            if src.get("code") == "Base64" and src.get("orig_prompt"):
                # 少数情况下返回 base64,解码落盘
                try:
                    raw = base64.b64decode(url)
                except (ValueError, TypeError):
                    continue
                filename = f"wanx_{_uuid.uuid4().hex}.png"
                (upload_dir / filename).write_bytes(raw)
                urls.append(f"/static/{filename}")
            else:
                # 下载 URL 落盘
                local = await self._download_image(url)
                if local:
                    urls.append(local)
        if not urls:
            raise ProviderError("provider_bad_response", "文生图服务未返回图像", json.dumps(data)[:500])
        return {"image_urls": urls, "raw": data}

    async def _poll_image_task(self, task_id: str, interval: float = 2.0, max_sec: float = 110.0) -> dict:
        """轮询 wanx 任务结果,SUCCEEDED 返回 {"results": [...]},否则超时抛错。"""
        deadline = time.monotonic() + max_sec
        while time.monotonic() < deadline:
            await asyncio.sleep(interval)
            data = await self._get_json(f"{TASK_QUERY_URL}/{task_id}", "image")
            output = data.get("output") or {}
            status = output.get("task_status")
            if status == "SUCCEEDED":
                return output
            if status == "FAILED":
                raise ProviderError("provider_upstream", "文生图生成失败", json.dumps(data)[:500])
            # PENDING / RUNNING 继续轮询
        raise ProviderError("provider_timeout", "文生图生成超时,本次不扣费")

    async def _download_image(self, url: str) -> str | None:
        """下载一张图落盘到 upload_dir,返回 /static/<名>;失败返回 None。"""
        import uuid as _uuid

        try:
            async with httpx.AsyncClient(timeout=self._timeout("image"), follow_redirects=True) as c:
                r = await c.get(url)
                r.raise_for_status()
                data = r.content
        except httpx.HTTPError as exc:
            logger.warning("文生图结果下载失败: %s", exc)
            return None
        filename = f"wanx_{_uuid.uuid4().hex}.png"
        upload_dir = get_settings().upload_path
        upload_dir.mkdir(parents=True, exist_ok=True)
        (upload_dir / filename).write_bytes(data)
        return f"/static/{filename}"

    # ---------- 语音合成 TTS(qwen-tts) ----------

    async def generate_audio_clone(self, model, params: dict | None = None) -> dict:
        """声音合成:POST multimodal-generation(generation),返回音频 URL 落盘为 /static/<名>。

        params.text 为合成文本;返回值 {"audio_url": "/static/...", "raw": ...}。
        """
        params = params or {}
        text = (params.get("text") or "").strip()
        if not text:
            raise ProviderError("invalid_params", "声音合成缺少文本内容")
        body = {"model": model.model_code, "input": {"text": text}}

        def validate(resp: httpx.Response) -> None:
            if resp.status_code >= 400:
                raise self._map_http_error(resp.status_code, resp.text)

        resp = await self._post_with_retry(
            TTS_URL,
            headers=self._headers(),
            json_body=body,
            model_type="audio",
            validate=validate,
        )
        data = resp.json()
        output = data.get("output") or {}
        audio = output.get("audio") or {}
        url = audio.get("url")
        if not url:
            raise ProviderError("provider_bad_response", "声音服务未返回音频地址", resp.text[:500])

        # 下载 OSS 音频落盘,避免签名 URL 过期
        audio_url = await self._download_remote_audio(url)
        return {"audio_url": audio_url, "raw": data}

    async def _download_remote_audio(self, url: str) -> str:
        """下载远程音频到 upload_dir,返回 /static/<名>;失败抛 ProviderError。"""
        import uuid as _uuid

        try:
            async with httpx.AsyncClient(timeout=self._timeout("audio"), follow_redirects=True) as c:
                r = await c.get(url)
                r.raise_for_status()
                content = r.content
        except httpx.HTTPError as exc:
            raise ProviderError("audio_download_failed", "音频下载失败,请稍后重试", str(exc)) from exc
        if not content:
            raise ProviderError("provider_bad_response", "声音服务未返回音频内容", url[:200])
        filename = f"tts_{_uuid.uuid4().hex[:12]}.wav"
        upload_dir = get_settings().upload_path
        upload_dir.mkdir(parents=True, exist_ok=True)
        (upload_dir / filename).write_bytes(content)
        return f"/static/{filename}"

    # ---------- 语音识别 ASR(异步任务,file_urls 协议) ----------

    async def generate_asr(self, model, audio_url: str, params: dict | None = None) -> dict:
        """语音识别:百炼 ASR 走异步任务协议,需公网可下载的音频 URL(file_urls)。

        - audio_url 必须为公网 http(s) 可下载地址(百炼无法访问本机 localhost /static);
        - 本地 /static/<名> 会抛明确中文错误提示需先上传到公网;
        - 提交拿 task_id 后轮询 GET /api/v1/tasks/{id},SUCCEEDED 里取 text。
        """
        if audio_url.startswith("/static/"):
            raise ProviderError(
                "invalid_audio",
                "百炼语音识别需公网可访问的音频地址,本地文件请先上传到 OSS/公网后再试",
                audio_url,
            )
        if not (audio_url.startswith("http://") or audio_url.startswith("https://")):
            raise ProviderError("invalid_audio", "音频地址不合法,需 http(s) 公网地址", audio_url)

        body = {"model": model.model_code, "input": {"file_urls": [audio_url]}}

        def validate(resp: httpx.Response) -> None:
            if resp.status_code >= 400:
                raise self._map_http_error(resp.status_code, resp.text)

        resp = await self._post_with_retry(
            ASR_URL,
            headers=self._headers(extra={"X-DashScope-Async": "enable"}),
            json_body=body,
            model_type="audio",
            validate=validate,
        )
        data = resp.json()
        task_id = (data.get("output") or {}).get("task_id")
        if not task_id:
            raise ProviderError("provider_bad_response", "语音识别服务未返回任务句柄", resp.text[:500])

        text = await self._poll_asr_task(task_id)
        return {"text": text, "raw": data}

    async def _poll_asr_task(self, task_id: str, interval: float = 2.0, max_sec: float = 120.0) -> str:
        """轮询 ASR 任务,SUCCEEDED 返回转写 text,否则超时/失败抛错。"""
        deadline = time.monotonic() + max_sec
        while time.monotonic() < deadline:
            await asyncio.sleep(interval)
            data = await self._get_json(f"{TASK_QUERY_URL}/{task_id}", "audio")
            output = data.get("output") or {}
            status = output.get("task_status")
            if status == "SUCCEEDED":
                text = output.get("text")
                if text is None:
                    raise ProviderError("provider_bad_response", "语音识别返回格式异常", json.dumps(data)[:500])
                return str(text)
            if status == "FAILED":
                raise ProviderError("provider_upstream", "语音识别失败", json.dumps(data)[:500])
        raise ProviderError("provider_timeout", "语音识别超时,本次不扣费")

    # ---------- 视频(暂不实现,复用基类契约) ----------

    async def generate_video(self, model, prompt: str, params: dict | None = None) -> dict:
        """DashScope 本期不接视频,统一按「接口未就绪」处理(任务失败不扣费)。"""
        raise ProviderError(
            "provider_not_ready", "阿里云百炼视频接口本期未接入,请使用 Mock 模型演示"
        )