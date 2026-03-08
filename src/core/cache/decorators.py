import asyncio
import functools
import hashlib
import json
import uuid
from typing import Callable, Optional

from src.core.cache.cache_key import make_cache_key
from src.core.cache.redis_ops import redis_cache


def cached(
    ttl: int = 3600,
    prefix: Optional[str] = None,
    auto_refresh: bool = True,
    wait_for_lock: bool = True,
):
    """
    通用异步缓存装饰器（支持自动刷新 + 分布式锁防击穿）

    Args:
        ttl: 缓存过期时间（秒）
        prefix: 自定义缓存前缀（会拼接到项目名后）
        auto_refresh: 是否在快过期时后台刷新缓存
        wait_for_lock: 是否在未获取锁时轮询等待缓存
    """

    def decorator(func: Callable):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # === 1. 生成缓存 Key ===
            cache_key = _generate_cache_key(func.__name__, args, kwargs, prefix)

            # === 2. 查询缓存 ===
            cached_data = await redis_cache.get_json(cache_key)
            if cached_data is not None:
                if auto_refresh:
                    remaining = await redis_cache.ttl(cache_key)
                    if 0 < remaining < ttl * 0.1:
                        asyncio.create_task(
                            _refresh_cache(func, args, kwargs, cache_key, ttl)
                        )
                return cached_data

            # === 3. 分布式锁防击穿 ===
            lock_key = f"lock:{cache_key}"
            lock_value = str(uuid.uuid4())
            got_lock = await redis_cache.acquire_lock(lock_key, lock_value, ex=5)

            if not got_lock and wait_for_lock:
                # 未获取锁 -> 等待缓存更新
                for _ in range(10):  # 最多等待 1 秒
                    await asyncio.sleep(0.1)
                    cached_data = await redis_cache.get_json(cache_key)
                    if cached_data is not None:
                        return cached_data
                # 超时后仍未获取到缓存，继续执行函数（降级）

            try:
                # === 4. 执行函数 ===
                result = await func(*args, **kwargs)
                if result is not None:
                    await redis_cache.set_json(cache_key, result, ex=ttl)
                return result
            finally:
                # === 5. 释放锁 ===
                if got_lock:
                    await redis_cache.release_lock(lock_key, lock_value)

        return wrapper

    return decorator


def _generate_cache_key(
    func_name: str, args: tuple, kwargs: dict, prefix: Optional[str]
) -> str:
    """
    基于函数签名生成稳定缓存 Key
    示例： fastapi:cache:user_info:3e8d7a9f
    """
    params_str = json.dumps(
        {"args": args, "kwargs": kwargs}, sort_keys=True, default=str
    )
    params_hash = hashlib.md5(params_str.encode()).hexdigest()[:8]
    parts = ["cache", func_name, params_hash]
    if prefix:
        parts.insert(0, prefix)
    return make_cache_key(*parts)


async def _refresh_cache(
    func: Callable, args: tuple, kwargs: dict, cache_key: str, ttl: int
):
    """后台刷新缓存"""
    try:
        result = await func(*args, **kwargs)
        if result is not None:
            await redis_cache.set_json(cache_key, result, ex=ttl)
    except Exception as e:
        print(f"[Cache] 后台刷新失败: {e}")
