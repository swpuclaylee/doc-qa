from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from src.models.conversation import MessageRole


class ChatRequest(BaseModel):
    """问答请求"""

    document_id: int = Field(..., description="文档 ID")
    session_id: str = Field(..., description="会话 ID，同一会话保持一致")
    question: str = Field(..., min_length=1, max_length=2000, description="用户问题")


class ConversationOut(BaseModel):
    """单条对话记录"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    session_id: str
    document_id: int
    role: MessageRole
    content: str
    created_at: datetime


class ChatHistoryOut(BaseModel):
    """对话历史列表"""

    session_id: str
    document_id: int
    messages: list[ConversationOut]
