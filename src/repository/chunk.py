from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.chunk import DocumentChunk
from src.repository.base import BaseRepository


class ChunkRepository(BaseRepository[DocumentChunk]):
    def __init__(self):
        super().__init__(DocumentChunk)

    async def bulk_create(
        self, db: AsyncSession, document_id: int, contents: list[str]
    ) -> int:
        """
        批量写入切片

        Args:
            document_id: 文档 ID
            contents: 切片文本列表

        Returns:
            写入数量
        """
        chunks = [
            DocumentChunk(
                document_id=document_id,
                content=content,
                chunk_index=i,
            )
            for i, content in enumerate(contents)
        ]
        db.add_all(chunks)
        await db.commit()
        return len(chunks)

    async def get_by_document(
        self, db: AsyncSession, document_id: int
    ) -> list[DocumentChunk]:
        """获取文档的所有切片，按序号排序"""
        result = await db.execute(
            select(self.model)
            .where(self.model.document_id == document_id)
            .order_by(self.model.chunk_index.asc())
        )
        return list(result.scalars().all())


chunk_repo = ChunkRepository()
