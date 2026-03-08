from loguru import logger


class Reranker:
    """
    Rerank 重排序器

    使用 bge-reranker-base 对候选切片重新打分，
    比向量相似度更精准地评估切片和问题的相关性。
    """

    def __init__(self):
        self._model = None

    def init(self):
        """
        初始化 Rerank 模型

        在 lifespan 启动阶段调用，预加载模型到内存。
        """
        if self._model is not None:
            return

        from sentence_transformers import CrossEncoder

        self._model = CrossEncoder(
            "BAAI/bge-reranker-base",
            max_length=512,
        )
        logger.info("Rerank 模型已加载")

    @property
    def model(self):
        if self._model is None:
            raise RuntimeError("Rerank 模型未初始化，请先调用 init()")
        return self._model

    def rerank(self, query: str, documents: list[str], top_k: int) -> list[int]:
        """
        对候选文档重新打分排序

        Args:
            query: 用户问题
            documents: 候选切片文本列表
            top_k: 返回前 top_k 个的索引

        Returns:
            排序后的索引列表（按相关性从高到低）
        """
        if not documents:
            return []

        # CrossEncoder 输入格式：(query, document) 对
        pairs = [(query, doc) for doc in documents]
        scores = self.model.predict(pairs)

        # 按分数降序排列，取 Top-K 的索引
        sorted_indices = sorted(
            range(len(scores)),
            key=lambda i: scores[i],
            reverse=True,
        )[:top_k]

        return sorted_indices


# 全局实例
reranker = Reranker()
