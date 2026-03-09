from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.conversation import Conversation, MessageRole
from src.repository.base import BaseRepository


class ConversationRepository(BaseRepository[Conversation]):
    def __init__(self):
        super().__init__(Conversation)

    async def get_by_session(
        self, db: AsyncSession, session_id: str, limit: int = 20
    ) -> list[Conversation]:
        """获取会话历史，按时间正序，最多取 limit 条"""
        result = await db.execute(
            select(self.model)
            .where(self.model.session_id == session_id)
            .order_by(self.model.created_at.asc())
            .limit(limit)
        )
        return list(result.scalars().all())

    # async def add_message(
    #     self,
    #     db: AsyncSession,
    #     session_id: str,
    #     document_id: int,
    #     role: MessageRole,
    #     content: str,
    # ) -> Conversation:
    #     """写入一条对话记录"""
    #     return await self.create(
    #         db,
    #         {
    #             "session_id": session_id,
    #             "document_id": document_id,
    #             "role": role,
    #             "content": content,
    #         },
    #     )

    async def add_message(
        self,
        db: AsyncSession,
        session_id: str,
        document_ids: list[int] | int,  # 兼容新旧调用
        role: MessageRole,
        content: str,
    ) -> Conversation:
        # 统一转为列表
        if isinstance(document_ids, int):
            doc_ids_list = [document_ids]
            doc_id_primary = document_ids
        else:
            doc_ids_list = document_ids
            doc_id_primary = document_ids[0] if document_ids else None

        msg = Conversation(
            session_id=session_id,
            document_id=doc_id_primary,  # 保留单值字段（可空，兼容旧数据）
            document_ids=doc_ids_list,  # 新字段
            role=role,
            content=content,
        )
        db.add(msg)
        await db.commit()
        await db.refresh(msg)
        return msg

    async def delete_by_session(self, db: AsyncSession, session_id: str) -> int:
        """清空某个会话的所有记录，返回删除条数"""
        result = await db.execute(
            delete(self.model).where(self.model.session_id == session_id)
        )
        await db.commit()
        return result.rowcount


conversation_repo = ConversationRepository()
