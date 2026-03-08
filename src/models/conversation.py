import enum

from sqlalchemy import Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base
from src.models.mixins import TimestampMixin


class MessageRole(str, enum.Enum):
    """消息角色"""

    USER = "user"
    ASSISTANT = "assistant"


class Conversation(TimestampMixin, Base):
    """对话历史表"""

    __tablename__ = "conversations"

    session_id: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True, comment="会话 ID"
    )
    document_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        comment="关联文档 ID",
    )
    role: Mapped[MessageRole] = mapped_column(
        Enum(MessageRole), nullable=False, comment="消息角色"
    )
    content: Mapped[str] = mapped_column(Text, nullable=False, comment="消息内容")

    # 关联文档
    document: Mapped["Document"] = relationship("Document", lazy="select")
