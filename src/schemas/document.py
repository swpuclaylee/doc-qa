from datetime import datetime

from pydantic import BaseModel, ConfigDict

from src.models.document import DocumentStatus


class DocumentBase(BaseModel):
    """
    文档基础字段（上传时的原始属性）。
    作为 DocumentCreate 和 DocumentOut 的公共基类。
    """

    filename: str
    file_type: str
    file_size: int


class DocumentCreate(DocumentBase):
    """创建文档（内部使用，由 service 层构建）"""

    pass


class DocumentUpdate(BaseModel):
    """更新文档状态（内部使用）"""

    status: DocumentStatus | None = None
    chunk_count: int | None = None
    error_msg: str | None = None


class DocumentOut(DocumentBase):
    """返回给前端的文档信息"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    chunk_count: int
    status: DocumentStatus
    error_msg: str | None
    created_at: datetime
    updated_at: datetime
