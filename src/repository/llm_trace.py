from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.llm_trace import LLMTrace
from src.repository.base import BaseRepository


class LLMTraceRepository(BaseRepository[LLMTrace]):
    def __init__(self):
        super().__init__(LLMTrace)

    async def create_trace(self, db: AsyncSession, data: dict) -> LLMTrace:
        """创建链路日志"""
        return await self.create(db, data)

    async def get_by_session(
        self, db: AsyncSession, session_id: str, limit: int = 20
    ) -> list[LLMTrace]:
        """获取会话的链路日志"""
        result = await db.execute(
            select(self.model)
            .where(self.model.session_id == session_id)
            .order_by(self.model.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())


llm_trace_repo = LLMTraceRepository()
