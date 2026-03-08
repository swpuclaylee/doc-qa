from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_db
from src.core.rate_limit.decorators import rate_limit
from src.schemas.base import ResponseModel
from src.schemas.chat import ChatHistoryOut, ChatRequest
from src.service.chat import chat_service

router = APIRouter(prefix="/chat", tags=["问答"])


@router.post(
    "",
    summary="流式问答（SSE）",
    response_description="text/event-stream 流式返回回答内容",
)
@rate_limit(limit=20, window=60, algorithm="sliding", target="ip")
async def chat(
    request: Request,
    req: ChatRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    对指定文档进行问答，以 SSE 流式返回回答。

    前端接收方式：
        const es = new EventSource('/api/v1/chat');
        // 或用 fetch + ReadableStream 处理 POST 请求
    """

    async def event_stream():
        async for token in chat_service.chat_stream(
            db=db,
            document_id=req.document_id,
            session_id=req.session_id,
            question=req.question,
        ):
            # SSE 格式：每条消息以 "data: " 开头，以 "\n\n" 结尾
            yield f"data: {token}\n\n"

        # 发送结束标志
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # 禁用 Nginx 缓冲，确保实时推送
        },
    )


@router.get(
    "/{session_id}",
    response_model=ResponseModel[ChatHistoryOut],
    summary="获取对话历史",
)
async def get_history(
    session_id: str,
    document_id: int,
    db: AsyncSession = Depends(get_db),
):
    history = await chat_service.get_history(db, session_id, document_id)
    return ResponseModel(data=history)


@router.delete(
    "/{session_id}",
    response_model=ResponseModel,
    summary="清空对话历史",
)
async def clear_history(
    session_id: str,
    db: AsyncSession = Depends(get_db),
):
    count = await chat_service.clear_history(db, session_id)
    return ResponseModel(message=f"已清空 {count} 条对话记录")
