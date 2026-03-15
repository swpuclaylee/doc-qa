import asyncio

from celery.signals import worker_process_init, worker_process_shutdown
from loguru import logger

from src.core.celery_app import celery_app

# ── Worker 进程级别资源 ──────────────────────────────────────
# 每个 Worker 进程持有一个事件循环，所有任务共用，避免 AsyncEngine 跨循环失效

_loop: asyncio.AbstractEventLoop | None = None


@worker_process_init.connect
def init_worker(**kwargs):
    """
    Worker 进程启动时初始化：
    1. 创建持久事件循环（绑定到进程，不随任务结束而关闭）
    2. 初始化 AsyncEngine（绑定到上面的循环）
    3. 初始化 Embedding 模型、Reranker（CPU 密集，只加载一次）
    """
    global _loop

    from src.core.config import settings
    from src.core.embedding import embedding_manager
    # from src.core.reranker import reranker
    from src.db.session import db_manager

    _loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_loop)

    # 初始化数据库引擎（绑定到 _loop）
    db_manager.init(
        database_url=settings.DATABASE_URL,
        echo=settings.DB_ECHO,
        pool_size=settings.DB_POOL_SIZE,
        max_overflow=settings.DB_MAX_OVERFLOW,
        pool_recycle=settings.DB_POOL_RECYCLE,
        pool_timeout=settings.DB_POOL_TIMEOUT,
    )

    # 初始化模型
    embedding_manager.init()
    # reranker.init()

    logger.info("Worker 进程资源初始化完成")


@worker_process_shutdown.connect
def shutdown_worker(**kwargs):
    """
    Worker 进程退出时优雅关闭：
    释放数据库连接池，关闭事件循环
    """
    global _loop

    from src.db.session import db_manager

    if _loop and db_manager.engine:
        _loop.run_until_complete(db_manager.close())
        logger.info("数据库连接池已关闭")

    if _loop and not _loop.is_closed():
        _loop.close()
        logger.info("Worker 事件循环已关闭")


# ── Celery 任务 ───────────────────────────────────────────────


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

    使用 Worker 进程级别的持久事件循环（_loop），
    避免 AsyncEngine 跨循环失效的问题。
    """
    if _loop is None:
        # 防御性检查：理论上不应发生（init_worker 信号会先于任务执行）
        raise RuntimeError("Worker 事件循环未初始化，请检查 worker_process_init 信号")

    try:
        return _loop.run_until_complete(
            _process_document_async(self, document_id, file_bytes_b64, file_type)
        )
    except Exception as exc:
        logger.error(f"文档处理任务失败: document_id={document_id} error={exc}")
        raise self.retry(exc=exc, countdown=60) from exc


async def _process_document_async(
    task, document_id: int, file_bytes_b64: str, file_type: str
) -> dict:
    """
    异步处理逻辑

    所有初始化已在 init_worker 完成，这里只做业务逻辑。
    """
    import base64

    from src.core.vector_store import vector_store_manager
    from src.db.session import db_manager
    from src.models.document import DocumentStatus
    from src.repository.chunk import chunk_repo
    from src.repository.document import document_repo
    from src.service.document import DocumentService

    file_bytes = base64.b64decode(file_bytes_b64)

    async with db_manager.get_session() as db:
        await document_repo.update_status(db, document_id, DocumentStatus.PROCESSING)
        logger.info(f"开始处理文档: document_id={document_id} file_type={file_type}")

        try:
            svc = DocumentService()
            chunk_count = await svc._process(document_id, file_type, file_bytes)

            chunks = await vector_store_manager.get_all_chunks(document_id)
            await chunk_repo.bulk_create(db, document_id, chunks)

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
