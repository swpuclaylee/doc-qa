import time
from collections.abc import AsyncGenerator

#from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
#from langchain_openai import ChatOpenAI
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from src.agent.executor import agent_runner
from src.core.cache.redis_ops import redis_cache
#from src.core.config import settings
from src.models.conversation import MessageRole
from src.repository.conversation import conversation_repo
from src.repository.document import document_repo
from src.repository.llm_trace import llm_trace_repo
from src.schemas.chat import ChatHistoryOut, ChatMode, ConversationOut, SourceRef

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
    """
    聊天业务层，协调 Agent 执行、对话历史存储和链路日志记录。

    主要职责：
    - 校验文档状态（doc_qa 模式）
    - 读取/写入对话历史（conversation_repo）
    - 调用 AgentRunner 流式执行并转发 token
    - 将 list[SourceRef] sentinel 转换为 __SOURCES_EVENT__ 标记（传给 endpoint）
    - 在 finally 块写链路日志（llm_trace_repo），无论成功失败均记录
    """

    # def _build_llm(self) -> ChatOpenAI:
    #     """构建 LLM 实例"""
    #     return ChatOpenAI(
    #         model="deepseek-chat",
    #         api_key=settings.DEEPSEEK_API_KEY,
    #         base_url=settings.DEEPSEEK_BASE_URL,
    #         temperature=0.3,
    #         streaming=True,
    #     )

    # def _estimate_tokens(self, text: str) -> int:
    #     """
    #     估算文本的 token 数
    #
    #     粗略规则：
    #     - 中文字符：1 字 ≈ 1 token
    #     - 英文/其他：4 字符 ≈ 1 token
    #     """
    #     chinese_chars = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
    #     other_chars = len(text) - chinese_chars
    #     return chinese_chars + other_chars // 4

    # def _build_messages(
    #     self,
    #     context: str,
    #     history: list,
    #     question: str,
    # ) -> list:
    #     """
    #     组装消息列表，按 token 预算动态截断历史
    #
    #     优先保留最近的对话，超出预算的早期消息直接丢弃。
    #     """
    #     messages = [SystemMessage(content=SYSTEM_PROMPT.format(context=context))]
    #
    #     # 从最新消息往最旧遍历，累计 token 数不超过预算
    #     total_tokens = 0
    #     trimmed_history = []
    #
    #     for msg in reversed(history):
    #         tokens = self._estimate_tokens(msg.content)
    #         if total_tokens + tokens > MAX_HISTORY_TOKENS:
    #             break
    #         trimmed_history.insert(0, msg)
    #         total_tokens += tokens
    #
    #     if len(trimmed_history) < len(history):
    #         logger.debug(
    #             f"历史消息截断: 原始 {len(history)} 条 "
    #             f"→ 保留 {len(trimmed_history)} 条 "
    #             f"token 预算 {MAX_HISTORY_TOKENS}"
    #         )
    #
    #     # 加入历史消息
    #     for msg in trimmed_history:
    #         if msg.role == MessageRole.USER:
    #             messages.append(HumanMessage(content=msg.content))
    #         else:
    #             messages.append(AIMessage(content=msg.content))
    #
    #     # 加入当前问题
    #     messages.append(HumanMessage(content=question))
    #     return messages

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

    # def _format_prompt_for_trace(self, messages: list) -> str:
    #     """把消息列表格式化为可读字符串，用于日志记录"""
    #     lines = []
    #     for msg in messages:
    #         role = msg.__class__.__name__.replace("Message", "").upper()
    #         lines.append(f"[{role}]\n{msg.content}")
    #     return "\n\n".join(lines)

    # 第五版（当前）：多模式
    async def chat_stream(
        self,
        db: AsyncSession,
        document_ids: list[int] | None,
        session_id: str,
        question: str,
        mode: ChatMode = ChatMode.DOC_QA,
    ) -> AsyncGenerator[str, None]:
        """
        流式问答主方法，以 AsyncGenerator 形式 yield 内容。

        数据流：
          AgentRunner → str tokens → yield token
                      → list[SourceRef] sentinel → yield "__SOURCES_EVENT__:{json}"

        Args:
            db: 数据库会话
            document_ids: 文档 ID 列表（doc_qa 模式必填，其他模式可为 None）
            session_id: 会话 ID
            question: 用户问题
            mode: 聊天模式（doc_qa / free_chat / free_doc_chat）

        Yields:
            str: 回答 token 或 "__SOURCES_EVENT__:{json}" 来源事件标记
        """
        # 1. 文档校验（仅 doc_qa 模式）
        if mode == ChatMode.DOC_QA:
            for doc_id in document_ids or []:
                doc = await document_repo.get(db, doc_id)
                if not doc:
                    yield f"错误：文档 {doc_id} 不存在"
                    return
                if doc.status.value != "done":
                    yield f"错误：文档 {doc_id} 尚未处理完成（当前状态：{doc.status.value}）"
                    return

        # 2. 拉取历史（两种模式相同）
        history = await conversation_repo.get_by_session(db, session_id)

        # 3. 存用户消息（document_ids 对 free_chat 为空列表）
        await conversation_repo.add_message(
            db, session_id, document_ids or [], MessageRole.USER, question
        )

        # 4. 执行 Agent
        full_response = []
        final_sources: list[SourceRef] = []
        start_time = time.time()
        status = "success"
        error_msg = None

        try:
            async for item in agent_runner.run_stream_with_sources(
                db=db,
                document_ids=document_ids,
                session_id=session_id,
                question=question,
                history=history,
                redis_client=redis_cache,
                mode=mode,  # ← 透传模式
            ):
                if isinstance(item, list):
                    final_sources = item
                    if (
                        mode in (ChatMode.DOC_QA, ChatMode.FREE_DOC_CHAT)
                        and final_sources
                    ):
                        # 仅文档问答模式发送 sources 事件
                        import json

                        sources_json = json.dumps(
                            [s.model_dump() for s in final_sources],
                            ensure_ascii=False,
                        )
                        yield f"__SOURCES_EVENT__:{sources_json}"
                else:
                    full_response.append(item)
                    yield item

        except Exception as e:
            status = "failed"
            error_msg = str(e)
            yield f"\n\n[错误：{str(e)}]"

        finally:
            latency_ms = (time.time() - start_time) * 1000
            full_answer = "".join(full_response)

            if full_answer:
                await conversation_repo.add_message(
                    db,
                    session_id,
                    document_ids or [],
                    MessageRole.ASSISTANT,
                    full_answer,
                )

            import json

            sources_json = (
                json.dumps(
                    [s.model_dump() for s in final_sources],
                    ensure_ascii=False,
                )
                if final_sources
                else None
            )

            await llm_trace_repo.create_trace(
                db,
                {
                    "session_id": session_id,
                    "document_id": (document_ids[0] if document_ids else None),
                    "question": question,
                    "retrieved_chunks": sources_json,
                    "prompt": question,
                    "answer": full_answer,
                    "latency_ms": round(latency_ms, 2),
                    "model_name": "deepseek-chat",
                    "status": status,
                    "error_msg": error_msg,
                },
            )

    # 第四版：多文档，加来源信息
    # async def chat_stream(
    #     self,
    #     db: AsyncSession,
    #     document_ids: list[int],
    #     session_id: str,
    #     question: str,
    # ) -> AsyncGenerator[str, None]:
    #     # 1. 批量校验文档（不变）
    #     for doc_id in document_ids:
    #         doc = await document_repo.get(db, doc_id)
    #         if not doc:
    #             yield f"错误：文档 {doc_id} 不存在"
    #             return
    #         if doc.status.value != "done":
    #             yield f"错误：文档 {doc_id} 尚未处理完成（当前状态：{doc.status.value}）"
    #             return
    #
    #     # 2. 拉取历史（不变）
    #     history = await conversation_repo.get_by_session(db, session_id)
    #
    #     # 3. 存用户消息（不变）
    #     await conversation_repo.add_message(
    #         db, session_id, document_ids, MessageRole.USER, question
    #     )
    #
    #     # 4. 执行 Agent，区分 token 和 sources
    #     full_response = []
    #     final_sources: list[SourceRef] = []
    #     start_time = time.time()
    #     status = "success"
    #     error_msg = None
    #
    #     try:
    #         async for item in agent_runner.run_stream_with_sources(
    #             db=db,
    #             document_ids=document_ids,
    #             session_id=session_id,
    #             question=question,
    #             history=history,
    #             redis_client=redis_cache,
    #         ):
    #             if isinstance(item, list):
    #                 # 最后一次 yield：来源列表
    #                 final_sources = item
    #                 # 以特殊标记发送给上层（endpoint 解析后包装为 sources 事件）
    #                 import json
    #
    #                 sources_json = json.dumps(
    #                     [s.model_dump() for s in final_sources],
    #                     ensure_ascii=False,
    #                 )
    #                 yield f"__SOURCES_EVENT__:{sources_json}"
    #             else:
    #                 # 普通 token
    #                 full_response.append(item)
    #                 yield item
    #
    #     except Exception as e:
    #         status = "failed"
    #         error_msg = str(e)
    #         yield f"\n\n[错误：{str(e)}]"
    #
    #     finally:
    #         latency_ms = (time.time() - start_time) * 1000
    #         full_answer = "".join(full_response)
    #
    #         if full_answer:
    #             await conversation_repo.add_message(
    #                 db, session_id, document_ids, MessageRole.ASSISTANT, full_answer
    #             )
    #
    #         # 存储 sources 到 trace
    #         import json
    #
    #         sources_json = (
    #             json.dumps(
    #                 [s.model_dump() for s in final_sources],
    #                 ensure_ascii=False,
    #             )
    #             if final_sources
    #             else None
    #         )
    #
    #         await llm_trace_repo.create_trace(
    #             db,
    #             {
    #                 "session_id": session_id,
    #                 "document_id": document_ids[0] if document_ids else None,
    #                 "question": question,
    #                 "retrieved_chunks": sources_json,  # ← 存储来源结构
    #                 "prompt": question,
    #                 "answer": full_answer,
    #                 "latency_ms": round(latency_ms, 2),
    #                 "model_name": "deepseek-chat",
    #                 "status": status,
    #                 "error_msg": error_msg,
    #             },
    #         )

    # 第三版：多文档，Agent
    # async def chat_stream(
    #         self,
    #         db: AsyncSession,
    #         document_ids: list[int],  # ← 改为列表
    #         session_id: str,
    #         question: str,
    # ) -> AsyncGenerator[str, None]:
    #     # 1. 批量校验文档
    #     for doc_id in document_ids:
    #         doc = await document_repo.get(db, doc_id)
    #         if not doc:
    #             yield f"错误：文档 {doc_id} 不存在"
    #             return
    #         if doc.status.value != "done":
    #             yield f"错误：文档 {doc_id} 尚未处理完成（当前状态：{doc.status.value}）"
    #             return
    #
    #     # 2. 拉取历史
    #     history = await conversation_repo.get_by_session(db, session_id)
    #
    #     # 3. 存用户消息（document_ids 序列化后存入 document_ids 字段）
    #     await conversation_repo.add_message(
    #         db, session_id, document_ids, MessageRole.USER, question
    #     )
    #
    #     # 4. 执行 Agent 流式推理
    #     full_response = []
    #     start_time = time.time()
    #     status = "success"
    #     error_msg = None
    #
    #     try:
    #         async for token in agent_runner.run_stream(
    #                 db=db,
    #                 document_ids=document_ids,  # ← 改为列表
    #                 session_id=session_id,
    #                 question=question,
    #                 history=history,
    #                 redis_client=redis_cache,
    #         ):
    #             full_response.append(token)
    #             yield token
    #
    #     except Exception as e:
    #         status = "failed"
    #         error_msg = str(e)
    #         yield f"\n\n[错误：{str(e)}]"
    #
    #     finally:
    #         latency_ms = (time.time() - start_time) * 1000
    #         full_answer = "".join(full_response)
    #
    #         if full_answer:
    #             await conversation_repo.add_message(
    #                 db, session_id, document_ids, MessageRole.ASSISTANT, full_answer
    #             )
    #
    #         await llm_trace_repo.create_trace(
    #             db,
    #             {
    #                 "session_id": session_id,
    #                 "document_id": document_ids[0],  # 取第一个作为主文档（兼容现有表结构）
    #                 "question": question,
    #                 "retrieved_chunks": None,
    #                 "prompt": question,
    #                 "answer": full_answer,
    #                 "latency_ms": round(latency_ms, 2),
    #                 "model_name": "deepseek-chat",
    #                 "status": status,
    #                 "error_msg": error_msg,
    #             },
    #         )

    # 第二版：单文档，引入Agent
    # async def chat_stream(
    #     self,
    #     db: AsyncSession,
    #     document_id: int,
    #     session_id: str,
    #     question: str,
    # ) -> AsyncGenerator[str, None]:
    #     # 1. 校验文档
    #     doc = await document_repo.get(db, document_id)
    #     if not doc:
    #         yield "错误：文档不存在"
    #         return
    #     if doc.status.value != "done":
    #         yield f"错误：文档尚未处理完成（当前状态：{doc.status.value}）"
    #         return
    #
    #     # 2. 拉取历史
    #     history = await conversation_repo.get_by_session(db, session_id)
    #
    #     # 3. 存用户消息
    #     await conversation_repo.add_message(
    #         db, session_id, document_id, MessageRole.USER, question
    #     )
    #
    #     # 4. 执行 Agent 流式推理
    #     full_response = []
    #     start_time = time.time()
    #     status = "success"
    #     error_msg = None
    #
    #     try:
    #         async for token in agent_runner.run_stream(
    #             db=db,
    #             document_id=document_id,
    #             session_id=session_id,
    #             question=question,
    #             history=history,
    #             redis_client=redis_cache,  # 新增
    #         ):
    #             full_response.append(token)
    #             yield token
    #
    #     except Exception as e:
    #         status = "failed"
    #         error_msg = str(e)
    #         yield f"\n\n[错误：{str(e)}]"
    #
    #     finally:
    #         latency_ms = (time.time() - start_time) * 1000
    #         full_answer = "".join(full_response)
    #
    #         if full_answer:
    #             await conversation_repo.add_message(
    #                 db, session_id, document_id, MessageRole.ASSISTANT, full_answer
    #             )
    #
    #         # 写链路日志
    #         await llm_trace_repo.create_trace(
    #             db,
    #             {
    #                 "session_id": session_id,
    #                 "document_id": document_id,
    #                 "question": question,
    #                 "retrieved_chunks": None,  # Agent 自主决定是否检索
    #                 "prompt": question,
    #                 "answer": full_answer,
    #                 "latency_ms": round(latency_ms, 2),
    #                 "model_name": "deepseek-chat",
    #                 "status": status,
    #                 "error_msg": error_msg,
    #             },
    #         )

    # 第一版：单文档，手动RAG，直接调LLM
    # async def chat_stream(
    #     self,
    #     db: AsyncSession,
    #     document_id: int,
    #     session_id: str,
    #     question: str,
    # ) -> AsyncGenerator[str, None]:
    #     """
    #     流式问答，返回一个异步生成器，逐 token yield 回答内容
    #
    #     Args:
    #         db: 数据库会话
    #         document_id: 针对哪个文档提问
    #         session_id: 会话 ID
    #         question: 用户问题
    #
    #     Yields:
    #         str: 每次 yield 一个 token
    #     """
    #     # 1. 校验文档存在且处理完成
    #     doc = await document_repo.get(db, document_id)
    #     if not doc:
    #         yield "错误：文档不存在"
    #         return
    #     if doc.status.value != "done":
    #         yield f"错误：文档尚未处理完成（当前状态：{doc.status.value}）"
    #         return
    #
    #     # 2. 检索相关文档切片
    #     retrieved_docs = await hybrid_searcher.search(
    #         db=db,
    #         document_id=document_id,
    #         query=question,
    #         k=4,
    #         fetch_k=20,
    #     )
    #
    #     context = "\n\n".join([d.page_content for d in retrieved_docs])
    #     logger.debug(f"检索到 {len(retrieved_docs)} 个切片 session={session_id}")
    #
    #     retrieved_chunks_json = json.dumps(
    #         [d.page_content for d in retrieved_docs],
    #         ensure_ascii=False,
    #     )
    #
    #     # 3. 拉取历史，组装消息
    #     history = await conversation_repo.get_by_session(db, session_id)
    #
    #     # 4. 组装消息
    #     messages = self._build_messages(context, history, question)
    #     prompt_str = self._format_prompt_for_trace(messages)
    #
    #     # 5. 存储用户消息
    #     await conversation_repo.add_message(
    #         db, session_id, document_id, MessageRole.USER, question
    #     )
    #
    #     # 6. 流式调用 LLM，逐 token yield
    #     llm = self._build_llm()
    #     full_response = []
    #     start_time = time.time()
    #     status = "success"
    #     error_msg = None
    #
    #     try:
    #         async for chunk in llm.astream(messages):
    #             token = chunk.content
    #             if token:
    #                 full_response.append(token)
    #                 yield token
    #
    #     except Exception as e:
    #         status = "failed"
    #         error_msg = str(e)
    #         logger.error(f"LLM 调用失败: {e}")
    #         yield f"\n\n[错误：{str(e)}]"
    #
    #     finally:
    #         latency_ms = (time.time() - start_time) * 1000
    #         full_answer = "".join(full_response)
    #
    #         # 7. 存 LLM 回答
    #         if full_answer:
    #             await conversation_repo.add_message(
    #                 db, session_id, document_id, MessageRole.ASSISTANT, full_answer
    #             )
    #
    #         # 8. 写链路日志
    #         await llm_trace_repo.create_trace(
    #             db,
    #             {
    #                 "session_id": session_id,
    #                 "document_id": document_id,
    #                 "question": question,
    #                 "retrieved_chunks": retrieved_chunks_json,
    #                 "prompt": prompt_str,
    #                 "answer": full_answer,
    #                 "latency_ms": round(latency_ms, 2),
    #                 "model_name": "deepseek-chat",
    #                 "status": status,
    #                 "error_msg": error_msg,
    #             },
    #         )
    #
    #         logger.info(
    #             f"问答完成 session={session_id} "
    #             f"latency={latency_ms:.0f}ms "
    #             f"answer_len={len(full_answer)} "
    #             f"status={status}"
    #         )

    async def get_history(
        self, db: AsyncSession, session_id: str, document_id: int
    ) -> ChatHistoryOut:
        """
        获取指定会话的对话历史。

        Returns:
            ChatHistoryOut: 包含会话 ID 和消息列表
        """
        messages = await conversation_repo.get_by_session(db, session_id)
        return ChatHistoryOut(
            session_id=session_id,
            document_id=document_id,
            messages=[ConversationOut.model_validate(m) for m in messages],
        )

    async def clear_history(self, db: AsyncSession, session_id: str) -> int:
        """
        清空指定会话的所有对话记录。

        Returns:
            int: 实际删除的记录条数
        """
        count = await conversation_repo.delete_by_session(db, session_id)
        logger.info(f"清空会话历史 session={session_id} count={count}")
        return count


chat_service = ChatService()
