import asyncio

from loguru import logger

from src.core.celery_app import celery_app


@celery_app.task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    name="src.tasks.document.process_document",
)
def process_document(
    self, document_id: int, file_bytes_b64: str, file_type: str
) -> dict:
    """
    异步处理文档：解析 + 切片 + Embedding + 存入向量数据库

    Args:
        document_id: 文档 ID
        file_bytes_b64: base64 编码的文件内容（Celery 任务参数必须可序列化）
        file_type: 文件类型 pdf/docx/txt

    Returns:
        {"status": "done", "chunk_count": N}
    """
    try:
        return asyncio.run(
            _process_document_async(self, document_id, file_bytes_b64, file_type)
        )
    except Exception as exc:
        logger.error(f"文档处理任务失败: document_id={document_id} error={exc}")
        raise self.retry(exc=exc, countdown=60)


async def _process_document_async(
    task, document_id: int, file_bytes_b64: str, file_type: str
) -> dict:
    """异步处理逻辑"""
    import base64

    from src.core.config import settings
    from src.core.embedding import embedding_manager
    from src.db.session import db_manager
    from src.models.document import DocumentStatus
    from src.repository.document import document_repo
    from src.service.document import DocumentService

    # 初始化数据库（Worker 进程里没有 lifespan，需要手动初始化）
    if db_manager.engine is None:
        db_manager.init(
            database_url=settings.DATABASE_URL,
            echo=settings.DB_ECHO,
            pool_size=settings.DB_POOL_SIZE,
            max_overflow=settings.DB_MAX_OVERFLOW,
            pool_recycle=settings.DB_POOL_RECYCLE,
            pool_timeout=settings.DB_POOL_TIMEOUT,
        )

    # 初始化 Embedding 模型
    if embedding_manager._model is None:
        embedding_manager.init()

    # 解码文件内容
    file_bytes = base64.b64decode(file_bytes_b64)

    async with db_manager.get_session() as db:
        # 更新状态为处理中
        await document_repo.update_status(db, document_id, DocumentStatus.PROCESSING)
        logger.info(f"开始处理文档: document_id={document_id} file_type={file_type}")

        try:
            svc = DocumentService()
            chunk_count = await svc._process(document_id, file_type, file_bytes)
            await document_repo.update_status(
                db, document_id, DocumentStatus.DONE, chunk_count=chunk_count
            )
            logger.info(f"文档处理完成: document_id={document_id} chunks={chunk_count}")
            return {"status": "done", "chunk_count": chunk_count}

        except Exception as e:
            await document_repo.update_status(
                db, document_id, DocumentStatus.FAILED, error_msg=str(e)
            )
            logger.error(f"文档处理失败: document_id={document_id} error={e}")
            raise
