from typing import Generic, Type, TypeVar

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.base import Base

# 定义泛型类型
ModelType = TypeVar("ModelType", bound=Base)


class BaseRepository(Generic[ModelType]):
    """
    基础仓储类

    封装通用的 CRUD 操作，子类继承后自动拥有这些方法
    """

    def __init__(self, model: Type[ModelType]):
        """
        初始化

        Args:
            model: SQLAlchemy 模型类（如 User, Role, Permission）
        """
        self.model = model

    async def get(self, db: AsyncSession, id: int) -> ModelType | None:
        """根据 ID 查询"""
        result = await db.execute(select(self.model).where(self.model.id == id))
        return result.scalar_one_or_none()

    async def get_multi(
        self, db: AsyncSession, skip: int = 0, limit: int = 100
    ) -> tuple[list[ModelType], int]:
        """
        分页查询

        Returns:
            (数据列表, 总数)
        """
        # 查询总数
        count_result = await db.execute(select(func.count()).select_from(self.model))
        total = count_result.scalar()

        # 查询数据
        result = await db.execute(select(self.model).offset(skip).limit(limit))
        items = list(result.scalars().all())

        return items, total

    async def create(self, db: AsyncSession, obj_in: dict) -> ModelType:
        """创建"""
        obj = self.model(**obj_in)
        db.add(obj)
        await db.commit()
        await db.refresh(obj)
        return obj

    async def update(self, db: AsyncSession, id: int, obj_in: dict) -> ModelType | None:
        """更新"""
        obj = await self.get(db, id)
        if not obj:
            return None

        for field, value in obj_in.items():
            setattr(obj, field, value)

        await db.commit()
        await db.refresh(obj)
        return obj

    async def delete(self, db: AsyncSession, id: int) -> bool:
        """物理删除"""
        obj = await self.get(db, id)
        if not obj:
            return False

        await db.delete(obj)
        await db.commit()
        return True
