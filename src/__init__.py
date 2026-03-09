from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from loguru import logger
from starlette.exceptions import HTTPException as StarletteHTTPException

from src.core.config import STATIC_DIR, settings
from src.core.events import lifespan
from src.core.logger import setup_logger


def create_app() -> FastAPI:
    """创建并配置 FastAPI 应用"""

    # 启动日志系统
    setup_logger()

    # 创建应用实例
    app = FastAPI(
        title=settings.PROJECT_NAME,
        description=settings.PROJECT_DESCRIPTION,
        version=settings.VERSION,
        # docs_url=settings.API_PREFIX + "/docs",
        # openapi_url=settings.API_PREFIX + "/openapi.json",
        swagger_ui_parameters={
            "docExpansion": "none",
            "filter": True,
            "defaultModelsExpandDepth": -1,
        },
        lifespan=lifespan,
    )

    # 配置 CORS
    setup_cors(app)

    # 注册路由
    register_routers(app)

    # 注册中间件
    register_middlewares(app)

    # 注册异常处理器
    register_exception_handlers(app)

    return app


def setup_cors(app: FastAPI):
    """配置 CORS"""

    from fastapi.middleware.cors import CORSMiddleware

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


def register_routers(app: FastAPI) -> None:
    """注册路由"""
    from fastapi.responses import FileResponse
    from fastapi.staticfiles import StaticFiles

    from src.api.v1.router import api_v1_router

    app.include_router(api_v1_router, prefix=settings.API_PREFIX)

    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/", include_in_schema=False)
    async def index():
        return FileResponse(STATIC_DIR / "index.html")


def register_middlewares(app: FastAPI):
    """注册中间件"""

    from src.middleware.logging import LoggingMiddleware

    app.add_middleware(LoggingMiddleware, slow_threshold=1.0)

    from src.middleware.request_context import RequestContextMiddleware

    app.add_middleware(RequestContextMiddleware)


def register_exception_handlers(app: FastAPI):
    """注册异常处理器"""

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        """
        处理 HTTPException

        将 FastAPI 的 HTTPException 转换为统一响应格式
        """
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ):
        """
        处理参数验证异常

        Pydantic 验证失败时触发
        """
        # 提取第一个错误信息
        first_error = exc.errors()[0]
        field = ".".join(str(x) for x in first_error["loc"][1:])  # 字段名
        message = first_error["msg"]  # 错误信息

        logger.warning(f"参数验证失败: {field} - {message}")

        return JSONResponse(
            status_code=422,
            content={"detail": f"{field}: {message}"},
        )

    @app.exception_handler(Exception)
    async def exception_handler(request: Request, exc: Exception):
        """
        处理所有未捕获的异常

        返回 500 错误
        """
        logger.error(f"未捕获异常: {type(exc).__name__}")
        logger.exception(exc)

        return JSONResponse(
            status_code=500,
            content={"detail": "服务器内部错误"},
        )
