from langchain_huggingface import HuggingFaceEmbeddings

from src.core.config import settings


class EmbeddingManager:
    """Embedding 模型管理器"""

    def __init__(self):
        self._model: HuggingFaceEmbeddings | None = None

    def init(self):
        """
        初始化 Embedding 模型

        首次调用时从磁盘加载模型到内存，后续复用同一个实例。
        在 lifespan 启动阶段调用，避免第一次请求时才加载导致超时。
        """
        if self._model is not None:
            return

        self._model = HuggingFaceEmbeddings(
            model_name=settings.EMBEDDING_MODEL_NAME,
            model_kwargs={"device": "cpu"},
            encode_kwargs={"normalize_embeddings": True},  # 归一化，余弦相似度计算更准确
        )

    @property
    def model(self) -> HuggingFaceEmbeddings:
        if self._model is None:
            raise RuntimeError("Embedding 模型未初始化，请先调用 init()")
        return self._model


# 全局实例
embedding_manager = EmbeddingManager()
