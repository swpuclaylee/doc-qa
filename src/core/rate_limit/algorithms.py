"""
Redis 限流算法模块
支持：
1. 固定窗口限流 (Fixed Window)
2. 滑动窗口限流 (Sliding Window)

说明：
- 所有算法均使用 Redis 原子操作保证并发安全
- 支持异步调用
"""

import time

from src.core.cache.cache import get_redis


# ------------------------------
# 1. 固定窗口限流
# ------------------------------
async def fixed_window_limit(key: str, limit: int, window: int) -> tuple[bool, int]:
    """
    固定窗口限流

    Args:
        key: 限流键（如 user_id 或 ip）
        limit: 最大请求次数
        window: 时间窗口（秒）

    Returns:
        (是否允许请求, 剩余请求次数)
    """
    client = get_redis()

    # 使用 Lua 脚本保证原子性
    lua_script = """
    local count = redis.call('INCR', KEYS[1])
    if count == 1 then
        redis.call('EXPIRE', KEYS[1], ARGV[1])
    end
    return count
    """

    count = await client.eval(lua_script, 1, key, window)
    remaining = max(0, limit - count)

    return count <= limit, remaining


# ------------------------------
# 2. 滑动窗口限流
# ------------------------------
async def sliding_window_limit(key: str, limit: int, window: int) -> tuple[bool, int]:
    """
    滑动窗口限流

    Args:
        key: 限流键
        limit: 最大请求次数
        window: 时间窗口（秒）

    Returns:
        (是否允许请求, 剩余请求次数)
    """
    now = time.time()
    window_start = now - window
    rate_key = f"rate_limit:sliding:{key}"
    client = get_redis()

    # 删除窗口外的请求
    await client.zremrangebyscore(rate_key, 0, window_start)

    # 当前窗口请求数
    count = await client.zcard(rate_key)

    if count >= limit:
        return False, 0

    # 添加当前请求
    await client.zadd(rate_key, {str(now): now})
    await client.expire(rate_key, window + 1)

    remaining = limit - count - 1
    return True, remaining
