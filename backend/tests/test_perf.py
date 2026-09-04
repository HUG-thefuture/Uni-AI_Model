"""WP09 性能固化本地测试(不进仓库验收,pytest 直接跑):
- db.py 慢查询日志:阈值 0 时任何 SQL 记 warning「慢查询」;阈值足够大时不记录;
- db.py MySQL 连接池参数固化:pool_size=20 / max_overflow=10 / pool_recycle=1800;
- core/http_client.py:懒初始化单例复用 + limits(100/20)+ 关闭后重建;
- MockProvider 显式延迟:params["mock_delay_sec"] / model.config_json /
  Settings.mock_delay_sec 三级覆盖,非法值忽略,默认保持随机分支。
"""
import asyncio
import logging
import time
from types import SimpleNamespace

import pytest
from sqlalchemy import text

from app.core import db as db_module
from app.core.config import get_settings
from app.core.http_client import close_http_client, get_http_client
from app.providers.mock import MockProvider

pytest.importorskip("pymysql", reason="MySQL 池参数测试需要 pymysql 驱动")


# ---------- 慢查询日志 ----------

def test_slow_query_warning_when_threshold_zero(monkeypatch, caplog):
    monkeypatch.setattr(get_settings(), "slow_query_ms", 0)
    with caplog.at_level(logging.WARNING, logger="app.db"):
        with db_module.engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    assert any("慢查询" in r.message for r in caplog.records)


def test_no_slow_query_warning_with_big_threshold(monkeypatch, caplog):
    monkeypatch.setattr(get_settings(), "slow_query_ms", 10_000)
    with caplog.at_level(logging.WARNING, logger="app.db"):
        with db_module.engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    assert not any("慢查询" in r.message for r in caplog.records)


def test_mysql_pool_params_frozen(monkeypatch):
    """MySQL 分支:pool_size=20 / max_overflow=10 / pool_recycle=1800(WP09 固化)。"""
    monkeypatch.setattr(get_settings(), "database_url",
                        "mysql+pymysql://user:pass@127.0.0.1:3306/ai_portal")
    eng = db_module._build_engine()
    try:
        assert eng.pool.size() == 20
        assert eng.pool._max_overflow == 10
        assert eng.pool._recycle == 1800
        assert eng.pool._pre_ping is True
    finally:
        eng.dispose()


def test_sqlite_branch_untouched():
    """sqlite 分支不套 MySQL 池参数(测试库可正常工作即为通过)。"""
    with db_module.engine.connect() as conn:
        conn.execute(text("SELECT 1"))


# ---------- http_client 单例 ----------

def test_http_client_singleton_and_limits():
    client1 = get_http_client()
    client2 = get_http_client()
    assert client1 is client2
    pool = client1._transport._pool  # httpx 连接池
    assert pool._max_connections == 100
    assert pool._max_keepalive_connections == 20
    asyncio.run(close_http_client())
    client3 = get_http_client()  # 关闭后懒重建
    assert client3 is not client1 and not client3.is_closed
    asyncio.run(close_http_client())


# ---------- Mock 显式延迟 ----------

def _image_model(config_json=None):
    return SimpleNamespace(id=1, vendor="mock", model_code="mock-image",
                           config_json=config_json)


def _run_image(model, params=None) -> float:
    start = time.perf_counter()
    result = asyncio.run(MockProvider().generate_image(model, "一只熊猫", params))
    assert result["image_url"]
    return time.perf_counter() - start


def test_explicit_delay_via_params():
    elapsed = _run_image(_image_model(), {"mock_delay_sec": 0.05})
    assert elapsed < 1.0


def test_explicit_delay_via_config_json():
    elapsed = _run_image(_image_model('{"mock_delay_sec": 0.05}'))
    assert elapsed < 1.0


def test_explicit_delay_via_settings(monkeypatch):
    monkeypatch.setattr(get_settings(), "mock_delay_sec", 0.05)
    elapsed = _run_image(_image_model())
    assert elapsed < 1.0


def test_invalid_delay_ignored_uses_random_branch(monkeypatch):
    """非法值(负数/非数字)忽略;params 优先级高于 config_json。"""
    assert MockProvider._explicit_delay(_image_model(), {"mock_delay_sec": -1}) is None
    assert MockProvider._explicit_delay(_image_model(), {"mock_delay_sec": "abc"}) is None
    monkeypatch.setattr(get_settings(), "mock_delay_sec", None)
    # params 优先于 config_json
    model = _image_model('{"mock_delay_sec": 99}')
    assert MockProvider._explicit_delay(model, {"mock_delay_sec": 0.05}) == 0.05
    assert MockProvider._explicit_delay(model, None) == 99


def test_text_stream_respects_explicit_delay():
    async def run():
        start = time.perf_counter()
        chunks = []
        async for chunk in MockProvider().generate_text(
            _image_model('{"mock_delay_sec": 0.05}'), [{"role": "user", "content": "hi"}]
        ):
            chunks.append(chunk)
        return time.perf_counter() - start, chunks

    elapsed, chunks = asyncio.run(run())
    assert elapsed < 1.0
    assert chunks[-1]["done"] is True  # 流式契约不变
