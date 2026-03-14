from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_db
from src.core.rate_limit.decorators import rate_limit
from src.schemas.base import PaginatedResponse, ResponseModel
from src.schemas.document import DocumentOut
from src.service.document import document_service

router = APIRouter(prefix="/documents", tags=["文档管理"])

# 文件大小限制：50MB
MAX_FILE_SIZE = 50 * 1024 * 1024

# 允许的 MIME 类型
ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/plain",
}


@router.post(
    "/upload",
    response_model=ResponseModel[DocumentOut],
    status_code=status.HTTP_201_CREATED,
    summary="上传文档",
)
@rate_limit(limit=20, window=60, algorithm="fixed", target="ip")
async def upload_document(
    request: Request,
    file: UploadFile = File(..., description="支持 PDF、Word、TXT"),
    db: AsyncSession = Depends(get_db),
):
    """
    上传文档接口。

    校验文件类型（PDF/Word/TXT）和大小（最大50MB），
    然后调用 DocumentService.upload() 创建 DB 记录并异步触发 Celery 处理任务。
    文档处理是异步的，上传成功后状态为 pending，前端需轮询状态接口。
    """
    # 校验文件类型
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"不支持的文件类型: {file.content_type}，支持 PDF、Word、TXT",
        )

    # 读取文件内容
    file_bytes = await file.read()

    # 校验文件大小
    if len(file_bytes) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="文件过大，最大支持 50MB",
        )

    try:
        doc = await document_service.upload(
            db=db,
            filename=file.filename,
            content_type=file.content_type,
            file_bytes=file_bytes,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)
        ) from e

    return ResponseModel(data=doc, message="文档上传成功")


@router.get(
    "",
    response_model=ResponseModel[PaginatedResponse[DocumentOut]],
    summary="文档列表",
)
async def list_documents(
    page: int = 1,
    page_size: int = 20,
    db: AsyncSession = Depends(get_db),
):
    """
    分页查询文档列表。

    Args:
        page: 页码（从1开始）
        page_size: 每页数量

    Returns:
        分页后的文档列表及总数
    """
    skip = (page - 1) * page_size
    docs, total = await document_service.list_documents(db, skip=skip, limit=page_size)

    return ResponseModel(
        data=PaginatedResponse(
            items=docs,
            total=total,
            page=page,
            page_size=page_size,
        )
    )


@router.delete(
    "/{document_id}",
    response_model=ResponseModel,
    summary="删除文档",
)
async def delete_document(
    document_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    删除指定文档。

    同时删除 PostgreSQL 元数据记录和 Chroma 向量数据（若已处理完成）。
    文档不存在时返回 404。
    """
    deleted = await document_service.delete(db, document_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="文档不存在",
        )
    return ResponseModel(message="删除成功")
