import enum
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.models.conversation import MessageRole


class ChatMode(str, enum.Enum):
    """
    聊天模式枚举。

    - DOC_QA：文档问答，需要指定 document_ids，使用 search_documents 工具
    - FREE_CHAT：自由聊天，不使用检索工具，只有 calculator 和 get_current_time
    - FREE_DOC_CHAT：文档自由问答，自动检索全库所有文档，无需指定 document_ids
    """

    DOC_QA = "doc_qa"  # 文档问答（默认）
    FREE_CHAT = "free_chat"  # 自由聊天
    FREE_DOC_CHAT = "free_doc_chat"  # 文档自由聊天


class ChatRequest(BaseModel):
    """问答请求"""

    mode: ChatMode = Field(
        default=ChatMode.DOC_QA,
        description="聊天模式：doc_qa（文档问答）或 free_chat（自由聊天）",
    )
    document_ids: list[int] | None = Field(
        default=None,
        min_length=1,
        max_length=10,
        description="文档 ID 列表（doc_qa 模式必填，free_chat 模式忽略）",
    )
    session_id: str = Field(..., description="会话 ID，同一会话保持一致")
    question: str = Field(..., min_length=1, max_length=2000, description="用户问题")

    @model_validator(mode="after")
    def validate_document_ids_for_doc_qa(self) -> "ChatRequest":
        """文档问答模式下必须提供 document_ids"""
        if self.mode == ChatMode.DOC_QA and not self.document_ids:
            raise ValueError("doc_qa 模式下 document_ids 不能为空")
        return self


# class ChatRequest(BaseModel):
#     document_ids: list[int] = Field(
#         ...,
#         min_length=1,
#         max_length=10,
#         description="文档 ID 列表（1-10个）",
#     )
#     session_id: str = Field(..., description="会话 ID，同一会话保持一致")
#     question: str = Field(..., min_length=1, max_length=2000, description="用户问题")


class ConversationOut(BaseModel):
    """
    单条对话记录的响应模型（对应 Conversation ORM 对象）。
    用于历史记录列表的序列化输出。
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    session_id: str
    document_id: int
    role: MessageRole
    content: str
    created_at: datetime


class ChatHistoryOut(BaseModel):
    """
    对话历史列表响应模型。
    包含会话 ID、关联文档 ID 列表，以及有序的消息列表。
    """

    session_id: str
    document_ids: list[int]
    messages: list[ConversationOut]


class SourceRef(BaseModel):
    """
    单条答案引用来源，由 AgentRunner 从工具输出中解析 __SOURCES__: 标记得到。
    最终通过 SSE event: sources 事件发送给前端展示引用卡片。
    """

    document_id: int = Field(..., description="来源文档 ID")
    chunk_index: int = Field(..., description="片段序号（从0开始）")
    snippet: str = Field(..., description="片段内容前150字（用于展示）")
    filename: str = Field(default="", description="来源文档文件名")
