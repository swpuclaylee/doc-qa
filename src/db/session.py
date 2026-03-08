from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


class DatabaseManager:
    """数据库连接管理器"""

    def __init__(self):
        self.engine: AsyncEngine | None = None
        self.session_maker: async_sessionmaker[AsyncSession] | None = None

    def init(
        self,
        database_url: str,
        echo: bool = False,
        pool_size: int = 5,
        max_overflow: int = 10,
        pool_recycle: int = 3600,
        pool_timeout: int = 30,
    ):
        """
        初始化数据库引擎和会话工厂

        Args:
            database_url: 数据库连接字符串
            echo: 是否打印 SQL 语句，开发环境建议 True
            pool_size: 连接池维护的常驻连接数量，默认 5
            max_overflow: 连接池满时最多还能创建的临时连接数，默认 10
            pool_recycle: 连接在池中存活的最大时间（秒），默认 3600
            pool_timeout: 从连接池获取连接的最大等待时间（秒），默认 30
        """
        # 创建异步数据库引擎
        self.engine = create_async_engine(
            database_url,
            echo=echo,
            future=True,  # 使用 2.0 风格 API
            pool_pre_ping=True,  # 连接池预检查，确保连接有效
            pool_size=pool_size,
            max_overflow=max_overflow,
            pool_recycle=pool_recycle,
            pool_timeout=pool_timeout,
        )

        # 创建会话工厂
        self.session_maker = async_sessionmaker(
            bind=self.engine,
            class_=AsyncSession,
            expire_on_commit=False,  # 提交后不过期对象，允许在会话外访问已加载的属性
            autoflush=False,  # 禁用自动刷新，手动控制何时同步到数据库
            autocommit=False,  # 禁用自动提交，需要显式调用 commit()
        )

    async def close(self):
        """关闭数据库连接池"""
        if self.engine:
            await self.engine.dispose()

    def get_session(self) -> AsyncSession:
        """
        创建新的数据库会话

        Returns:
            AsyncSession: 数据库会话对象

        Raises:
            RuntimeError: 如果数据库未初始化
        """
        if not self.session_maker:
            raise RuntimeError("数据库未初始化，请先调用 init() 方法")
        return self.session_maker()


# 全局数据库管理器实例
db_manager = DatabaseManager()
