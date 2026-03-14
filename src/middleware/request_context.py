import time
import uuid

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware


class RequestContextMiddleware(BaseHTTPMiddleware):
    """请求上下文中间件"""

    async def dispatch(self, request: Request, call_next):
        """
        在每个请求进入时初始化请求上下文，响应返回时附加追踪头。

        写入 request.state：
        - request_id：来自 X-Request-ID 头或自动生成的 UUID
        - start_time：请求开始时间戳
        - client_ip：客户端真实 IP（考虑代理转发）
        - user_agent：User-Agent 字符串
        - user / user_id：初始化为 None（后续认证中间件填充）

        响应头追加：
        - X-Request-ID：请求追踪 ID
        - X-Process-Time：请求处理耗时（秒，3位小数）
        """
        # 1. 生成请求 ID
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        request.state.request_id = request_id

        # 2. 记录开始时间
        request.state.start_time = time.time()

        # 3. 客户端信息
        request.state.client_ip = await self.get_real_ip(request)
        request.state.user_agent = request.headers.get("User-Agent")

        # 4. 初始化用户信息（后续认证中间件会填充）
        request.state.user = None
        request.state.user_id = None

        # 处理请求
        response = await call_next(request)

        # 5. 添加响应头
        response.headers["X-Request-ID"] = request_id

        # 6. 计算处理时间
        process_time = time.time() - request.state.start_time
        response.headers["X-Process-Time"] = f"{process_time:.3f}"

        return response

    async def get_real_ip(self, request: Request) -> str:
        """获取客户端真实 IP"""
        # 优先从 X-Forwarded-For 获取
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            # X-Forwarded-For 格式: client_ip, proxy1_ip, proxy2_ip
            return forwarded.split(",")[0].strip()

        # 其次从 X-Real-IP 获取
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip

        # 最后用直连 IP
        return request.client.host
