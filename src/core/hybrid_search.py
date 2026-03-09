import asyncio

import jieba
from langchain_core.documents import Document
from rank_bm25 import BM25Okapi
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.reranker import reranker
from src.core.vector_store import vector_store_manager
from src.repository.chunk import chunk_repo

# RRF 算法参数，常用值为 60，越大越平滑
RRF_K = 60


class HybridSearcher:
    """
    混合检索器

    结合向量检索（语义）和 BM25 检索（关键词），
    用 RRF 算法融合两个排名列表，取 Top-K 返回。
    """

    async def search(
        self,
        db: AsyncSession,
        document_id: int,
        query: str,
        k: int = 4,
        fetch_k: int = 20,
    ) -> list[Document]:
        """
        混合检索

        Args:
            db: 数据库会话
            document_id: 文档 ID
            query: 用户问题
            k: 最终返回的切片数
            fetch_k: 每路检索的候选数量

        Returns:
            融合精排序后的 Top-K Document 列表
        """
        # 1. 向量检索
        vector_results = await vector_store_manager.similarity_search(
            document_id=document_id,
            query=query,
            k=fetch_k,
        )

        # 2. BM25 检索
        bm25_results = await self._bm25_search(db, document_id, query, k=fetch_k)

        # 3. RRF 融合，得到 Top-20 候选
        candidates = self._rrf_fusion(vector_results, bm25_results, k=fetch_k)

        # 4. Rerank 精排，从 Top-20 里取 Top-K
        if candidates:
            texts = [doc.page_content for doc in candidates]
            top_indices = reranker.rerank(query, texts, top_k=k)
            return [candidates[i] for i in top_indices]

        return candidates[:k]

    async def search_multi(
        self,
        db: AsyncSession,
        document_ids: list[int],
        query: str,
        k: int = 6,
        fetch_k: int = 20,
    ) -> list[Document]:
        """
        多文档联合检索

        对每个文档并发执行 search()，合并结果后再做一轮 RRF 融合，
        最后 Rerank 取 Top-K。

        Args:
            db: 数据库会话
            document_ids: 文档 ID 列表
            query: 用户问题
            k: 最终返回的切片总数
            fetch_k: 每个文档的检索候选数

        Returns:
            跨文档融合排序后的 Top-K Document 列表，
            每条 Document.metadata 含 document_id 字段
        """
        if not document_ids:
            return []

        # 1. 并发对每个文档执行 search()
        tasks = [
            self.search(
                db=db, document_id=doc_id, query=query, k=fetch_k, fetch_k=fetch_k
            )
            for doc_id in document_ids
        ]
        all_results: list[list[Document]] = await asyncio.gather(*tasks)

        # 2. 为每条结果注入 document_id 元数据
        tagged_results: list[list[Document]] = []
        for doc_id, results in zip(document_ids, all_results, strict=False):
            tagged = []
            for doc in results:
                new_meta = dict(doc.metadata)
                new_meta["document_id"] = doc_id
                tagged.append(
                    Document(page_content=doc.page_content, metadata=new_meta)
                )
            tagged_results.append(tagged)

        # 3. 跨文档 RRF 融合（把所有文档的结果当作多路输入）
        #    每个文档的检索结果作为独立的一路
        if len(tagged_results) == 1:
            candidates = tagged_results[0][:fetch_k]
        else:
            # 利用现有 _rrf_fusion 做两两融合
            # 对于 3 个以上文档，逐步累积融合
            candidates = tagged_results[0]
            for i in range(1, len(tagged_results)):
                candidates = self._rrf_fusion(candidates, tagged_results[i], k=fetch_k)

        # 4. Rerank 精排
        if candidates:
            texts = [doc.page_content for doc in candidates]
            top_indices = reranker.rerank(query, texts, top_k=k)
            return [candidates[i] for i in top_indices]

        return candidates[:k]

    async def _bm25_search(
        self,
        db: AsyncSession,
        document_id: int,
        query: str,
        k: int,
    ) -> list[Document]:
        """
        BM25 关键词检索

        从 PostgreSQL 取出文档所有切片，构建 BM25 索引，检索后返回。
        """

        # 从数据库取切片
        chunks = await chunk_repo.get_by_document(db, document_id)
        if not chunks:
            return []

        # 中文分词（简单按字符切分，生产环境可换 jieba）
        corpus = [list(jieba.cut(c.content)) for c in chunks]
        tokenized_query = list(jieba.cut(query))

        # 构建 BM25 索引并检索
        bm25 = BM25Okapi(corpus)
        scores = bm25.get_scores(tokenized_query)

        # 取 Top-K
        top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[
            :k
        ]

        return [
            Document(
                page_content=chunks[i].content,
                metadata={"chunk_index": chunks[i].chunk_index, "source": "bm25"},
            )
            for i in top_indices
            if scores[i] > 0  # 过滤掉完全不相关的结果
        ]

    def _rrf_fusion(
        self,
        vector_results: list[Document],
        bm25_results: list[Document],
        k: int,
    ) -> list[Document]:
        """
        RRF（倒数排名融合）算法

        公式：score(d) = Σ 1 / (RRF_K + rank(d))
        rank 从 1 开始，排名越靠前分数越高。
        """
        scores: dict[str, float] = {}
        doc_map: dict[str, Document] = {}

        def _add_results(results: list[Document], weight: float = 1.0):
            for rank, doc in enumerate(results, start=1):
                # 用文本内容作为唯一标识（去重）
                key = doc.page_content[:100]
                rrf_score = weight / (RRF_K + rank)
                scores[key] = scores.get(key, 0) + rrf_score
                if key not in doc_map:
                    doc_map[key] = doc

        # 两路结果权重相同
        _add_results(vector_results, weight=1.0)
        _add_results(bm25_results, weight=1.0)

        # 按 RRF 分数降序排列，取 Top-K
        sorted_keys = sorted(scores, key=lambda x: scores[x], reverse=True)[:k]
        return [doc_map[key] for key in sorted_keys]


hybrid_searcher = HybridSearcher()
