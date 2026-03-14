from contextlib import asynccontextmanager

from fastapi import FastAPI
from loguru import logger

from src.core.cache.cache import close_redis, init_redis
from src.core.config import STATIC_DIR
from src.core.embedding import embedding_manager
from src.core.reranker import reranker
from src.db.init_db import close_db, init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI 应用生命周期管理（startup / shutdown）。

    Startup 阶段（按顺序）：
    1. 初始化 PostgreSQL 异步连接池（AsyncEngine）
    2. 初始化 Redis 连接池
    3. 加载 Embedding 模型到内存（bge-small-zh-v1.5，CPU，约需 10s）
    4. 加载 Reranker 模型到内存（bge-reranker-base，CPU，可选）
    5. 创建 static 目录（如不存在）

    Shutdown 阶段：
    - 关闭数据库连接池
    - 关闭 Redis 连接池

    注意：Embedding/Reranker 仅在 Web 进程中加载；
    Celery Worker 通过 worker_process_init 信号独立初始化自己的资源。
    """

    # ========== 启动时 ==========
    logger.info("应用启动中...")

    # 1. 初始化数据库连接池
    await init_db()
    logger.info("数据库连接池已初始化")

    # 2. 初始化 Redis 连接
    await init_redis()
    logger.info("Redis 已初始化")

    logger.info("应用启动完成")

    embedding_manager.init()
    logger.info("Embedding 模型已加载")

    reranker.init()
    logger.info("Rerank 模型已加载")

    # 3. 创建静态目录
    STATIC_DIR.mkdir(parents=True, exist_ok=True)

    yield

    # ========== 关闭时 ==========

    # 关闭数据库连接池
    await close_db()
    logger.info("数据库连接池已关闭")

    # 关闭 Redis 连接
    await close_redis()
    logger.info("Redis 已关闭")
