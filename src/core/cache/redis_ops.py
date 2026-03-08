import json
import uuid
from typing import Any

from redis.asyncio import Redis

from src.core.cache.cache import get_redis


class RedisCache:
    """Redis 操作封装"""

    def _get_client(self) -> Redis:
        """获取 Redis 客户端"""
        return get_redis()

    # ========== 字符串操作 ==========

    async def get(self, key: str) -> str | None:
        """获取值"""
        return await self._get_client().get(key)

    async def set(
        self,
        key: str,
        value: Any,
        ex: int | None = None,
        px: int | None = None,
        nx: bool = False,
        xx: bool = False,
    ) -> bool:
        """
        设置值

        Args:
            key: 键
            value: 值
            ex: 过期时间（秒）
            px: 过期时间（毫秒）
            nx: 仅当键不存在时设置
            xx: 仅当键存在时设置
        """
        return await self._get_client().set(key, value, ex=ex, px=px, nx=nx, xx=xx)

    async def delete(self, *keys: str) -> int:
        """删除键，返回删除的数量"""
        return await self._get_client().delete(*keys)

    async def exists(self, *keys: str) -> int:
        """检查键是否存在，返回存在的数量"""
        return await self._get_client().exists(*keys)

    async def expire(self, key: str, seconds: int) -> bool:
        """设置过期时间（秒）"""
        return await self._get_client().expire(key, seconds)

    async def ttl(self, key: str) -> int:
        """
        获取剩余过期时间（秒）
        返回 -1 表示永不过期，-2 表示键不存在
        """
        return await self._get_client().ttl(key)

    async def incr(self, key: str, amount: int = 1) -> int:
        """递增"""
        return await self._get_client().incr(key, amount)

    async def decr(self, key: str, amount: int = 1) -> int:
        """递减"""
        return await self._get_client().decr(key, amount)

    # ========== 哈希操作 ==========

    async def hget(self, name: str, key: str) -> str | None:
        """获取哈希字段的值"""
        return await self._get_client().hget(name, key)

    async def hset(self, name: str, key: str, value: Any) -> int:
        """设置哈希字段"""
        return await self._get_client().hset(name, key, value)

    async def hmset(self, name: str, mapping: dict) -> bool:
        """批量设置哈希字段"""
        return await self._get_client().hset(name, mapping=mapping)

    async def hgetall(self, name: str) -> dict:
        """获取哈希所有字段"""
        return await self._get_client().hgetall(name)

    async def hdel(self, name: str, *keys: str) -> int:
        """删除哈希字段"""
        return await self._get_client().hdel(name, *keys)

    async def hexists(self, name: str, key: str) -> bool:
        """检查哈希字段是否存在"""
        return await self._get_client().hexists(name, key)

    async def hkeys(self, name: str) -> list:
        """获取哈希所有字段名"""
        return await self._get_client().hkeys(name)

    async def hvals(self, name: str) -> list:
        """获取哈希所有值"""
        return await self._get_client().hvals(name)

    # ========== 列表操作 ==========

    async def lpush(self, name: str, *values: Any) -> int:
        """从左侧推入"""
        return await self._get_client().lpush(name, *values)

    async def rpush(self, name: str, *values: Any) -> int:
        """从右侧推入"""
        return await self._get_client().rpush(name, *values)

    async def lpop(self, name: str) -> str | None:
        """从左侧弹出"""
        return await self._get_client().lpop(name)

    async def rpop(self, name: str) -> str | None:
        """从右侧弹出"""
        return await self._get_client().rpop(name)

    async def lrange(self, name: str, start: int, end: int) -> list:
        """获取列表范围内的元素"""
        return await self._get_client().lrange(name, start, end)

    async def llen(self, name: str) -> int:
        """获取列表长度"""
        return await self._get_client().llen(name)

    # ========== 集合操作 ==========

    async def sadd(self, name: str, *values: Any) -> int:
        """添加元素到集合"""
        return await self._get_client().sadd(name, *values)

    async def srem(self, name: str, *values: Any) -> int:
        """从集合删除元素"""
        return await self._get_client().srem(name, *values)

    async def smembers(self, name: str) -> set:
        """获取集合所有成员"""
        return await self._get_client().smembers(name)

    async def sismember(self, name: str, value: Any) -> bool:
        """检查元素是否在集合中"""
        return await self._get_client().sismember(name, value)

    async def scard(self, name: str) -> int:
        """获取集合大小"""
        return await self._get_client().scard(name)

    async def sinter(self, *keys: str) -> set:
        """集合交集"""
        return await self._get_client().sinter(*keys)

    async def sunion(self, *keys: str) -> set:
        """集合并集"""
        return await self._get_client().sunion(*keys)

    async def sdiff(self, *keys: str) -> set:
        """集合差集"""
        return await self._get_client().sdiff(*keys)

    # ========== 有序集合操作 ==========

    async def zadd(self, name: str, mapping: dict) -> int:
        """
        添加元素到有序集合
        mapping: {member: score}
        """
        return await self._get_client().zadd(name, mapping)

    async def zrem(self, name: str, *values: Any) -> int:
        """从有序集合删除元素"""
        return await self._get_client().zrem(name, *values)

    async def zrange(
        self, name: str, start: int, end: int, withscores: bool = False
    ) -> list:
        """按索引范围获取元素（从小到大）"""
        return await self._get_client().zrange(name, start, end, withscores=withscores)

    async def zrevrange(
        self, name: str, start: int, end: int, withscores: bool = False
    ) -> list:
        """按索引范围获取元素（从大到小）"""
        return await self._get_client().zrevrange(
            name, start, end, withscores=withscores
        )

    async def zrangebyscore(
        self, name: str, min_score: float, max_score: float, withscores: bool = False
    ) -> list:
        """按分数范围获取元素"""
        return await self._get_client().zrangebyscore(
            name, min_score, max_score, withscores=withscores
        )

    async def zcard(self, name: str) -> int:
        """获取有序集合大小"""
        return await self._get_client().zcard(name)

    async def zscore(self, name: str, value: Any) -> float | None:
        """获取元素的分数"""
        return await self._get_client().zscore(name, value)

    # ========== JSON 操作（辅助方法）==========

    async def get_json(self, key: str) -> Any:
        """获取 JSON 值"""
        value = await self.get(key)
        return json.loads(value) if value else None

    async def set_json(self, key: str, value: Any, ex: int | None = None) -> bool:
        """设置 JSON 值"""
        return await self.set(key, json.dumps(value, ensure_ascii=False), ex=ex)

    # ========== 分布式锁 ==========

    async def acquire_lock(
        self, key: str, value: str | None = None, ex: int = 10
    ) -> bool:
        """
        获取分布式锁
        Args:
            key: 锁名
            value: 锁值（唯一标识），若不传自动生成 UUID
            ex: 过期时间（秒）
        """
        value = value or str(uuid.uuid4())
        ok = await self.set(key, value, ex=ex, nx=True)
        return ok is True

    async def release_lock(self, key: str, value: str) -> bool:
        """
        释放分布式锁（仅当锁值匹配时才删除）
        防止误删其他进程的锁
        """
        lua_script = """
           if redis.call('get', KEYS[1]) == ARGV[1] then
               return redis.call('del', KEYS[1])
           else
               return 0
           end
           """
        result = await self._get_client().eval(lua_script, 1, key, value)
        return result == 1

    async def extend_lock(self, key: str, value: str, ex: int) -> bool:
        """
        延长锁的过期时间（防止长任务超时）
        仅在锁仍属于当前客户端时有效
        """
        lua_script = """
           if redis.call('get', KEYS[1]) == ARGV[1] then
               return redis.call('expire', KEYS[1], ARGV[2])
           else
               return 0
           end
           """
        result = await self._get_client().eval(lua_script, 1, key, value, ex)
        return result == 1


# 创建全局实例
redis_cache: RedisCache = RedisCache()
