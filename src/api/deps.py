from typing import AsyncGenerator

from fastapi import Request
from fastapi.security import OAuth2PasswordBearer
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.session import db_manager

# 创建OAuth2认证方案
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


def get_logger(request: Request):
    """
        获取带请求上下文的 logger
    o
        自动包含：request_id, method, path, user_id, ip
    """
    return logger.bind(
        request_id=getattr(request.state, "request_id", None),
        method=request.method,
        path=request.url.path,
        user_id=getattr(request.state, "user_id", None),
        ip=getattr(request.state, "client_ip", None),
    )


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    数据库会话依赖

    使用 async generator 自动管理会话生命周期：
    - 请求开始时创建会话
    - 请求结束时自动关闭会话
    - 异常发生时自动回滚

    Yields:
        AsyncSession: 数据库会话对象
    """
    async with db_manager.get_session() as session:
        try:
            yield session
        except Exception:
            # 发生异常时回滚事务
            await session.rollback()
            raise
        finally:
            # 确保会话被关闭
            await session.close()
