import enum

from sqlalchemy import BigInteger, Enum, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base
from src.models.mixins import TimestampMixin


class DocumentStatus(str, enum.Enum):
    """
    文档处理状态（状态机流转）。

    状态流转路径：
        PENDING → PROCESSING → DONE
                            ↘ FAILED（可重试）

    Celery Worker 负责状态推进；API 层仅读取状态，不直接修改。
    """

    PENDING = "pending"  # 待处理（上传完成，等待 Celery 消费）
    PROCESSING = "processing"  # 处理中（Celery Worker 正在解析/切片/向量化）
    DONE = "done"  # 处理完成（可以进行问答检索）
    FAILED = "failed"  # 处理失败（error_msg 字段记录原因，可重新上传）


class Document(TimestampMixin, Base):
    """
    文档元数据表（documents）。

    存储上传文档的基本信息和处理状态。
    文档内容不在此表，切片文本存于 document_chunks，
    向量表示存于 Chroma 的 doc_{id} collection。
    """

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
