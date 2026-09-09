"""JWT 登出黑名单(进程内内存实现)。

- logout 时把当前 token 的 sha256 摘要拉黑,有效期取 token 剩余寿命,到期自动清理;
- get_current_user 每次校验前查询,黑名单中的 token 立即失效;
- 限制:单进程内存有效(与文档口径一致);多 worker/多实例部署时需替换为
  Redis 等共享存储,本模块接口(set/get)已为此预留。
"""
import hashlib
import threading
import time

_lock = threading.Lock()
# {sha256hex: 过期时间戳(秒)}
_blacklist: dict[str, float] = {}
_CLEAN_INTERVAL = 600  # 清理周期(秒)
_last_clean = 0.0


def _cleanup() -> None:
    """惰性清理:删除已过期的条目,避免长期运行内存膨胀。"""
    global _last_clean
    now = time.time()
    if now - _last_clean < _CLEAN_INTERVAL:
        return
    _last_clean = now
    expired = [k for k, exp in _blacklist.items() if exp <= now]
    for k in expired:
        _blacklist.pop(k, None)


def revoke(token: str, expires_at_ts: float) -> None:
    """拉黑 token;expires_at_ts 为该 token 的过期 Unix 时间戳。"""
    digest = hashlib.sha256(token.encode()).hexdigest()
    with _lock:
        _cleanup()
        _blacklist[digest] = max(float(expires_at_ts), time.time())


def is_revoked(token: str) -> bool:
    """token 是否已被登出拉黑。"""
    digest = hashlib.sha256(token.encode()).hexdigest()
    with _lock:
        exp = _blacklist.get(digest)
        if exp is None:
            return False
        if exp <= time.time():  # 已过有效期的黑名单条目顺带清理
            _blacklist.pop(digest, None)
            return False
        return True
