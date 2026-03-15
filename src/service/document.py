import base64
import tempfile
from pathlib import Path

from langchain_community.document_loaders import Docx2txtLoader, PyPDFLoader, TextLoader
from langchain_core.documents import Document as LangchainDocument
from langchain_text_splitters import RecursiveCharacterTextSplitter
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.vector_store import vector_store_manager
from src.models.document import DocumentStatus
from src.repository.document import document_repo
from src.schemas.document import DocumentOut
from src.tasks.document import process_document

# 支持的文件类型
SUPPORTED_TYPES = {
    "application/pdf": "pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "text/plain": "txt",
}

# 切片配置
CHUNK_SIZE = 500  # 每个切片最大字符数
CHUNK_OVERLAP = 50  # 相邻切片的重叠字符数，保留上下文连续性


class DocumentService:
    """
    文档业务层，负责文档上传、处理调度、列表查询和删除。

    上传流程：
    1. 校验文件类型
    2. 在 PostgreSQL 创建文档记录（状态: PENDING）
    3. base64 编码文件内容，通过 Celery 异步调度处理任务
    Celery Worker 负责解析、切片、向量化，并更新状态为 DONE/FAILED。
    """

    async def upload(
        self,
        db: AsyncSession,
        filename: str,
        content_type: str,
        file_bytes: bytes,
    ) -> DocumentOut:
        """
        上传并处理文档

        Args:
            db: 数据库会话
            filename: 原始文件名
            content_type: MIME 类型
            file_bytes: 文件内容

        Returns:
            DocumentOut: 文档元数据

        Raises:
            ValueError: 不支持的文件类型
        """
        # 1. 校验文件类型
        file_type = SUPPORTED_TYPES.get(content_type)
        if not file_type:
            raise ValueError(f"不支持的文件类型: {content_type}，支持 PDF、Word、TXT")

        # 2. 创建文档记录（状态: PENDING）
        doc = await document_repo.create(
            db,
            {
                "filename": filename,
                "file_type": file_type,
                "file_size": len(file_bytes),
                "status": DocumentStatus.PENDING,
            },
        )

        # 发送 Celery 任务（file_bytes 需要 base64 编码才能序列化）
        """
        Celery 任务参数通过 Redis 传递，必须是 JSON 可序列化的。
        bytes 类型不能直接序列化，所以要先 base64 编码成字符串，Worker 收到后再解码回 bytes。
        """
        file_bytes_b64 = base64.b64encode(file_bytes).decode()
        process_document.delay(doc.id, file_bytes_b64, file_type)

        return DocumentOut.model_validate(doc)

    async def _process(
        self, document_id: int, file_type: str, file_bytes: bytes
    ) -> int:
        """
        解析文档、切片、存入向量数据库

        Returns:
            切片数量
        """
        # delete=False 避免 Windows 上文件被占用时删除报错，手动清理
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(
                suffix=f".{file_type}", delete=False
            ) as tmp:
                tmp.write(file_bytes)
                tmp_path = tmp.name
            chunks = self._load_and_split(tmp_path, file_type)
        finally:
            if tmp_path:
                Path(tmp_path).unlink(missing_ok=True)

        # 存入向量数据库
        await vector_store_manager.add_documents(document_id, chunks)
        return len(chunks)

    def _load_and_split(
        self, file_path: str, file_type: str
    ) -> list[LangchainDocument]:
        """
        加载文档并切片

        不同文件类型用不同的 Loader 解析，
        统一用 RecursiveCharacterTextSplitter 切片。
        """
        # 根据文件类型选择 Loader
        if file_type == "pdf":
            loader = PyPDFLoader(file_path)
        elif file_type == "docx":
            loader = Docx2txtLoader(file_path)
        elif file_type == "txt":
            loader = TextLoader(file_path, encoding="utf-8")
        else:
            raise ValueError(f"未知文件类型: {file_type}")

        docs = loader.load()

        # 切片
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=CHUNK_SIZE,
            chunk_overlap=CHUNK_OVERLAP,
            separators=["\n\n", "\n", "。", "！", "？", ".", "!", "?", " ", ""],
        )
        return splitter.split_documents(docs)

    async def list_documents(
        self, db: AsyncSession, skip: int = 0, limit: int = 20
    ) -> tuple[list[DocumentOut], int]:
        """
        查询文档列表（分页）。

        Returns:
            tuple[list[DocumentOut], int]: (文档列表, 总数)
        """
        docs, total = await document_repo.get_multi(db, skip=skip, limit=limit)
        return [DocumentOut.model_validate(d) for d in docs], total

    async def delete(self, db: AsyncSession, document_id: int) -> bool:
        """
        删除文档

        同时删除：PostgreSQL 元数据 + Chroma 向量数据
        """
        doc = await document_repo.get(db, document_id)
        if not doc:
            return False

        # 只有处理成功的文档才有向量数据需要删除
        if doc.status == DocumentStatus.DONE:
            try:
                await vector_store_manager.delete_collection(document_id)
            except Exception as e:
                logger.warning(f"删除向量数据失败（忽略）: id={document_id} error={e}")

        # 再删元数据（级联删除关联的 conversations）
        await document_repo.delete(db, document_id)

        logger.info(f"文档已删除: id={document_id}")
        return True


document_service = DocumentService()
