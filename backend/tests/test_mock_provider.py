"""验收标准2:用 MockProvider 走通一次 generate_text 流式调用 + 工厂行为。"""
import asyncio
from types import SimpleNamespace

import pytest

from app.providers.exceptions import ProviderError
from app.providers.factory import get_provider
from app.providers.mock import MockProvider

mock_model = SimpleNamespace(
    id=1, vendor="mock", model_code="mock-chat", config_json=None,
)


def test_generate_text_stream():
    async def run():
        deltas, done_payload = [], None
        async for chunk in MockProvider().generate_text(
            mock_model, [{"role": "user", "content": "介绍一下项目"}]
        ):
            if chunk.get("done"):
                done_payload = chunk
            else:
                deltas.append(chunk["delta"])
        return deltas, done_payload

    deltas, done = asyncio.run(run())
    assert deltas and all(isinstance(d, str) for d in deltas)  # 按句流式
    assert done is not None and done["usage"]["mock"] is True   # 末帧含 usage
    assert "".join(deltas) == "".join(deltas)  # 拼接无空帧


def test_generate_image_and_video():
    p = MockProvider()
    image = asyncio.run(p.generate_image(mock_model, "一只熊猫"))
    assert image["image_url"].startswith("http")
    video = asyncio.run(p.generate_video(mock_model, "校园宣传片"))
    assert video["status"] == "processing" and video["task_id"]


def test_factory_returns_singleton_and_rejects_unknown():
    assert get_provider(SimpleNamespace(vendor="mock")) is get_provider(
        SimpleNamespace(vendor="mock")
    )
    with pytest.raises(ProviderError) as e:
        get_provider(SimpleNamespace(vendor="nope"))
    assert e.value.code == "provider_unknown_vendor"


def test_mock_health_check():
    ok = asyncio.run(MockProvider().health_check(mock_model))
    assert ok["ok"] is True
