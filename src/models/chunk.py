from sqlalchemy import ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base
from src.models.mixins import TimestampMixin


class DocumentChunk(TimestampMixin, Base):
    """文档切片表"""

    __tablename__ = "document_chunks"

    document_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="关联文档 ID",
    )
    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="切片文本内容",
    )
    chunk_index: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="切片序号（从0开始）",
    )
