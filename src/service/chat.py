from collections.abc import AsyncGenerator

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.hybrid_search import hybrid_searcher
from src.models.conversation import MessageRole
from src.repository.conversation import conversation_repo
from src.repository.document import document_repo
from src.schemas.chat import ChatHistoryOut, ConversationOut

SYSTEM_PROMPT = """你是一个专业的文档问答助手。
请根据以下从文档中检索到的相关内容，回答用户的问题。

要求：
- 只根据提供的文档内容回答，不要编造信息
- 如果文档中没有相关内容，请明确告知用户
- 回答要简洁、准确、有条理

相关文档内容：
{context}
"""


class ChatService:
    def _build_llm(self) -> ChatOpenAI:
        """构建 LLM 实例"""
        return ChatOpenAI(
            model="deepseek-chat",
            api_key=settings.DEEPSEEK_API_KEY,
            base_url=settings.DEEPSEEK_BASE_URL,
            temperature=0.3,
            streaming=True,
        )

    def _build_messages(
        self,
        context: str,
        history: list,
        question: str,
    ) -> list:
        """
        组装发送给 LLM 的消息列表

        结构：
          SystemMessage（含检索到的文档内容）
          + HumanMessage / AIMessage（历史对话，最近 10 条）
          + HumanMessage（当前问题）
        """
        messages = [SystemMessage(content=SYSTEM_PROMPT.format(context=context))]

        # 加入历史对话（最近 10 条，避免 token 超限）
        for msg in history[-10:]:
            if msg.role == MessageRole.USER:
                messages.append(HumanMessage(content=msg.content))
            else:
                messages.append(AIMessage(content=msg.content))

        # 加入当前问题
        messages.append(HumanMessage(content=question))
        return messages

    async def chat_stream(
        self,
        db: AsyncSession,
        document_id: int,
        session_id: str,
        question: str,
    ) -> AsyncGenerator[str, None]:
        """
        流式问答，返回一个异步生成器，逐 token yield 回答内容

        Args:
            db: 数据库会话
            document_id: 针对哪个文档提问
            session_id: 会话 ID
            question: 用户问题

        Yields:
            str: 每次 yield 一个 token
        """
        # 1. 校验文档存在且处理完成
        doc = await document_repo.get(db, document_id)
        if not doc:
            yield "错误：文档不存在"
            return
        if doc.status.value != "done":
            yield f"错误：文档尚未处理完成（当前状态：{doc.status.value}）"
            return

        # 2. 检索相关文档切片
        # retrieved_docs = await vector_store_manager.similarity_search(
        #     document_id=document_id,
        #     query=question,
        #     k=4,
        # )
        retrieved_docs = await hybrid_searcher.search(
            db=db,
            document_id=document_id,
            query=question,
            k=4,
            fetch_k=20,
        )

        context = "\n\n".join([d.page_content for d in retrieved_docs])
        logger.debug(f"检索到 {len(retrieved_docs)} 个切片 session={session_id}")

        # 3. 拉取对话历史
        history = await conversation_repo.get_by_session(db, session_id)

        # 4. 组装消息
        messages = self._build_messages(context, history, question)

        # 5. 存储用户消息
        await conversation_repo.add_message(
            db, session_id, document_id, MessageRole.USER, question
        )

        # 6. 流式调用 LLM，逐 token yield
        llm = self._build_llm()
        full_response = []

        try:
            async for chunk in llm.astream(messages):
                token = chunk.content
                if token:
                    full_response.append(token)
                    yield token

        except Exception as e:
            logger.error(f"LLM 调用失败: {e}")
            yield f"\n\n[错误：{str(e)}]"
            return

        # 7. 流式结束后，把完整回答存入数据库
        full_answer = "".join(full_response)
        await conversation_repo.add_message(
            db, session_id, document_id, MessageRole.ASSISTANT, full_answer
        )
        logger.info(f"问答完成 session={session_id} answer_len={len(full_answer)}")

    async def get_history(
        self, db: AsyncSession, session_id: str, document_id: int
    ) -> ChatHistoryOut:
        """获取对话历史"""
        messages = await conversation_repo.get_by_session(db, session_id)
        return ChatHistoryOut(
            session_id=session_id,
            document_id=document_id,
            messages=[ConversationOut.model_validate(m) for m in messages],
        )

    async def clear_history(self, db: AsyncSession, session_id: str) -> int:
        """清空对话历史，返回删除条数"""
        count = await conversation_repo.delete_by_session(db, session_id)
        logger.info(f"清空会话历史 session={session_id} count={count}")
        return count


chat_service = ChatService()
