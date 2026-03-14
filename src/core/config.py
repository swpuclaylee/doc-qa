from functools import lru_cache
from pathlib import Path

from pydantic import Field, computed_field
from pydantic_settings import BaseSettings

# 项目路径
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
STATIC_DIR = PROJECT_ROOT / "static"
ENV_FILE = PROJECT_ROOT / ".env"


class Settings(BaseSettings):
    """
    应用配置（从 .env 文件读取，pydantic-settings 自动解析）。

    分组说明：
    - 项目信息：PROJECT_NAME、VERSION 等
    - 数据库：DB_* 字段 + DATABASE_URL computed_field
    - Redis：REDIS_* 字段 + REDIS_URL property
    - JWT：SECRET_KEY、ALGORITHM、过期时间
    - LLM：DEEPSEEK_API_KEY、DEEPSEEK_BASE_URL
    - Chroma：CHROMA_HOST、CHROMA_PORT
    - Embedding：EMBEDDING_MODEL_NAME
    - Celery：CELERY_BROKER_URL / CELERY_RESULT_BACKEND（均复用 Redis）

    生产环境通过 .env 文件覆盖默认值，敏感字段（SECRET_KEY、DB_PASSWORD 等）
    不设默认值，强制在部署时指定。
    """

    # 项目信息
    PROJECT_NAME: str = "智能文档问答系统"
    PROJECT_DESCRIPTION: str = "智能文档问答系统"
    VERSION: str = "0.1.0"
    API_PREFIX: str = "/api/v1"

    # 环境配置
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    IS_PRODUCTION: bool = False

    # 数据库基础配置
    DB_HOST: str = Field(default="localhost", description="数据库主机")
    DB_PORT: int = Field(default=5432, description="数据库端口")
    DB_USER: str = Field(default="postgres", description="数据库用户名")
    DB_PASSWORD: str = Field(default="", description="数据库密码")
    DB_NAME: str = Field(default="myapp", description="数据库名称")

    # 数据库连接池配置
    DB_ECHO: bool = Field(default=False, description="是否打印 SQL")
    DB_POOL_SIZE: int = Field(default=10, description="连接池大小")
    DB_MAX_OVERFLOW: int = Field(default=20, description="最大溢出连接数")
    DB_POOL_RECYCLE: int = Field(default=3600, description="连接回收时间（秒）")
    DB_POOL_TIMEOUT: int = Field(default=30, description="连接超时时间（秒）")

    # MinIO 配置
    MINIO_ENDPOINT: str = "localhost:9000"  # MinIO 服务器地址
    MINIO_ACCESS_KEY: str = "minioadmin"  # 访问密钥
    MINIO_SECRET_KEY: str = "minioadmin"  # 秘密密钥
    MINIO_SECURE: bool = False  # 是否使用 HTTPS
    MINIO_BUCKET: str = "default"  # 默认存储桶
    MINIO_USE_HTTPS_URL: bool = True  # 生成的 URL 是否使用 HTTPS

    @computed_field
    @property
    def DATABASE_URL(self) -> str:
        """构建异步数据库 URL"""
        return (
            f"postgresql+asyncpg://{self.DB_USER}:{self.DB_PASSWORD}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        )

    # JWT 配置
    SECRET_KEY: str  # JWT 签名密钥
    ALGORITHM: str = "HS256"  # 签名算法
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15  # Access Token 过期时间（分钟）
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7  # Refresh Token 过期时间（天）

    # Redis
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD: str | None = None

    # 连接池配置
    REDIS_MAX_CONNECTIONS: int = 50
    REDIS_RETRY_ON_TIMEOUT: bool = True
    REDIS_SOCKET_KEEPALIVE: bool = True
    REDIS_SOCKET_TIMEOUT: int = 5
    REDIS_SOCKET_CONNECT_TIMEOUT: int = 5
    REDIS_DECODE_RESPONSES: bool = True

    @property
    def REDIS_URL(self) -> str:
        """生成 Redis URL"""
        if self.REDIS_PASSWORD:
            return f"redis://:{self.REDIS_PASSWORD}@{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"

    # CORS
    ALLOWED_ORIGINS: list[str] = ["*"]

    # fastapi_pagination 分页
    PAGINATION_SIZE: int = 50
    PAGINATION_MAX_SIZE: int = 500

    WORKERS: int = 4

    # LLM
    DEEPSEEK_API_KEY: str | None = None
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com"

    # Chroma
    CHROMA_HOST: str = "localhost"
    CHROMA_PORT: int = 1006

    # Embedding
    EMBEDDING_MODEL_NAME: str = "BAAI/bge-small-zh-v1.5"

    # ========== Celery 配置 ==========
    @property
    def CELERY_BROKER_URL(self) -> str:
        """Celery Broker URL"""
        return self.REDIS_URL

    @property
    def CELERY_RESULT_BACKEND(self) -> str:
        """Celery Result Backend URL"""
        return self.REDIS_URL

    class Config:
        env_file = ENV_FILE
        env_file_encoding = "utf-8"
        case_sensitive = True


# 使用 lru_cache 缓存配置，避免每次请求都重复读取 .env 文件
@lru_cache
def get_settings():
    """
    获取应用配置单例（lru_cache 确保全局只读取一次 .env）。

    在 FastAPI 应用和 Celery Worker 中均通过 `settings = get_settings()` 使用。
    """
    return Settings()


settings = get_settings()
