from sqlalchemy import Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base
from src.models.mixins import TimestampMixin


class LLMTrace(TimestampMixin, Base):
    """LLM 调用链路日志表"""

    __tablename__ = "llm_traces"

    session_id: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True, comment="会话 ID"
    )
    document_id: Mapped[int] = mapped_column(
        Integer, nullable=False, index=True, comment="文档 ID"
    )
    question: Mapped[str] = mapped_column(Text, nullable=False, comment="用户问题")
    retrieved_chunks: Mapped[str] = mapped_column(
        Text, nullable=True, comment="检索到的切片内容（JSON）"
    )
    prompt: Mapped[str] = mapped_column(
        Text, nullable=True, comment="发送给 LLM 的完整 Prompt"
    )
    answer: Mapped[str] = mapped_column(Text, nullable=True, comment="LLM 回答")
    prompt_tokens: Mapped[int] = mapped_column(
        Integer, nullable=True, comment="输入 token 数"
    )
    completion_tokens: Mapped[int] = mapped_column(
        Integer, nullable=True, comment="输出 token 数"
    )
    latency_ms: Mapped[float] = mapped_column(Float, nullable=True, comment="耗时（毫秒）")
    model_name: Mapped[str] = mapped_column(String(64), nullable=True, comment="模型名称")
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="success", comment="状态 success/failed"
    )
    error_msg: Mapped[str] = mapped_column(Text, nullable=True, comment="错误信息")
