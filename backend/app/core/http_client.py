"""共享 httpx.AsyncClient 单例(WP09 性能固化)。

- 模块级懒初始化:首次 get_http_client() 才创建,进程内复用同一连接池;
- limits:max_connections=100 / max_keepalive_connections=20(高并发提交任务时
  避免每次调用新建 TCP/TLS 连接的开销与端口耗尽);
- TODO(WP10): providers/base.py 目前在 _post_with_retry / _open_stream_with_retry
  中每次调用新建 AsyncClient,WP10 由 providers 层逐步接入本单例,本期先就绪,
  不改动 providers 层(归属限制)。
"""
import httpx

_client: httpx.AsyncClient | None = None


def get_http_client() -> httpx.AsyncClient:
    """返回进程级共享 AsyncClient;被关闭后自动重建(懒初始化单例)。"""
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
        )
    return _client


async def close_http_client() -> None:
    """优雅关闭(应用 shutdown 钩子预留);下次 get_http_client() 会重建。"""
    global _client
    if _client is not None and not _client.is_closed:
        await _client.aclose()
    _client = None
