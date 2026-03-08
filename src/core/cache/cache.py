from redis.asyncio import Redis

from src.core.config import settings

redis_client: Redis | None = None


async def init_redis():
    """初始化 Redis 连接"""
    global redis_client

    try:
        redis_client = Redis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=settings.REDIS_DECODE_RESPONSES,
            max_connections=settings.REDIS_MAX_CONNECTIONS,
            retry_on_timeout=settings.REDIS_RETRY_ON_TIMEOUT,
            socket_keepalive=settings.REDIS_SOCKET_KEEPALIVE,
            socket_timeout=settings.REDIS_SOCKET_TIMEOUT,
            socket_connect_timeout=settings.REDIS_SOCKET_CONNECT_TIMEOUT,
        )
        await redis_client.ping()
    except Exception as e:
        print(f"Redis 连接失败：{e}")
        redis_client = None


async def close_redis():
    """关闭 Redis 连接"""
    if redis_client:
        await redis_client.close()


def get_redis() -> Redis:
    """获取 Redis 连接"""
    if not redis_client:
        raise RuntimeError("Redis 未初始化")
    return redis_client
