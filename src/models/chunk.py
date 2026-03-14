from sqlalchemy import ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base
from src.models.mixins import TimestampMixin


class DocumentChunk(TimestampMixin, Base):
    """
    文档切片表（document_chunks）。

    双存储设计：切片文本同时写入此表（PostgreSQL）和 Chroma 向量库。
    - PostgreSQL：提供 BM25 关键词检索（jieba 分词 + rank_bm25）
    - Chroma：提供向量相似度检索（bge-small-zh-v1.5 embedding）
    两路结果通过 RRF 算法融合，实现混合检索。
    """

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
