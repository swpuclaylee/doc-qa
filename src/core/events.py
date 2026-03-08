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
    应用生命周期管理
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
