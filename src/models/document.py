import enum

from sqlalchemy import BigInteger, Enum, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base
from src.models.mixins import TimestampMixin


class DocumentStatus(str, enum.Enum):
    """文档处理状态"""

    PENDING = "pending"  # 待处理
    PROCESSING = "processing"  # 处理中
    DONE = "done"  # 处理完成
    FAILED = "failed"  # 处理失败


class Document(TimestampMixin, Base):
    """文档元数据表"""

    __tablename__ = "documents"

    filename: Mapped[str] = mapped_column(String(255), nullable=False, comment="原始文件名")
    file_type: Mapped[str] = mapped_column(
        String(20), nullable=False, comment="文件类型 pdf/docx/txt"
    )
    file_size: Mapped[int] = mapped_column(
        BigInteger, nullable=False, comment="文件大小（字节）"
    )
    chunk_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", comment="切片数量"
    )
    status: Mapped[DocumentStatus] = mapped_column(
        Enum(DocumentStatus),
        default=DocumentStatus.PENDING,
        nullable=False,
        comment="处理状态",
    )
    error_msg: Mapped[str | None] = mapped_column(Text, nullable=True, comment="失败原因")
