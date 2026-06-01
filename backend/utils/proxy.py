import random
from ..config import settings

# 代理池（从配置或环境变量加载）
_proxy_pool: list[str] = []


def get_proxy() -> str | None:
    """获取一个代理地址"""
    if settings.proxy_url:
        return settings.proxy_url
    if _proxy_pool:
        return random.choice(_proxy_pool)
    return None


def set_proxy_pool(proxies: list[str]):
    """设置代理池"""
    global _proxy_pool
    _proxy_pool = proxies


def rotate_proxy(current: str | None) -> str | None:
    """轮换到下一个代理"""
    if not _proxy_pool:
        return None
    if current and current in _proxy_pool:
        idx = _proxy_pool.index(current)
        next_idx = (idx + 1) % len(_proxy_pool)
        return _proxy_pool[next_idx]
    return random.choice(_proxy_pool)
