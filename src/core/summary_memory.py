from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI
from loguru import logger

from src.core.config import settings

# 触发压缩的 token 阈值
SUMMARY_TRIGGER_TOKENS = 2000
# 压缩后保留的最近完整消息条数（对数，USER+ASSISTANT 各算1条）
KEEP_RECENT = 6

SUMMARIZE_PROMPT = """请将以下对话历史压缩为一段简洁的摘要（200字以内）。
摘要应保留：用户的核心问题、助手的关键回答结论、重要实体（如文档章节、数据）。
对话历史：
{history}
"""


class SummaryMemoryManager:
    """
    对话摘要记忆管理器。

    当历史消息 token 总量超过 SUMMARY_TRIGGER_TOKENS 阈值时，
    自动将早期消息压缩为摘要存入 Redis（key: summary:{session_id}，TTL 24h），
    只保留最近 KEEP_RECENT 条消息参与后续对话。

    摘要以 Human+AI 对话对形式注入到消息列表开头，作为"前情提要"。
    """

    def _build_llm(self) -> ChatOpenAI:
        """
        构建用于生成摘要的 LLM（temperature=0 保证摘要稳定，非流式）。
        """
        return ChatOpenAI(
            model="deepseek-chat",
            api_key=settings.DEEPSEEK_API_KEY,
            base_url=settings.DEEPSEEK_BASE_URL,
            temperature=0.0,
            streaming=False,  # 摘要生成不需要流式
        )

    def _estimate_tokens(self, text: str) -> int:
        """
        粗略估算文本 token 数。

        规则：中文字符 1字≈1token，英文/其他 4字符≈1token。
        用于判断历史消息是否超出压缩阈值，不要求精确。
        """
        chinese = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
        return chinese + (len(text) - chinese) // 4

    async def compress(
        self,
        session_id: str,
        history: list,  # Conversation ORM 对象列表
        existing_summary: str,  # 上一轮已存储的摘要，可为空字符串
        redis_client,  # aioredis 客户端
    ) -> tuple[str, list]:
        """
        判断是否需要压缩，若需要则：
          1. 把超出预算的早期消息 + existing_summary 合并压缩成新摘要
          2. 写入 Redis
          3. 返回 (新摘要, 保留的近期消息列表)

        Returns:
            (summary_text, recent_messages)
        """
        total_tokens = sum(self._estimate_tokens(m.content) for m in history)
        if total_tokens <= SUMMARY_TRIGGER_TOKENS:
            # 未超限，无需压缩
            return existing_summary, history

        # 保留最近 KEEP_RECENT 条，其余压缩
        to_compress = history[:-KEEP_RECENT] if len(history) > KEEP_RECENT else []
        recent = history[-KEEP_RECENT:]

        if not to_compress:
            return existing_summary, recent

        # 拼接待压缩部分
        lines = []
        if existing_summary:
            lines.append(f"[已有摘要]\n{existing_summary}\n")
        for msg in to_compress:
            role = "用户" if msg.role.value == "user" else "助手"
            lines.append(f"{role}：{msg.content}")
        history_text = "\n".join(lines)

        # 调用 LLM 生成摘要
        llm = self._build_llm()
        prompt = SUMMARIZE_PROMPT.format(history=history_text)
        try:
            result = await llm.ainvoke([HumanMessage(content=prompt)])
            new_summary = result.content.strip()
        except Exception as e:
            logger.error(f"摘要生成失败 session={session_id}: {e}")
            new_summary = existing_summary  # 降级：保留旧摘要

        # 写入 Redis，TTL 24 小时
        key = f"summary:{session_id}"
        await redis_client.set(key, new_summary, ex=86400)
        logger.debug(f"摘要已更新 session={session_id} length={len(new_summary)}")

        return new_summary, recent


summary_memory_manager = SummaryMemoryManager()
