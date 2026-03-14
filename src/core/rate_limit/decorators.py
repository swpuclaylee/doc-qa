from functools import wraps
from typing import Literal

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

from src.core.rate_limit.algorithms import fixed_window_limit, sliding_window_limit

# 支持的算法类型
RateLimitAlgorithm = Literal["fixed", "sliding"]
# 支持的限流对象类型
RateLimitTarget = Literal["ip", "user"]


def rate_limit(
    limit: int = 100,
    window: int = 60,
    algorithm: RateLimitAlgorithm = "fixed",
    target: RateLimitTarget = "ip",
):
    """
    限流装饰器

    Args:
        limit: 最大请求次数
        window: 时间窗口（秒）
        algorithm: 限流算法 ["fixed", "sliding"]
        target: 限流对象 ["ip", "user"]
    """

    def decorator(func):
        """内层装饰器，接收被装饰的视图函数。"""

        @wraps(func)
        async def wrapper(request: Request, *args, **kwargs):
            """
            实际执行限流逻辑的异步包装函数。

            按 target 类型生成限流 key（IP 优先读 X-Forwarded-For），
            调用对应算法检查是否超限，超限时直接返回 429 响应。
            """
            # 获取用户 ID（如果是用户限流）
            user_id = None
            if hasattr(request.state, "user"):
                user_id = getattr(request.state.user, "id", None)

            # 生成限流 key
            if target == "ip":
                ip = request.client.host
                # 支持代理转发的真实 IP
                forwarded = request.headers.get("X-Forwarded-For")
                if forwarded:
                    ip = forwarded.split(",")[0].strip()
                key = f"rate_limit:ip:{ip}"
            elif target == "user":
                if not user_id:
                    raise HTTPException(status_code=401, detail="用户限流需要登录")
                key = f"rate_limit:user:{user_id}"
            else:
                raise ValueError(f"不支持的限流对象: {target}")

            # 执行限流检查
            if algorithm == "fixed":
                allowed, remaining = await fixed_window_limit(key, limit, window)
            elif algorithm == "sliding":
                allowed, remaining = await sliding_window_limit(key, limit, window)
            else:
                raise ValueError(f"不支持的限流算法: {algorithm}")

            if not allowed:
                return JSONResponse(
                    status_code=429,
                    content={"code": 0, "msg": "请求过于频繁，请稍后再试", "data": None},
                )

            return await func(request, *args, **kwargs)

        return wrapper

    return decorator
