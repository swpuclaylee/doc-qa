import time

from fastapi import Request
from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware


class LoggingMiddleware(BaseHTTPMiddleware):
    """请求日志中间件"""

    def __init__(self, app, slow_threshold: float = 1.0):
        """
        Args:
            slow_threshold: 慢请求阈值（秒）
        """
        super().__init__(app)
        self.slow_threshold = slow_threshold

    async def dispatch(self, request: Request, call_next):
        """
        拦截每个 HTTP 请求，记录访问日志和耗时。

        慢请求（超过 slow_threshold 秒）使用 WARNING 级别记录，
        正常请求使用 INFO 级别记录。
        日志绑定了 request_id、method、path、ip、user_id 等上下文字段。
        """
        # 记录开始时间
        start_time = time.time()

        # 绑定请求上下文
        log = logger.bind(
            request_id=request.state.request_id,
            method=request.method,
            path=request.url.path,
            ip=request.state.client_ip,
            user_id=request.state.user_id if request.state.user else None,
            log_type="access",
        )

        # 处理请求
        response = await call_next(request)

        # 计算处理时间
        process_time = time.time() - start_time

        # 记录响应
        if process_time > self.slow_threshold:
            log.bind(
                status_code=response.status_code, process_time=f"{process_time:.3f}s"
            ).warning(f"慢请求: 耗时 {process_time:.3f}s 超过阈值 {self.slow_threshold}s")
        else:
            log.bind(
                status_code=response.status_code, process_time=f"{process_time:.3f}s"
            ).info("请求完成")

        return response
