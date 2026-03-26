"""混合检索层：向量检索 + BM25 + 重排序 + 父文档检索。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import structlog

from server.config import ServerConfig
from server.models.schemas import Chunk, ChunkMetadata, IntentType

if TYPE_CHECKING:
    from elasticsearch import AsyncElasticsearch
    from FlagEmbedding import BGEM3FlagModel, FlagReranker
    from pymilvus import Collection

logger = structlog.get_logger()


@dataclass
class RetrievalResult:
    """检索结果，包含最终 chunk、父 chunk 和重排序分数。"""

    chunks: list[Chunk]
    parent_chunks: list[Chunk]
    scores: list[float]


class HybridRetriever:
    """混合检索器：结合向量检索与 BM25，经重排序后返回结果。

    各外部依赖（嵌入模型、重排序器、ES、Milvus）均采用懒初始化，
    避免在构建时即加载大型模型或建立网络连接。
    """

    def __init__(self, config: ServerConfig) -> None:
        self.config = config
        self._embed_model: BGEM3FlagModel | None = None
        self._reranker: FlagReranker | None = None
        self._es: AsyncElasticsearch | None = None
        self._collection: Collection | None = None

    # ------------------------------------------------------------------
    # 运行时延迟导入辅助
    # ------------------------------------------------------------------

    @staticmethod
    def _import_flag_embedding() -> tuple[type, type]:
        """延迟导入 FlagEmbedding，避免模块加载时触发重量级依赖。"""
        from FlagEmbedding import BGEM3FlagModel, FlagReranker

        return BGEM3FlagModel, FlagReranker

    @staticmethod
    def _import_milvus() -> tuple[type, Any]:
        """延迟导入 pymilvus。"""
        from pymilvus import Collection, connections

        return Collection, connections

    @staticmethod
    def _import_es() -> type:
        """延迟导入 elasticsearch。"""
        from elasticsearch import AsyncElasticsearch

        return AsyncElasticsearch

    # ------------------------------------------------------------------
    # 懒初始化属性
    # ------------------------------------------------------------------

    @property
    def embed_model(self) -> BGEM3FlagModel:
        """懒加载 BGE-M3 嵌入模型。"""
        if self._embed_model is None:
            bgem3_cls, _ = self._import_flag_embedding()
            self._embed_model = bgem3_cls("BAAI/bge-m3", use_fp16=True)
        return self._embed_model

    @property
    def reranker(self) -> FlagReranker:
        """懒加载 BGE-Reranker-v2-m3 重排序器。"""
        if self._reranker is None:
            _, reranker_cls = self._import_flag_embedding()
            self._reranker = reranker_cls(
                "BAAI/bge-reranker-v2-m3", use_fp16=True
            )
        return self._reranker

    async def _get_es(self) -> AsyncElasticsearch:
        """获取或创建 ES 异步客户端。"""
        if self._es is None:
            es_cls = self._import_es()
            self._es = es_cls(self.config.es_url)
        return self._es

    def _get_collection(self) -> Collection:
        """获取或创建 Milvus Collection（同时建立连接并加载数据）。"""
        if self._collection is None:
            collection_cls, milvus_connections = self._import_milvus()
            milvus_connections.connect(
                host=self.config.milvus_host,
                port=self.config.milvus_port,
            )
            self._collection = collection_cls(self.config.milvus_collection)
            self._collection.load()
        return self._collection

    # ------------------------------------------------------------------
    # 检索子步骤
    # ------------------------------------------------------------------

    async def _vector_search(
        self, query: str, top_k: int, filters: dict
    ) -> list[dict]:
        """使用 BGE-M3 编码查询，在 Milvus 中进行向量近似搜索。"""
        embedding = self.embed_model.encode(
            [query], return_dense=True
        )["dense_vecs"][0].tolist()
        collection = self._get_collection()

        # 构造 Milvus 布尔过滤表达式
        expr_parts: list[str] = []
        if "source" in filters:
            expr_parts.append(f'source == "{filters["source"]}"')
        if "element_type" in filters:
            expr_parts.append(f'element_type == "{filters["element_type"]}"')
        expr = " and ".join(expr_parts) if expr_parts else None

        results = collection.search(
            data=[embedding],
            anns_field="embedding",
            param={"metric_type": "COSINE", "params": {"ef": 128}},
            limit=top_k,
            expr=expr,
            output_fields=["chunk_id", "source", "element_type"],
        )

        return [
            {
                "chunk_id": hit.entity.get("chunk_id"),
                "source": hit.entity.get("source"),
                "score": hit.score,
            }
            for hit in results[0]
        ]

    async def _bm25_search(
        self, query: str, top_k: int, filters: dict
    ) -> list[dict]:
        """在 Elasticsearch 中使用 multi_match 进行 BM25 全文检索。"""
        es = await self._get_es()

        must_clauses = [
            {
                "multi_match": {
                    "query": query,
                    "fields": ["content", "embedding_text"],
                }
            }
        ]
        filter_clauses: list[dict] = []
        if "source" in filters:
            filter_clauses.append({"term": {"source": filters["source"]}})
        if "element_type" in filters:
            filter_clauses.append(
                {"term": {"element_type": filters["element_type"]}}
            )

        body = {
            "query": {
                "bool": {"must": must_clauses, "filter": filter_clauses}
            },
            "size": top_k,
        }
        resp = await es.search(index=self.config.es_index, body=body)

        return [
            {
                "chunk_id": hit["_id"],
                "source": hit["_source"].get("source", ""),
                "score": hit["_score"],
            }
            for hit in resp["hits"]["hits"]
        ]

    # ------------------------------------------------------------------
    # 合并、聚合、重排序
    # ------------------------------------------------------------------

    def _merge_results(
        self,
        vec_results: list[dict],
        bm25_results: list[dict],
        intent: IntentType = IntentType.REASONING,
    ) -> list[dict]:
        """合并向量检索和 BM25 结果并去重。

        当 intent 为 EXACT 时，优先保留 BM25 结果（精确匹配场景）；
        否则优先保留向量检索结果（语义理解场景）。
        """
        seen: set[str] = set()
        merged: list[dict] = []

        if intent == IntentType.EXACT:
            primary, secondary = bm25_results, vec_results
        else:
            primary, secondary = vec_results, bm25_results

        for result in primary:
            cid = result["chunk_id"]
            if cid not in seen:
                seen.add(cid)
                merged.append(result)

        for result in secondary:
            cid = result["chunk_id"]
            if cid not in seen:
                seen.add(cid)
                merged.append(result)

        return merged

    def _cross_doc_aggregate(
        self, results: list[dict], max_per_source: int = 3
    ) -> list[dict]:
        """跨文档聚合：限制每个来源文档的最大 chunk 数量，确保结果多样性。"""
        source_counts: dict[str, int] = {}
        aggregated: list[dict] = []

        for result in results:
            src = result.get("source", "")
            count = source_counts.get(src, 0)
            if count < max_per_source:
                aggregated.append(result)
                source_counts[src] = count + 1

        return aggregated

    def _rerank(
        self, query: str, chunks: list[Chunk], top_n: int
    ) -> list[tuple[Chunk, float]]:
        """使用 FlagReranker 对候选 chunk 进行重排序，返回 top_n 结果。"""
        if not chunks:
            return []

        pairs = [(query, c.embedding_text or c.content) for c in chunks]
        scores = self.reranker.compute_score(pairs)
        # compute_score 在单条输入时返回 float 而非 list
        if isinstance(scores, float):
            scores = [scores]

        scored = sorted(
            zip(chunks, scores), key=lambda x: x[1], reverse=True
        )
        return scored[:top_n]

    # ------------------------------------------------------------------
    # 数据获取
    # ------------------------------------------------------------------

    async def _fetch_chunks(self, chunk_ids: list[str]) -> list[Chunk]:
        """根据 chunk_id 列表从 ES 获取完整 Chunk 数据。"""
        if not chunk_ids:
            return []

        es = await self._get_es()
        chunks: list[Chunk] = []

        for cid in chunk_ids:
            try:
                doc = await es.get(index=self.config.es_index, id=cid)
                src = doc["_source"]
                meta_fields = {
                    k: src[k] for k in ChunkMetadata.model_fields if k in src
                }
                chunks.append(
                    Chunk(
                        chunk_id=cid,
                        content=src.get("content", ""),
                        embedding_text=src.get("embedding_text", ""),
                        metadata=ChunkMetadata(**meta_fields),
                    )
                )
            except Exception:
                logger.warning("chunk_fetch_failed", chunk_id=cid)

        return chunks

    async def _fetch_parent_chunks(self, chunks: list[Chunk]) -> list[Chunk]:
        """根据子 chunk 的 parent_chunk_id 获取对应的父 chunk。"""
        parent_ids: set[str] = set()
        for chunk in chunks:
            if chunk.metadata.parent_chunk_id:
                parent_ids.add(chunk.metadata.parent_chunk_id)
        return await self._fetch_chunks(list(parent_ids))

    # ------------------------------------------------------------------
    # 主检索流程
    # ------------------------------------------------------------------

    async def retrieve(
        self,
        query: str,
        intent: IntentType = IntentType.REASONING,
        filters: dict | None = None,
    ) -> RetrievalResult:
        """执行完整的混合检索流程。

        流程：向量检索 + BM25 → 合并去重 → 跨文档聚合
              → 获取完整 chunk → 重排序 → 获取父 chunk。

        当向量检索失败时，自动降级为仅 BM25 检索。
        """
        filters = filters or {}
        cfg = self.config

        # 向量检索（失败时降级）
        try:
            vec_results = await self._vector_search(
                query, cfg.vector_top_k, filters
            )
        except Exception:
            logger.warning("vector_search_failed_falling_back_to_bm25")
            vec_results = []

        # BM25 检索
        bm25_results = await self._bm25_search(query, cfg.bm25_top_k, filters)

        # 合并、聚合
        merged = self._merge_results(vec_results, bm25_results, intent)
        aggregated = self._cross_doc_aggregate(merged)

        # 获取完整 chunk 数据
        chunk_ids = [r["chunk_id"] for r in aggregated]
        chunks = await self._fetch_chunks(chunk_ids)

        # 重排序
        reranked = self._rerank(query, chunks, cfg.rerank_top_n)
        final_chunks = [c for c, _ in reranked]
        scores = [s for _, s in reranked]

        # 获取父 chunk
        parent_chunks = await self._fetch_parent_chunks(final_chunks)

        return RetrievalResult(
            chunks=final_chunks,
            parent_chunks=parent_chunks,
            scores=scores,
        )

    async def close(self) -> None:
        """清理 ES 连接资源。"""
        if self._es is not None:
            await self._es.close()
