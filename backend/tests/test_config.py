"""验收标准4:环境变量缺失时报错明确 + Online 缺 Key 的懒校验。"""
import asyncio
from types import SimpleNamespace

import pytest

from app.core.config import Settings
from app.providers.exceptions import ProviderError
from app.providers.factory import get_provider


def test_missing_required_env_raises_with_var_name(monkeypatch):
    for var in ("DATABASE_URL", "SECRET_KEY"):
        monkeypatch.delenv(var, raising=False)
    with pytest.raises(Exception) as e:
        Settings(_env_file=None)
    msg = str(e.value).lower()
    assert "database_url" in msg and "secret_key" in msg  # 明确提示缺哪个变量


def test_online_missing_key_raises_chinese_error(monkeypatch):
    monkeypatch.setenv("SILICONFLOW_API_KEY", "")
    online = get_provider(SimpleNamespace(vendor="siliconflow"))
    model = SimpleNamespace(id=2, vendor="siliconflow", model_code="Qwen/Qwen2.5-7B-Instruct")

    async def consume():
        async for _ in online.generate_text(model, [{"role": "user", "content": "hi"}]):
            pass

    with pytest.raises(ProviderError) as e:
        asyncio.run(consume())  # async generator 惰性执行,需迭代才触发校验
    assert e.value.code == "provider_not_configured"
    assert "SILICONFLOW_API_KEY" in e.value.message_zh
