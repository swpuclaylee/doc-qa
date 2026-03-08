import json
import time
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
from src.repository.llm_trace import llm_trace_repo
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

# 上下文 token 预算（为检索内容和回答留出空间）
MAX_HISTORY_TOKENS = 2000


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

    def _estimate_tokens(self, text: str) -> int:
        """
        估算文本的 token 数

        粗略规则：
        - 中文字符：1 字 ≈ 1 token
        - 英文/其他：4 字符 ≈ 1 token
        """
        chinese_chars = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
        other_chars = len(text) - chinese_chars
        return chinese_chars + other_chars // 4

    def _build_messages(
        self,
        context: str,
        history: list,
        question: str,
    ) -> list:
        """
        组装消息列表，按 token 预算动态截断历史

        优先保留最近的对话，超出预算的早期消息直接丢弃。
        """
        messages = [SystemMessage(content=SYSTEM_PROMPT.format(context=context))]

        # 从最新消息往最旧遍历，累计 token 数不超过预算
        total_tokens = 0
        trimmed_history = []

        for msg in reversed(history):
            tokens = self._estimate_tokens(msg.content)
            if total_tokens + tokens > MAX_HISTORY_TOKENS:
                break
            trimmed_history.insert(0, msg)
            total_tokens += tokens

        if len(trimmed_history) < len(history):
            logger.debug(
                f"历史消息截断: 原始 {len(history)} 条 "
                f"→ 保留 {len(trimmed_history)} 条 "
                f"token 预算 {MAX_HISTORY_TOKENS}"
            )

        # 加入历史消息
        for msg in trimmed_history:
            if msg.role == MessageRole.USER:
                messages.append(HumanMessage(content=msg.content))
            else:
                messages.append(AIMessage(content=msg.content))

        # 加入当前问题
        messages.append(HumanMessage(content=question))
        return messages

    # def _build_messages(
    #     self,
    #     context: str,
    #     history: list,
    #     question: str,
    # ) -> list:
    #     """
    #     组装发送给 LLM 的消息列表
    #
    #     结构：
    #       SystemMessage（含检索到的文档内容）
    #       + HumanMessage / AIMessage（历史对话，最近 10 条）
    #       + HumanMessage（当前问题）
    #     """
    #     messages = [SystemMessage(content=SYSTEM_PROMPT.format(context=context))]
    #
    #     # 加入历史对话（最近 10 条，避免 token 超限）
    #     for msg in history[-10:]:
    #         if msg.role == MessageRole.USER:
    #             messages.append(HumanMessage(content=msg.content))
    #         else:
    #             messages.append(AIMessage(content=msg.content))
    #
    #     # 加入当前问题
    #     messages.append(HumanMessage(content=question))
    #     return messages

    def _format_prompt_for_trace(self, messages: list) -> str:
        """把消息列表格式化为可读字符串，用于日志记录"""
        lines = []
        for msg in messages:
            role = msg.__class__.__name__.replace("Message", "").upper()
            lines.append(f"[{role}]\n{msg.content}")
        return "\n\n".join(lines)

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
        retrieved_docs = await hybrid_searcher.search(
            db=db,
            document_id=document_id,
            query=question,
            k=4,
            fetch_k=20,
        )

        context = "\n\n".join([d.page_content for d in retrieved_docs])
        logger.debug(f"检索到 {len(retrieved_docs)} 个切片 session={session_id}")

        retrieved_chunks_json = json.dumps(
            [d.page_content for d in retrieved_docs],
            ensure_ascii=False,
        )

        # 3. 拉取历史，组装消息
        history = await conversation_repo.get_by_session(db, session_id)

        # 4. 组装消息
        messages = self._build_messages(context, history, question)
        prompt_str = self._format_prompt_for_trace(messages)

        # 5. 存储用户消息
        await conversation_repo.add_message(
            db, session_id, document_id, MessageRole.USER, question
        )

        # 6. 流式调用 LLM，逐 token yield
        llm = self._build_llm()
        full_response = []
        start_time = time.time()
        status = "success"
        error_msg = None

        try:
            async for chunk in llm.astream(messages):
                token = chunk.content
                if token:
                    full_response.append(token)
                    yield token

        except Exception as e:
            status = "failed"
            error_msg = str(e)
            logger.error(f"LLM 调用失败: {e}")
            yield f"\n\n[错误：{str(e)}]"

        finally:
            latency_ms = (time.time() - start_time) * 1000
            full_answer = "".join(full_response)

            # 7. 存 LLM 回答
            if full_answer:
                await conversation_repo.add_message(
                    db, session_id, document_id, MessageRole.ASSISTANT, full_answer
                )

            # 8. 写链路日志
            await llm_trace_repo.create_trace(
                db,
                {
                    "session_id": session_id,
                    "document_id": document_id,
                    "question": question,
                    "retrieved_chunks": retrieved_chunks_json,
                    "prompt": prompt_str,
                    "answer": full_answer,
                    "latency_ms": round(latency_ms, 2),
                    "model_name": "deepseek-chat",
                    "status": status,
                    "error_msg": error_msg,
                },
            )

            logger.info(
                f"问答完成 session={session_id} "
                f"latency={latency_ms:.0f}ms "
                f"answer_len={len(full_answer)} "
                f"status={status}"
            )

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
