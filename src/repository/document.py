from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.document import Document, DocumentStatus
from src.repository.base import BaseRepository


class DocumentRepository(BaseRepository[Document]):
    def __init__(self):
        super().__init__(Document)

    async def get_by_status(
        self, db: AsyncSession, status: DocumentStatus
    ) -> list[Document]:
        """按状态查询文档列表"""
        result = await db.execute(select(self.model).where(self.model.status == status))
        return list(result.scalars().all())

    async def update_status(
        self,
        db: AsyncSession,
        id: int,
        status: DocumentStatus,
        chunk_count: int | None = None,
        error_msg: str | None = None,
    ) -> Document | None:
        """
        更新文档处理状态，可选同时更新 chunk_count 和 error_msg。

        Args:
            id: 文档 ID
            status: 目标状态
            chunk_count: 切片数量（处理完成时写入）
            error_msg: 错误信息（处理失败时写入）

        Returns:
            更新后的 Document 对象，文档不存在时返回 None
        """
        obj = await self.get(db, id)
        if not obj:
            return None

        obj.status = status
        if chunk_count is not None:
            obj.chunk_count = chunk_count
        if error_msg is not None:
            obj.error_msg = error_msg

        await db.commit()
        await db.refresh(obj)
        return obj


document_repo = DocumentRepository()
