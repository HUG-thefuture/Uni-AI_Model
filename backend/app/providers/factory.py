"""Provider 工厂:按 models.vendor 返回单例 Provider;未知 vendor 抛 ProviderError。"""
from app.providers.base import BaseProvider
from app.providers.exceptions import ProviderError
from app.providers.local import LocalProvider
from app.providers.mock import MockProvider
from app.providers.online import OnlineProvider

_REGISTRY: dict[str, BaseProvider] = {
    "siliconflow": OnlineProvider(),
    "ollama": LocalProvider(),
    "mock": MockProvider(),
}


def get_provider(model) -> BaseProvider:
    """model: app.models.model.Model 行(或带 vendor 属性的对象)。"""
    vendor = getattr(model, "vendor", None)
    provider = _REGISTRY.get(vendor)
    if provider is None:
        raise ProviderError(
            "provider_unknown_vendor",
            f"未知的模型提供方「{vendor}」,请检查 models 表 vendor 字段",
        )
    return provider
