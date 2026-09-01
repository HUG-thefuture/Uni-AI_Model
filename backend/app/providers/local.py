"""LocalProvider:Ollama 本地模型(WP08,OpenAI 兼容路径 /v1)。

- generate_text:POST {OLLAMA_BASE_URL}/v1/chat/completions,stream=true,
  解析 SSE 增量(data: {...choices[].delta.content...})直到 [DONE];
- generate_text_once:非流式通路,返回 {"content", "usage", "raw"},与 OnlineProvider
  同构,开放接口 / 调用方无感;
- 超时/重试复用 BaseProvider 的 _open_stream_with_retry / _post_with_retry
  (与线上模型同套 config);本地服务无需鉴权头;
- 连接失败(httpx.ConnectError)定制中文提示:「本地模型服务未启动,请联系管理员」;
- 图像/声音/视频任务类型不支持,统一抛 provider_not_supported;
- health_check:GET /api/tags 探活,返回 {"ok", "latency_ms", "models"};
- probe_available:门户列表「在线/离线」轻量探活(httpx GET /api/tags,2s 超时,
  模块级缓存 60s,key=vendor+endpoint),失败/超时返回 False 且不抛异常。
"""
import json
import logging
import time
from typing import AsyncIterator

import httpx

from ..core.config import get_settings
from .base import BaseProvider
from .exceptions import ProviderError

logger = logging.getLogger("app.provider.local")

# 连接失败(服务未启动)的定制中文提示
LOCAL_UNREACHABLE_ZH = "本地模型服务未启动,请联系管理员"

# 门户 available 探活:2 秒超时,结果缓存 60 秒
PROBE_TIMEOUT_SEC = 2
PROBE_TTL_SEC = 60

# 模块级探活缓存:{key: (monotonic 时间戳, available)};key = "ollama:<endpoint>"
_PROBE_CACHE: dict[str, tuple[float, bool]] = {}


class LocalProvider(BaseProvider):
    vendor = "ollama"

    @property
    def base_url(self) -> str:
        return get_settings().ollama_base_url.rstrip("/")

    def _endpoint_for(self, model) -> str:
        """调用端点:优先 models.endpoint(管理端可配),为空回退 OLLAMA_BASE_URL。"""
        endpoint = (getattr(model, "endpoint", None) or "").strip()
        return endpoint.rstrip("/") if endpoint else self.base_url

    def _timeout(self, model_type: str) -> httpx.Timeout:
        """覆写基类超时构造:httpx 0.28 要求 Timeout 必须有 default 或四参齐全。

        语义不变:connect 取 provider_connect_timeout,read/write/pool 按任务类型
        取 read_timeouts(文本 60s / 图像 120s / 音视频 300s)。
        (基类 BaseProvider._timeout 在 httpx 0.28 下会抛
        「Timeout must either include a default, or set all four parameters
        explicitly」,Online 同样受影响,待统一修复。)
        """
        s = get_settings()
        read = s.read_timeouts.get(model_type, 60)
        return httpx.Timeout(read, connect=s.provider_connect_timeout)

    # ---------- 异常翻译:ConnectError 定制中文提示 ----------

    @staticmethod
    def _translate(exc: Exception) -> ProviderError:
        """覆写 BaseProvider._translate:连接失败给出「本地模型服务未启动」。"""
        if isinstance(exc, httpx.ConnectError):
            return ProviderError("provider_unreachable", LOCAL_UNREACHABLE_ZH, str(exc))
        return BaseProvider._translate(exc)

    # ---------- 文本:流式与非流式(与 OnlineProvider 同构) ----------

    async def generate_text(
        self, model, messages: list[dict], params: dict | None = None
    ) -> AsyncIterator[dict]:
        """流式对话。yield {"delta": str} ... 最后 yield {"done": True, "usage": {...}}。"""
        body = {
            "model": model.model_code,
            "messages": messages,
            "stream": True,
            **self.model_params(model, {"temperature": 0.7}),
        }
        client, resp = await self._open_stream_with_retry(
            f"{self._endpoint_for(model)}/v1/chat/completions",
            # 本地服务无需鉴权:不带 Authorization,仅 Content-Type
            headers={"Content-Type": "application/json"},
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
                    logger.warning("Ollama SSE 增量解析失败,跳过: %s", payload[:200])
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
        """非流式对话:一次拿到完整结果,返回 {"content": str, "usage": {...}, "raw": {...}}。"""
        body = {
            "model": model.model_code,
            "messages": messages,
            "stream": False,
            **self.model_params(model, {"temperature": 0.7}),
        }

        def validate(resp: httpx.Response) -> None:
            if resp.status_code >= 400:
                raise self._map_http_error(resp.status_code, resp.text)

        resp = await self._post_with_retry(
            f"{self._endpoint_for(model)}/v1/chat/completions",
            headers={"Content-Type": "application/json"},
            json_body=body,
            model_type="text",
            validate=validate,
        )
        data = resp.json()
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError(
                "provider_bad_response", "本地模型服务返回格式异常", resp.text[:500]
            ) from exc
        return {"content": content, "usage": data.get("usage", {}), "raw": data}

    # ---------- 探活 ----------

    async def health_check(self, model) -> dict:
        """探活:GET {base}/api/tags,Ollama 就绪即可达。

        返回 {"ok": bool, "latency_ms": int, "models": [名称列表]};失败 models 为空。
        """
        start = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=self._timeout("text")) as client:
                resp = await client.get(f"{self._endpoint_for(model)}/api/tags")
            latency_ms = int((time.monotonic() - start) * 1000)
            if resp.status_code >= 400:
                return {"ok": False, "latency_ms": latency_ms, "models": []}
            try:
                names = [
                    str(m.get("name", ""))
                    for m in (resp.json().get("models") or [])
                    if isinstance(m, dict)
                ]
            except ValueError:
                names = []
            return {"ok": True, "latency_ms": latency_ms, "models": names}
        except httpx.HTTPError:
            return {
                "ok": False,
                "latency_ms": int((time.monotonic() - start) * 1000),
                "models": [],
            }

    @staticmethod
    def probe_available(endpoint: str | None) -> bool:
        """门户列表轻量探活(httpx GET {endpoint}/api/tags,2s 超时)。

        - 模块级缓存 60 秒,key=vendor+endpoint,缓存期内不发请求;
        - 失败/超时返回 False,异常全部吞掉(不阻塞模型列表返回);
        - sync 实现:门户列表为 def 路由(FastAPI 线程池执行),不占事件循环。
        """
        normalized = (endpoint or "").strip().rstrip("/")
        key = f"ollama:{normalized}"
        now = time.monotonic()
        cached = _PROBE_CACHE.get(key)
        if cached is not None and now - cached[0] < PROBE_TTL_SEC:
            return cached[1]
        target = normalized or get_settings().ollama_base_url.rstrip("/")
        available = False
        try:
            resp = httpx.get(f"{target}/api/tags", timeout=PROBE_TIMEOUT_SEC)
            available = resp.status_code < 400
        except Exception:  # noqa: BLE001 探活失败不阻塞列表,统一按离线处理
            available = False
        _PROBE_CACHE[key] = (now, available)
        return available

    # ---------- 不支持的任务类型 ----------

    def _not_supported(self) -> ProviderError:
        return ProviderError("provider_not_supported", "该模型不支持该任务类型")

    async def generate_image(self, model, prompt: str, params: dict | None = None) -> dict:
        raise self._not_supported()

    async def generate_audio_clone(self, model, params: dict | None = None) -> dict:
        raise self._not_supported()

    async def generate_asr(self, model, audio_url: str, params: dict | None = None) -> dict:
        raise self._not_supported()

    async def generate_video(self, model, prompt: str, params: dict | None = None) -> dict:
        raise self._not_supported()
