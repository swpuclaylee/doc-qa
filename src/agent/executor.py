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
    get_search_documents_tool,
)
from src.core.config import settings
from src.core.summary_memory import summary_memory_manager
from src.models.conversation import MessageRole
from src.schemas.chat import SourceRef

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


class AgentRunner:
    def _build_llm(self) -> ChatOpenAI:
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

    def _build_messages(
        self,
        history: list,
        question: str,
        summary: str = "",  # 新增参数
    ) -> list:
        messages = [SystemMessage(content=SYSTEM_PROMPT)]

        # 若有摘要，以 HumanMessage 形式插入（模拟对话上下文的前情提要）
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

    async def run_stream(
        self,
        db: AsyncSession,
        document_ids: list[int],
        session_id: str,
        question: str,
        history: list,
        redis_client,
    ) -> AsyncGenerator[str, None]:
        """
        流式执行 Agent（LangGraph ReAct 实现）

        执行过程：
        1. LLM 收到消息，判断是否需要调用工具
        2. 如需要，调用工具获取结果（不 yield）
        3. 将工具结果拼入上下文，生成最终回答（逐 token yield）

        事件过滤逻辑：
        - langgraph_node == "agent"：LLM 推理节点产生的事件
        - not chunk.tool_call_chunks：排除工具调用决策片段，只取文字回答
        """
        # 1. 读取已有摘要
        existing_summary = await redis_client.get(f"summary:{session_id}") or ""
        if isinstance(existing_summary, bytes):
            existing_summary = existing_summary.decode()

        # 2. 判断是否需要压缩
        summary, recent_history = await summary_memory_manager.compress(
            session_id=session_id,
            history=history,
            existing_summary=existing_summary,
            redis_client=redis_client,
        )

        # 3. 组装消息（传入摘要 + 近期历史）
        messages = self._build_messages(recent_history, question, summary=summary)

        tools = [
            get_search_documents_tool(document_ids, db),
            get_current_time,
            calculator,
        ]

        llm = self._build_llm()

        # create_react_agent 是 LangChain 1.x 的推荐替代方案
        # 取代了已移除的 AgentExecutor + create_tool_calling_agent
        agent = create_react_agent(model=llm, tools=tools)

        full_response = []

        try:
            async for event in agent.astream_events(
                {"messages": messages},
                # recursion_limit=10 约等于旧版 max_iterations=5
                # LangGraph 每轮工具调用占 2 步（LLM决策 + 工具执行）
                config={"recursion_limit": 10},
                version="v2",
            ):
                if (
                    event["event"] == "on_chat_model_stream"
                    and event["metadata"].get("langgraph_node") == "agent"
                ):
                    chunk = event["data"]["chunk"]
                    # tool_call_chunks 非空 → LLM 正在生成工具调用参数，跳过
                    # content 非空且无 tool_call_chunks → 最终文字回答，yield
                    if chunk.content and not chunk.tool_call_chunks:
                        full_response.append(chunk.content)
                        yield chunk.content

        except Exception as e:
            logger.error(f"Agent 执行失败: session={session_id} error={e}")
            yield f"\n\n[错误：{str(e)}]"
            return

        logger.info(
            f"Agent 执行完成: session={session_id} "
            f"answer_len={len(''.join(full_response))}"
        )

    async def run_stream_with_sources(
        self,
        db: AsyncSession,
        document_ids: list[int],
        session_id: str,
        question: str,
        history: list,
        redis_client,
    ) -> AsyncGenerator[str | list[SourceRef], None]:
        """
        流式执行 Agent，同时收集检索来源。

        Yields:
            str：正常回答 token
            list[SourceRef]：最后 yield 一次来源列表（用 sentinel 区分）
        """
        # 1. 摘要压缩（不变）
        existing_summary = await redis_client.get(f"summary:{session_id}") or ""
        if isinstance(existing_summary, bytes):
            existing_summary = existing_summary.decode()

        summary, recent_history = await summary_memory_manager.compress(
            session_id=session_id,
            history=history,
            existing_summary=existing_summary,
            redis_client=redis_client,
        )

        # 2. 组装消息（不变）
        messages = self._build_messages(recent_history, question, summary=summary)

        tools = [
            get_search_documents_tool(document_ids, db),
            get_current_time,
            calculator,
        ]

        llm = self._build_llm()
        agent = create_react_agent(model=llm, tools=tools)

        full_response = []
        collected_sources: list[SourceRef] = []  # ← 新增：收集来源

        try:
            async for event in agent.astream_events(
                {"messages": messages},
                config={"recursion_limit": 10},
                version="v2",
            ):
                event_type = event["event"]

                # 收集工具执行结果，提取来源
                if event_type == "on_tool_end":
                    tool_output = event.get("data", {}).get("output", "")
                    if isinstance(tool_output, str) and "__SOURCES__:" in tool_output:
                        _, sources_json = tool_output.rsplit("__SOURCES__:", 1)
                        try:
                            raw_sources = json.loads(sources_json.strip())
                            for s in raw_sources:
                                source = SourceRef(
                                    document_id=s["document_id"],
                                    chunk_index=s["chunk_index"],
                                    snippet=s["snippet"],
                                )
                                # 去重：同一文档同一片段只保留一次
                                if not any(
                                    x.document_id == source.document_id
                                    and x.chunk_index == source.chunk_index
                                    for x in collected_sources
                                ):
                                    collected_sources.append(source)
                        except (json.JSONDecodeError, KeyError):
                            pass  # 解析失败静默忽略

                # 正常 token 输出（与之前相同）
                if (
                    event_type == "on_chat_model_stream"
                    and event["metadata"].get("langgraph_node") == "agent"
                ):
                    chunk = event["data"]["chunk"]
                    if chunk.content and not chunk.tool_call_chunks:
                        full_response.append(chunk.content)
                        yield chunk.content

        except Exception as e:
            logger.error(f"Agent 执行失败: session={session_id} error={e}")
            yield f"\n\n[错误：{str(e)}]"
            return

        # 最后 yield 来源列表（调用方通过类型判断区分）
        yield collected_sources

        logger.info(
            f"Agent 执行完成: session={session_id} "
            f"answer_len={len(''.join(full_response))} "
            f"sources_count={len(collected_sources)}"
        )


agent_runner = AgentRunner()
