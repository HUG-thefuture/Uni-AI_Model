"""BaseProvider 抽象基类:所有模型适配器(Online/Local/Mock)的统一契约。

统一约束(全组红线相关):
- 全部 async,httpx 异步调用;
- 连接超时 10s,读取超时按任务类型取自配置(文本 60s / 图像 120s / 音视频 300s);
- 失败重试最多 2 次(仅限未产生部分输出的幂等请求,指数退避 1s/2s);
- 所有异常转换为 ProviderError(code, message_zh, raw),禁止向上泄漏原始堆栈;
- 调用日志(request_id、耗时、结果)由 services/call_log.py 统一落库 ai_call_logs。
"""
import asyncio
import abc
import logging
from typing import Any, AsyncIterator, Callable

import httpx

from app.core.config import get_settings
from app.providers.exceptions import ProviderError

logger = logging.getLogger("app.provider")

_RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class BaseProvider(abc.ABC):
    """适配器基类。vendor 见 models.vendor:siliconflow / ollama / mock。"""

    vendor: str = "base"

    # ---------- 抽象接口 ----------

    @abc.abstractmethod
    async def generate_text(
        self, model, messages: list[dict], params: dict | None = None
    ) -> AsyncIterator[dict]:
        """流式文本:逐段 yield {"delta": "..."},结束时 yield {"done": True, "usage": {...}}。"""
        raise NotImplementedError
        yield  # pragma: no cover

    @abc.abstractmethod
    async def generate_image(self, model, prompt: str, params: dict | None = None) -> dict:
        """返回 {"image_url": ..., "raw": ...}。"""
        raise NotImplementedError

    @abc.abstractmethod
    async def generate_audio_clone(self, model, params: dict | None = None) -> dict:
        """声音克隆:返回 {"audio_url": ..., "raw": ...}。"""
        raise NotImplementedError

    @abc.abstractmethod
    async def generate_asr(self, model, audio_url: str, params: dict | None = None) -> dict:
        """语音识别:返回 {"text": ..., "raw": ...}。"""
        raise NotImplementedError

    @abc.abstractmethod
    async def generate_video(self, model, prompt: str, params: dict | None = None) -> dict:
        """长耗时视频:返回任务句柄 {"task_id": ..., "status": ..., "raw": ...}。"""
        raise NotImplementedError

    @abc.abstractmethod
    async def health_check(self, model) -> dict:
        """返回 {"ok": bool, "latency_ms": int}。"""
        raise NotImplementedError

    # ---------- 公共工具:超时 / 重试 / 异常转换 ----------

    def _timeout(self, model_type: str) -> httpx.Timeout:
        s = get_settings()
        return httpx.Timeout(
            connect=s.provider_connect_timeout, read=s.read_timeouts.get(model_type, 60)
        )

    @staticmethod
    def _translate(exc: Exception) -> ProviderError:
        """httpx 异常 → ProviderError(统一中文提示)。"""
        if isinstance(exc, httpx.TimeoutException):
            return ProviderError("provider_timeout", "模型服务响应超时,请稍后重试", str(exc))
        if isinstance(exc, httpx.ConnectError):
            return ProviderError("provider_unreachable", "无法连接模型服务,请检查网络或服务状态", str(exc))
        return ProviderError("provider_unknown", "模型服务调用失败,请稍后重试", str(exc))

    async def _post_with_retry(
        self,
        url: str,
        *,
        headers: dict,
        json_body: dict,
        model_type: str,
        validate: Callable[[httpx.Response], None] | None = None,
    ) -> httpx.Response:
        """非流式 POST:带重试(最多 provider_max_retries 次,指数退避 1s/2s)。

        validate(response) 用于把 4xx 等业务错误转换成 ProviderError;
        只有「请求未产生任何结果」的错误才值得重试。
        """
        s = get_settings()
        retries = max(0, s.provider_max_retries)
        last_exc: Exception | None = None
        for attempt in range(retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self._timeout(model_type)) as client:
                    resp = await client.post(url, headers=headers, json=json_body)
                if validate:
                    validate(resp)  # 抛 ProviderError(不可重试类)或直接通过
                if resp.status_code in _RETRYABLE_STATUS:
                    raise httpx.HTTPStatusError(
                        f"上游 {resp.status_code}", request=resp.request, response=resp
                    )
                return resp
            except ProviderError:
                raise  # 业务类错误(鉴权/参数)不重试
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                if attempt < retries:
                    delay = 2 ** attempt  # 1s, 2s
                    logger.warning(
                        "上游调用失败(第 %s 次),%.0fs 后重试: %s", attempt + 1, delay, exc
                    )
                    await asyncio.sleep(delay)
        raise self._translate(last_exc or Exception("unknown"))

    async def _open_stream_with_retry(
        self, url: str, *, headers: dict, json_body: dict, model_type: str
    ) -> tuple[httpx.AsyncClient, httpx.Response]:
        """流式 POST:仅重试「建立连接/拿到响应头」阶段;一旦开始收到增量不再重试。

        返回 (client, resp) 二元组,resp 处于 streaming 状态;调用方结束后须依次
        await resp.aclose() 与 await client.aclose()。
        """
        s = get_settings()
        retries = max(0, s.provider_max_retries)
        last_exc: Exception | None = None
        for attempt in range(retries + 1):
            client = httpx.AsyncClient(timeout=self._timeout(model_type))
            try:
                resp = await client.send(
                    client.build_request("POST", url, headers=headers, json=json_body),
                    stream=True,
                )
                if resp.status_code in _RETRYABLE_STATUS:
                    await resp.aclose()
                    raise httpx.HTTPStatusError(
                        f"上游 {resp.status_code}", request=resp.request, response=resp
                    )
                if resp.status_code >= 400:
                    raw = (await resp.aread()).decode("utf-8", "replace")
                    await resp.aclose()
                    await client.aclose()
                    raise self._map_http_error(resp.status_code, raw)
                return client, resp  # 成功:client 生命周期交给调用方
            except ProviderError:
                await client.aclose()
                raise
            except Exception as exc:  # noqa: BLE001
                await client.aclose()
                last_exc = exc
                if attempt < retries:
                    delay = 2 ** attempt
                    logger.warning(
                        "流式连接失败(第 %s 次),%.0fs 后重试: %s", attempt + 1, delay, exc
                    )
                    await asyncio.sleep(delay)
        raise self._translate(last_exc or Exception("unknown"))

    @staticmethod
    def _map_http_error(status_code: int, raw: str) -> ProviderError:
        if status_code == 401 or status_code == 403:
            return ProviderError("provider_auth", "模型服务鉴权失败,请检查 API Key 配置", raw)
        if status_code == 429:
            return ProviderError("provider_rate_limit", "模型服务限流,请稍后重试", raw)
        return ProviderError("provider_upstream", "模型服务返回错误,请稍后重试", raw)

    def require_config(self, value: str | None, env_name: str) -> str:
        """密钥/配置懒校验:缺失时给出明确中文提示。"""
        if not value:
            raise ProviderError(
                "provider_not_configured",
                f"环境变量 {env_name} 未配置,无法调用该模型;请联系管理员或在 .env 中配置",
            )
        return value

    def model_params(self, model, default: dict[str, Any] | None = None) -> dict:
        """从 models.config_json 解析非敏感参数(温度/max_tokens 等)。"""
        import json

        params: dict = dict(default or {})
        try:
            if getattr(model, "config_json", None):
                params.update(json.loads(model.config_json))
        except (ValueError, TypeError):
            logger.warning("模型 %s config_json 解析失败,使用默认参数", getattr(model, "id", "?"))
        return params
