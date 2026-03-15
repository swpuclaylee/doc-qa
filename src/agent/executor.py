import json
from collections.abc import AsyncGenerator

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from src.agent.tools import (
    calculator,
    get_current_time,
    get_search_all_documents_tool,
    get_search_documents_tool,
)
from src.core.config import settings
from src.core.summary_memory import summary_memory_manager
from src.models.conversation import MessageRole
from src.schemas.chat import ChatMode, SourceRef

# SYSTEM_PROMPT = """你是一个专业的文档问答助手。
#
# 你有以下工具可以使用：
# - search_document：在文档中检索相关内容，回答文档相关问题时必须调用
# - get_current_time：获取当前时间
# - calculator：数学计算
#
# 工作原则：
# - 回答文档相关问题时，必须先调用 search_document 检索，基于检索结果回答
# - 如果检索结果中没有相关信息，明确告知用户
# - 不要编造文档中没有的内容
# - 回答简洁、准确、有条理
# """

SYSTEM_PROMPT = """你是一个专业的文档问答助手。

你有以下工具可以使用：
- search_documents：在一组文档中检索相关内容，回答文档相关问题时必须调用
- get_current_time：获取当前时间
- calculator：数学计算

工作原则：
- 回答文档相关问题时，必须先调用 search_documents 检索，基于检索结果回答
- 检索结果中会标注每个片段来自哪个文档（文档ID），回答时可以提及信息来源
- 如果检索结果中没有相关信息，明确告知用户
- 如果多个文档都有相关信息，综合各文档内容给出完整回答
- 不要编造文档中没有的内容
- 回答简洁、准确、有条理
"""


# 新增自由聊天专用系统提示
FREE_CHAT_SYSTEM_PROMPT = """你是一个智能助手，可以回答各种问题、进行创意写作、分析数据、提供建议等。

你有以下工具可以使用：
- get_current_time：获取当前时间
- calculator：数学计算

工作原则：
- 根据用户问题直接给出高质量回答
- 如需数学计算，使用 calculator 工具
- 如需当前时间，使用 get_current_time 工具
- 回答准确、清晰、有帮助
"""

# 文档自由提示词
FREE_DOC_CHAT_SYSTEM_PROMPT = """你是一个智能文档助手，可以检索知识库中的任意文档来回答问题。

你有以下工具可以使用：
- search_all_documents：在知识库全部文档中检索相关内容
- get_current_time：获取当前时间
- calculator：数学计算

工作原则：
- 回答知识库相关问题时，必须先调用 search_all_documents 检索
- 检索结果会标注每个片段的来源文档，回答时可提及信息来源
- 如果知识库中没有相关内容，明确告知用户并说明无法从文档中找到答案
- 不要编造知识库中没有的内容
- 回答简洁、准确、有条理
"""


class AgentRunner:
    """
    LangGraph ReAct Agent 执行器。

    封装了 create_react_agent 的完整执行流程，包括：
    - 按模式（doc_qa / free_chat / free_doc_chat）选择工具集和系统提示
    - 对话摘要压缩（超过阈值自动压缩早期历史到 Redis）
    - 流式 token 输出（on_chat_model_stream 事件过滤）
    - 来源引用收集（on_tool_end 事件解析 __SOURCES__: 标记）
    """

    def _build_llm(self) -> ChatOpenAI:
        """
        构建 DeepSeek LLM 实例（streaming=True 支持流式输出）。
        每次调用都新建实例，避免跨请求共享状态。
        """
        return ChatOpenAI(
            model="deepseek-chat",
            api_key=settings.DEEPSEEK_API_KEY,
            base_url=settings.DEEPSEEK_BASE_URL,
            temperature=0.7,
            streaming=True,
        )

    # def _build_messages(self, history: list, question: str) -> list:
    #     """
    #     组装输入消息列表：SystemMessage + 历史对话 + 当前问题
    #
    #     LangGraph create_react_agent 直接接收消息列表，
    #     不需要 ChatPromptTemplate 或 MessagesPlaceholder。
    #     """
    #     messages = [SystemMessage(content=SYSTEM_PROMPT)]
    #
    #     for msg in history:
    #         if msg.role == MessageRole.USER:
    #             messages.append(HumanMessage(content=msg.content))
    #         else:
    #             messages.append(AIMessage(content=msg.content))
    #
    #     messages.append(HumanMessage(content=question))
    #     return messages

    # def _build_messages(
    #     self,
    #     history: list,
    #     question: str,
    #     summary: str = "",  # 新增参数
    # ) -> list:
    #     """
    #     组装消息列表（SYSTEM + 摘要 + 历史 + 当前问题）。
    #
    #     若有摘要，以 Human+AI 对话对形式注入，模拟"前情提要"，
    #     避免直接插入 SystemMessage 导致 LangGraph 无法正确解析。
    #
    #     Args:
    #         history: 近期历史消息（Conversation ORM 对象列表）
    #         question: 当前用户问题
    #         summary: 已压缩的早期历史摘要（可为空）
    #     """
    #     messages = [SystemMessage(content=SYSTEM_PROMPT)]
    #
    #     # 若有摘要，以 HumanMessage 形式插入（模拟对话上下文的前情提要）
    #     if summary:
    #         messages.append(HumanMessage(content=f"[以下是早期对话摘要，请作为背景信息参考]\n{summary}"))
    #         messages.append(AIMessage(content="好的，我已了解早期对话背景，请继续。"))
    #
    #     for msg in history:
    #         if msg.role == MessageRole.USER:
    #             messages.append(HumanMessage(content=msg.content))
    #         else:
    #             messages.append(AIMessage(content=msg.content))
    #
    #     messages.append(HumanMessage(content=question))
    #     return messages

    def _build_messages_with_prompt(
        self,
        history: list,
        question: str,
        summary: str = "",
        system_prompt: str = SYSTEM_PROMPT,  # 默认使用文档问答提示
    ) -> list:
        """
        组装消息列表（SYSTEM + 摘要 + 历史 + 当前问题）。

        若有摘要，以 Human+AI 对话对形式注入，模拟"前情提要"，
        避免直接插入 SystemMessage 导致 LangGraph 无法正确解析。

        Args:
            history: 近期历史消息（Conversation ORM 对象列表）
            question: 当前用户问题
            summary: 已压缩的早期历史摘要（可为空）
            system_prompt: 系统提示词
        """
        messages = [SystemMessage(content=system_prompt)]

        if summary:
            messages.append(HumanMessage(content=f"[以下是早期对话摘要，请作为背景信息参考]\n{summary}"))
            messages.append(AIMessage(content="好的，我已了解早期对话背景，请继续。"))

        for msg in history:
            if msg.role == MessageRole.USER:
                messages.append(HumanMessage(content=msg.content))
            else:
                messages.append(AIMessage(content=msg.content))

        messages.append(HumanMessage(content=question))
        return messages

    # async def run_stream(
    #     self,
    #     db: AsyncSession,
    #     document_id: int,
    #     session_id: str,
    #     question: str,
    #     history: list,
    # ) -> AsyncGenerator[str, None]:
    #     """
    #     流式执行 Agent（LangGraph ReAct 实现）
    #
    #     执行过程：
    #     1. LLM 收到消息，判断是否需要调用工具
    #     2. 如需要，调用工具获取结果（不 yield）
    #     3. 将工具结果拼入上下文，生成最终回答（逐 token yield）
    #
    #     事件过滤逻辑：
    #     - langgraph_node == "agent"：LLM 推理节点产生的事件
    #     - not chunk.tool_call_chunks：排除工具调用决策片段，只取文字回答
    #     """
    #     tools = [
    #         get_search_document_tool(document_id, db),
    #         get_current_time,
    #         calculator,
    #     ]
    #
    #     llm = self._build_llm()
    #     messages = self._build_messages(history, question)
    #
    #     # create_react_agent 是 LangChain 1.x 的推荐替代方案
    #     # 取代了已移除的 AgentExecutor + create_tool_calling_agent
    #     agent = create_react_agent(model=llm, tools=tools)
    #
    #     full_response = []
    #
    #     try:
    #         async for event in agent.astream_events(
    #             {"messages": messages},
    #             # recursion_limit=10 约等于旧版 max_iterations=5
    #             # LangGraph 每轮工具调用占 2 步（LLM决策 + 工具执行）
    #             config={"recursion_limit": 10},
    #             version="v2",
    #         ):
    #             if (
    #                 event["event"] == "on_chat_model_stream"
    #                 and event["metadata"].get("langgraph_node") == "agent"
    #             ):
    #                 chunk = event["data"]["chunk"]
    #                 # tool_call_chunks 非空 → LLM 正在生成工具调用参数，跳过
    #                 # content 非空且无 tool_call_chunks → 最终文字回答，yield
    #                 if chunk.content and not chunk.tool_call_chunks:
    #                     full_response.append(chunk.content)
    #                     yield chunk.content
    #
    #     except Exception as e:
    #         logger.error(f"Agent 执行失败: session={session_id} error={e}")
    #         yield f"\n\n[错误：{str(e)}]"
    #         return
    #
    #     logger.info(
    #         f"Agent 执行完成: session={session_id} "
    #         f"answer_len={len(''.join(full_response))}"
    #     )

    # async def run_stream(
    #     self,
    #     db: AsyncSession,
    #     document_id: int,
    #     session_id: str,
    #     question: str,
    #     history: list,
    #     redis_client,
    # ) -> AsyncGenerator[str, None]:
    #     """
    #     流式执行 Agent（LangGraph ReAct 实现）
    #
    #     执行过程：
    #     1. LLM 收到消息，判断是否需要调用工具
    #     2. 如需要，调用工具获取结果（不 yield）
    #     3. 将工具结果拼入上下文，生成最终回答（逐 token yield）
    #
    #     事件过滤逻辑：
    #     - langgraph_node == "agent"：LLM 推理节点产生的事件
    #     - not chunk.tool_call_chunks：排除工具调用决策片段，只取文字回答
    #     """
    #     # 1. 读取已有摘要
    #     existing_summary = await redis_client.get(f"summary:{session_id}") or ""
    #     if isinstance(existing_summary, bytes):
    #         existing_summary = existing_summary.decode()
    #
    #     # 2. 判断是否需要压缩
    #     summary, recent_history = await summary_memory_manager.compress(
    #         session_id=session_id,
    #         history=history,
    #         existing_summary=existing_summary,
    #         redis_client=redis_client,
    #     )
    #
    #     # 3. 组装消息（传入摘要 + 近期历史）
    #     messages = self._build_messages(recent_history, question, summary=summary)
    #
    #     tools = [
    #         get_search_document_tool(document_id, db),
    #         get_current_time,
    #         calculator,
    #     ]
    #
    #     llm = self._build_llm()
    #
    #     # create_react_agent 是 LangChain 1.x 的推荐替代方案
    #     # 取代了已移除的 AgentExecutor + create_tool_calling_agent
    #     agent = create_react_agent(model=llm, tools=tools)
    #
    #     full_response = []
    #
    #     try:
    #         async for event in agent.astream_events(
    #             {"messages": messages},
    #             # recursion_limit=10 约等于旧版 max_iterations=5
    #             # LangGraph 每轮工具调用占 2 步（LLM决策 + 工具执行）
    #             config={"recursion_limit": 10},
    #             version="v2",
    #         ):
    #             if (
    #                 event["event"] == "on_chat_model_stream"
    #                 and event["metadata"].get("langgraph_node") == "agent"
    #             ):
    #                 chunk = event["data"]["chunk"]
    #                 # tool_call_chunks 非空 → LLM 正在生成工具调用参数，跳过
    #                 # content 非空且无 tool_call_chunks → 最终文字回答，yield
    #                 if chunk.content and not chunk.tool_call_chunks:
    #                     full_response.append(chunk.content)
    #                     yield chunk.content
    #
    #     except Exception as e:
    #         logger.error(f"Agent 执行失败: session={session_id} error={e}")
    #         yield f"\n\n[错误：{str(e)}]"
    #         return
    #
    #     logger.info(
    #         f"Agent 执行完成: session={session_id} "
    #         f"answer_len={len(''.join(full_response))}"
    #     )

    # async def run_stream(
    #     self,
    #     db: AsyncSession,
    #     document_ids: list[int],
    #     session_id: str,
    #     question: str,
    #     history: list,
    #     redis_client,
    # ) -> AsyncGenerator[str, None]:
    #     """
    #     流式执行 Agent（LangGraph ReAct 实现）
    #
    #     执行过程：
    #     1. LLM 收到消息，判断是否需要调用工具
    #     2. 如需要，调用工具获取结果（不 yield）
    #     3. 将工具结果拼入上下文，生成最终回答（逐 token yield）
    #
    #     事件过滤逻辑：
    #     - langgraph_node == "agent"：LLM 推理节点产生的事件
    #     - not chunk.tool_call_chunks：排除工具调用决策片段，只取文字回答
    #     """
    #     # 1. 读取已有摘要
    #     existing_summary = await redis_client.get(f"summary:{session_id}") or ""
    #     if isinstance(existing_summary, bytes):
    #         existing_summary = existing_summary.decode()
    #
    #     # 2. 判断是否需要压缩
    #     summary, recent_history = await summary_memory_manager.compress(
    #         session_id=session_id,
    #         history=history,
    #         existing_summary=existing_summary,
    #         redis_client=redis_client,
    #     )
    #
    #     # 3. 组装消息（传入摘要 + 近期历史）
    #     messages = self._build_messages(recent_history, question, summary=summary)
    #
    #     tools = [
    #         get_search_documents_tool(document_ids, db),
    #         get_current_time,
    #         calculator,
    #     ]
    #
    #     llm = self._build_llm()
    #
    #     # create_react_agent 是 LangChain 1.x 的推荐替代方案
    #     # 取代了已移除的 AgentExecutor + create_tool_calling_agent
    #     agent = create_react_agent(model=llm, tools=tools)
    #
    #     full_response = []
    #
    #     try:
    #         async for event in agent.astream_events(
    #             {"messages": messages},
    #             # recursion_limit=10 约等于旧版 max_iterations=5
    #             # LangGraph 每轮工具调用占 2 步（LLM决策 + 工具执行）
    #             config={"recursion_limit": 10},
    #             version="v2",
    #         ):
    #             if (
    #                 event["event"] == "on_chat_model_stream"
    #                 and event["metadata"].get("langgraph_node") == "agent"
    #             ):
    #                 chunk = event["data"]["chunk"]
    #                 # tool_call_chunks 非空 → LLM 正在生成工具调用参数，跳过
    #                 # content 非空且无 tool_call_chunks → 最终文字回答，yield
    #                 if chunk.content and not chunk.tool_call_chunks:
    #                     full_response.append(chunk.content)
    #                     yield chunk.content
    #
    #     except Exception as e:
    #         logger.error(f"Agent 执行失败: session={session_id} error={e}")
    #         yield f"\n\n[错误：{str(e)}]"
    #         return
    #
    #     logger.info(
    #         f"Agent 执行完成: session={session_id} "
    #         f"answer_len={len(''.join(full_response))}"
    #     )

    # async def run_stream_with_sources(
    #     self,
    #     db: AsyncSession,
    #     document_ids: list[int],
    #     session_id: str,
    #     question: str,
    #     history: list,
    #     redis_client,
    # ) -> AsyncGenerator[str | list[SourceRef], None]:
    #     """
    #     流式执行 Agent，同时收集检索来源。
    #
    #     Yields:
    #         str：正常回答 token
    #         list[SourceRef]：最后 yield 一次来源列表（用 sentinel 区分）
    #     """
    #     # 1. 摘要压缩（不变）
    #     existing_summary = await redis_client.get(f"summary:{session_id}") or ""
    #     if isinstance(existing_summary, bytes):
    #         existing_summary = existing_summary.decode()
    #
    #     summary, recent_history = await summary_memory_manager.compress(
    #         session_id=session_id,
    #         history=history,
    #         existing_summary=existing_summary,
    #         redis_client=redis_client,
    #     )
    #
    #     # 2. 组装消息（不变）
    #     messages = self._build_messages(recent_history, question, summary=summary)
    #
    #     tools = [
    #         get_search_documents_tool(document_ids, db),
    #         get_current_time,
    #         calculator,
    #     ]
    #
    #     llm = self._build_llm()
    #     agent = create_react_agent(model=llm, tools=tools)
    #
    #     full_response = []
    #     collected_sources: list[SourceRef] = []  # ← 新增：收集来源
    #
    #     try:
    #         async for event in agent.astream_events(
    #             {"messages": messages},
    #             config={"recursion_limit": 10},
    #             version="v2",
    #         ):
    #             event_type = event["event"]
    #
    #             # 收集工具执行结果，提取来源
    #             if event_type == "on_tool_end":
    #                 tool_output = event.get("data", {}).get("output", "")
    #                 if isinstance(tool_output, str) and "__SOURCES__:" in tool_output:
    #                     _, sources_json = tool_output.rsplit("__SOURCES__:", 1)
    #                     try:
    #                         raw_sources = json.loads(sources_json.strip())
    #                         for s in raw_sources:
    #                             source = SourceRef(
    #                                 document_id=s["document_id"],
    #                                 chunk_index=s["chunk_index"],
    #                                 snippet=s["snippet"],
    #                             )
    #                             # 去重：同一文档同一片段只保留一次
    #                             if not any(
    #                                 x.document_id == source.document_id
    #                                 and x.chunk_index == source.chunk_index
    #                                 for x in collected_sources
    #                             ):
    #                                 collected_sources.append(source)
    #                     except (json.JSONDecodeError, KeyError):
    #                         pass  # 解析失败静默忽略
    #
    #             # 正常 token 输出（与之前相同）
    #             if (
    #                 event_type == "on_chat_model_stream"
    #                 and event["metadata"].get("langgraph_node") == "agent"
    #             ):
    #                 chunk = event["data"]["chunk"]
    #                 if chunk.content and not chunk.tool_call_chunks:
    #                     full_response.append(chunk.content)
    #                     yield chunk.content
    #
    #     except Exception as e:
    #         logger.error(f"Agent 执行失败: session={session_id} error={e}")
    #         yield f"\n\n[错误：{str(e)}]"
    #         return
    #
    #     # 最后 yield 来源列表（调用方通过类型判断区分）
    #     yield collected_sources
    #
    #     logger.info(
    #         f"Agent 执行完成: session={session_id} "
    #         f"answer_len={len(''.join(full_response))} "
    #         f"sources_count={len(collected_sources)}"
    #     )

    async def run_stream_with_sources(
        self,
        db: AsyncSession,
        document_ids: list[int] | None,
        session_id: str,
        question: str,
        history: list,
        redis_client,
        mode: ChatMode = ChatMode.DOC_QA,  # ← 新增参数
    ) -> AsyncGenerator[str | list[SourceRef], None]:
        """
        流式执行 Agent，支持三种模式，同时收集检索来源。

        模式说明：
        - doc_qa：挂载 search_documents 工具（按指定 document_ids 检索），收集来源
        - free_doc_chat：挂载 search_all_documents 工具（全库检索），收集来源
        - free_chat：不挂载检索工具，sources 始终为空列表

        执行流程：
        1. 从 Redis 读取已有摘要，按需压缩历史对话
        2. 按模式选择系统提示词和工具集
        3. 通过 LangGraph astream_events(v2) 流式执行
        4. 过滤 on_chat_model_stream 事件，yield 文字 token
        5. 过滤 on_tool_end 事件，解析 __SOURCES__: 标记收集引用来源
        6. 最后 yield 来源列表作为终止 sentinel（调用方通过 isinstance 判断区分）

        Args:
            db: 数据库会话
            document_ids: 文档 ID 列表（doc_qa 模式使用，其他模式可为 None）
            session_id: 会话 ID
            question: 当前用户问题
            history: 历史消息列表
            redis_client: Redis 客户端（用于读写摘要）
            mode: 聊天模式

        Yields:
            str: 回答 token
            list[SourceRef]: 最后一次 yield 来源列表（终止 sentinel）
        """
        # 1. 摘要压缩（两种模式共用）
        existing_summary = await redis_client.get(f"summary:{session_id}") or ""
        if isinstance(existing_summary, bytes):
            existing_summary = existing_summary.decode()

        summary, recent_history = await summary_memory_manager.compress(
            session_id=session_id,
            history=history,
            existing_summary=existing_summary,
            redis_client=redis_client,
        )

        # 2. 按模式选择系统提示和工具集
        if mode == ChatMode.FREE_CHAT:
            system_prompt = FREE_CHAT_SYSTEM_PROMPT
            tools = [get_current_time, calculator]
        elif mode == ChatMode.FREE_DOC_CHAT:  # ← 新增
            system_prompt = FREE_DOC_CHAT_SYSTEM_PROMPT
            tools = [
                get_search_all_documents_tool(db),  # ← 全库工具
                get_current_time,
                calculator,
            ]
        else:
            system_prompt = SYSTEM_PROMPT
            tools = [
                get_search_documents_tool(document_ids or [], db),
                get_current_time,
                calculator,
            ]

        # 3. 组装消息（系统提示注入到 _build_messages）
        messages = self._build_messages_with_prompt(
            recent_history, question, summary=summary, system_prompt=system_prompt
        )

        llm = self._build_llm()
        agent = create_react_agent(model=llm, tools=tools)

        full_response = []
        collected_sources: list[SourceRef] = []

        try:
            async for event in agent.astream_events(
                {"messages": messages},
                config={"recursion_limit": 10},
                version="v2",
            ):
                event_type = event["event"]

                if (
                    mode in (ChatMode.DOC_QA, ChatMode.FREE_DOC_CHAT)
                    and event_type == "on_tool_end"
                ):
                    tool_output = event.get("data", {}).get("output", "")

                    # 兼容新版本ToolMessage
                    if hasattr(tool_output, "content"):
                        tool_output = tool_output.content  # 取出字符串内容

                    if isinstance(tool_output, str) and "__SOURCES__:" in tool_output:
                        _, sources_json = tool_output.rsplit("__SOURCES__:", 1)
                        try:
                            raw_sources = json.loads(sources_json.strip())
                            for s in raw_sources:
                                source = SourceRef(
                                    document_id=s["document_id"],
                                    chunk_index=s["chunk_index"],
                                    snippet=s["snippet"],
                                    filename=s.get("filename", ""),
                                )
                                if not any(
                                    x.document_id == source.document_id
                                    and x.chunk_index == source.chunk_index
                                    for x in collected_sources
                                ):
                                    collected_sources.append(source)
                        except (json.JSONDecodeError, KeyError):
                            pass

                # 正常 token 输出（两种模式相同）
                if (
                    event_type == "on_chat_model_stream"
                    and event["metadata"].get("langgraph_node") == "agent"
                ):
                    chunk = event["data"]["chunk"]
                    if chunk.content and not chunk.tool_call_chunks:
                        full_response.append(chunk.content)
                        yield chunk.content

        except Exception as e:
            logger.error(f"Agent 执行失败: session={session_id} mode={mode} error={e}")
            yield f"\n\n[错误：{str(e)}]"
            return

        # 最后 yield 来源列表（free_chat 模式始终为空列表）
        yield collected_sources

        logger.info(
            f"Agent 执行完成: session={session_id} mode={mode} "
            f"answer_len={len(''.join(full_response))} "
            f"sources_count={len(collected_sources)}"
        )


agent_runner = AgentRunner()
