import uuid
from typing import Union

from src.core.config import settings


def make_cache_key(*parts: str) -> str:
    """
    生成格式化的 Redis key

    示例：
        make_key("user", "info", "123") -> "fastapi:user:info:123"
    """
    return f"{settings.PROJECT_NAME.lower()}:{':'.join(parts)}"


class CacheKey:
    """
    Redis 缓存 Key 管理
    """

    # ---------------- 用户相关 ----------------
    USER_INFO = "user:info:{user_id}"  # 用户信息
    USER_TOKEN = "user:token:{token}"  # 用户 Token
    USER_LIST = "user:list:page_{page}"  # 用户列表（分页）

    # ---------------- 验证码 ----------------
    VERIFY_CODE = "code:{phone}"  # 验证码

    # ---------------- 静态方法生成最终 Key ----------------
    @staticmethod
    def user_info(user_id: Union[int, str, uuid.UUID]) -> str:
        """用户信息 Key"""
        return make_cache_key(CacheKey.USER_INFO.format(user_id=user_id))

    @staticmethod
    def user_token(token: str) -> str:
        """用户 Token Key"""
        return make_cache_key(CacheKey.USER_TOKEN.format(token=token))

    @staticmethod
    def user_list(page: int) -> str:
        """用户列表分页 Key"""
        return make_cache_key(CacheKey.USER_LIST.format(page=page))

    @staticmethod
    def verify_code(phone: str) -> str:
        """验证码 Key"""
        return make_cache_key(CacheKey.VERIFY_CODE.format(phone=phone))
