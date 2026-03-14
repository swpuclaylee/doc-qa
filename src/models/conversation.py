import enum
from typing import TYPE_CHECKING

from sqlalchemy import Enum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base
from src.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from .document import Document


class MessageRole(str, enum.Enum):
    """消息角色"""

    USER = "user"
    ASSISTANT = "assistant"


class Conversation(TimestampMixin, Base):
    """
    对话历史表（conversations）。

    每条记录对应一次用户消息或助手回复。
    双字段设计：
    - document_id：兼容旧版单文档场景（可空）
    - document_ids：新版多文档场景，存 JSON 数组（首选）
    """

    __tablename__ = "conversations"

    session_id: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True, comment="会话 ID"
    )
    # 历史兼容字段：单文档时代遗留，多文档模式下存第一个 doc_id（可空）
    # 新代码应读取 document_ids 字段，此字段仅作向后兼容保留
    document_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=True,
        comment="关联文档 ID（兼容旧版单文档，新版请用 document_ids）",
    )
    # 多文档支持字段：存储本次对话关联的全部文档 ID 列表（JSONB 数组）
    document_ids: Mapped[list] = mapped_column(  # 新增字段
        JSONB,
        nullable=False,
        server_default="[]",
        comment="关联的多个文档 ID 列表",
    )
    role: Mapped[MessageRole] = mapped_column(
        Enum(MessageRole), nullable=False, comment="消息角色"
    )
    content: Mapped[str] = mapped_column(Text, nullable=False, comment="消息内容")

    # 关联文档
    document: Mapped["Document"] = relationship("Document", lazy="select")
