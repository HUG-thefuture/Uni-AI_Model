"""开放平台内存限流器(WP06):单 Key 每分钟固定窗口计数。

- 进程内存实现,重启即清零(多副本部署时后续可换 Redis,接口不变);
- 上限每次调用时从 get_settings().openapi_rate_limit_per_min 读取,便于热调;
- asyncio.Lock 保证并发安全。
"""
import asyncio
import time

from ..core.config import get_settings


class RateLimiter:
    """固定窗口计数限流:check(key_id) 超上限返回 False。"""

    def __init__(self) -> None:
        self._hits: dict[int, list[float]] = {}
        self._lock = asyncio.Lock()

    async def check(self, key_id: int) -> bool:
        """本次调用是否放行;放行则计数 +1。"""
        limit = get_settings().openapi_rate_limit_per_min
        now = time.monotonic()
        window_start = now - 60.0
        async with self._lock:
            hits = self._hits.get(key_id)
            if hits is None:
                hits = []
                self._hits[key_id] = hits
            # 淘汰 60s 窗口外的旧记录
            while hits and hits[0] <= window_start:
                hits.pop(0)
            if len(hits) >= limit:
                return False
            hits.append(now)
            return True

    async def reset(self, key_id: int) -> None:
        """清零指定 Key 的计数(测试用)。"""
        async with self._lock:
            self._hits.pop(key_id, None)


# 模块级单例:开放接口路由直接使用
rate_limiter = RateLimiter()
