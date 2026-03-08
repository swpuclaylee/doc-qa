from src.core.config import settings
from src.db.session import db_manager


async def init_db():
    """初始化数据库连接池"""
    db_manager.init(
        database_url=settings.DATABASE_URL,
        echo=settings.DB_ECHO,
        pool_size=settings.DB_POOL_SIZE,
        max_overflow=settings.DB_MAX_OVERFLOW,
        pool_recycle=settings.DB_POOL_RECYCLE,
        pool_timeout=settings.DB_POOL_TIMEOUT,
    )


async def close_db():
    """关闭数据库连接池"""
    await db_manager.close()
