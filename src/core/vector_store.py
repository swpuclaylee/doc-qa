import chromadb
from langchain_chroma import Chroma
from langchain_core.documents import Document

from src.core.config import settings
from src.core.embedding import embedding_manager


class VectorStoreManager:
    """
    Chroma 向量数据库管理器

    每个文档对应 Chroma 里的一个 Collection，
    用 document_id 作为 collection 名称做隔离。
    """

    def _get_collection_name(self, document_id: int) -> str:
        """每个文档用独立的 collection 存储"""
        return f"doc_{document_id}"

    def _get_store(self, document_id: int) -> Chroma:
        """获取指定文档的向量存储实例"""
        return Chroma(
            collection_name=self._get_collection_name(document_id),
            embedding_function=embedding_manager.model,
            client=self._get_chroma_client(),
        )

    def _get_chroma_client(self):
        """Chroma HTTP 客户端"""
        return chromadb.HttpClient(
            host=settings.CHROMA_HOST,
            port=settings.CHROMA_PORT,
        )

    async def add_documents(self, document_id: int, docs: list[Document]) -> int:
        """
        将切片后的文档存入向量数据库

        Args:
            document_id: 文档 ID，用于隔离不同文档的向量
            docs: LangChain Document 列表，每个是一个切片

        Returns:
            存入的切片数量
        """
        store = self._get_store(document_id)
        store.add_documents(docs)
        return len(docs)

    async def similarity_search(
        self, document_id: int, query: str, k: int = 4
    ) -> list[Document]:
        """
        相似度检索

        Args:
            document_id: 在哪个文档里检索
            query: 用户问题
            k: 返回最相似的 k 个切片

        Returns:
            最相似的 Document 列表
        """
        store = self._get_store(document_id)
        return store.similarity_search(query, k=k)

    async def delete_collection(self, document_id: int) -> None:
        """删除文档对应的向量集合（文档删除时调用）"""
        client = self._get_chroma_client()
        client.delete_collection(self._get_collection_name(document_id))

    async def get_all_chunks(self, document_id: int) -> list[str]:
        """取出文档在 Chroma 里的所有切片文本"""
        store = self._get_store(document_id)
        result = store.get(include=["documents"])
        return result["documents"] or []


# 全局实例
vector_store_manager = VectorStoreManager()
