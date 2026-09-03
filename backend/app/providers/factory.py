"""Provider 工厂:按 models.vendor 返回单例 Provider;未知 vendor 回退到通用 OpenAI 兼容 Provider。"""
from .base import BaseProvider
from .dashscope import DashScopeProvider
from .local import LocalProvider
from .mock import MockProvider
from .online import OnlineProvider
from .openai_compat import OpenAICompatProvider

_REGISTRY: dict[str, BaseProvider] = {
    "siliconflow": OnlineProvider(),
    "dashscope": DashScopeProvider(),
    "ollama": LocalProvider(),
    "mock": MockProvider(),
}

# 自定义供应商(后台管理添加的 vendor)统一走通用 OpenAI 兼容 Provider,
# base_url(endpoint) 与 api_key 从 models 表对应行读取。
_openai_compat = OpenAICompatProvider()


def get_provider(model) -> BaseProvider:
    """model: app.models.model.Model 行(或带 vendor 属性的对象)。

    内置 vendor 走各自 Provider;未知 vendor 视为自定义供应商,回退到
    OpenAI 兼容 Provider(从模型 endpoint + api_key 读配置)。
    """
    vendor = getattr(model, "vendor", None)
    provider = _REGISTRY.get(vendor)
    if provider is not None:
        return provider
    return _openai_compat
