"""Search backend helpers for hybrid retrieval."""

from __future__ import annotations

import asyncio

import structlog
from elasticsearch import NotFoundError

from server.config import ServerConfig
from server.core import retrieval_helpers

logger = structlog.get_logger(__name__)

_DEFAULT_BM25_FIELDS = [
    "content^2",
    "embedding_text",
    "source_title.text^3",
    "section_path.text^2",
    "clause_ids.text^4",
    "object_aliases.text^5",
]


async def _vector_search(
    collection: object,
    embedding_client: object,
    _config: ServerConfig,
    query: str,
    top_k: int,
    filters: dict,
) -> list[dict]:
    """使用 BGE-M3 编码查询，在 Milvus 中进行向量近似搜索。"""
    embedding = (await embedding_client.embed_texts([query]))[0]

    # 构造 Milvus 布尔过滤表达式（不含 element_type，已改为 boost）
    expr_parts: list[str] = []
    if "source" in filters:
        source_expr = retrieval_helpers._build_milvus_source_expr(filters["source"])
        if source_expr:
            expr_parts.append(source_expr)
    expr = " and ".join(expr_parts) if expr_parts else None

    results = await asyncio.to_thread(
        collection.search,
        data=[embedding],
        anns_field="embedding",
        param={"metric_type": "COSINE", "params": {"ef": 128}},
        limit=top_k,
        expr=expr,
        output_fields=["chunk_id", "source", "element_type"],
    )

    results = [
        {
            "chunk_id": hit.entity.get("chunk_id"),
            "source": hit.entity.get("source"),
            "score": hit.score,
        }
        for hit in results[0]
    ]
    return retrieval_helpers._filter_results_by_source(results, filters)


async def _bm25_search(
    es: object,
    config: ServerConfig,
    query: str,
    top_k: int,
    filters: dict,
    fields: list[str] | None = None,
    preferred_element_type: str | None = None,
) -> list[dict]:
    """在 Elasticsearch 中使用 multi_match 进行 BM25 全文检索。"""
    search_fields = fields or _DEFAULT_BM25_FIELDS

    must_clauses = [
        {
            "multi_match": {
                "query": query,
                "fields": search_fields,
            }
        }
    ]
    filter_clauses = retrieval_helpers._build_source_filter_clauses(filters)

    # element_type 作为 should boost 而非 filter，
    # 偏好匹配类型的 chunk 但不排除其他类型
    should_clauses: list[dict] = []
    if preferred_element_type:
        should_clauses.append(
            {"term": {"element_type": {"value": preferred_element_type, "boost": 2.0}}}
        )

    body = {
        "query": {
            "bool": {
                "must": must_clauses,
                "filter": filter_clauses,
                "should": should_clauses,
            }
        },
        "size": top_k,
    }
    try:
        resp = await es.search(index=config.es_index, body=body)
    except NotFoundError:
        logger.warning(
            "bm25_search_index_missing",
            index=config.es_index,
            query=query[:80],
        )
        return []

    return [
        {
            "chunk_id": hit["_id"],
            "source": hit["_source"].get("source", ""),
            "score": hit["_score"],
        }
        for hit in resp["hits"]["hits"]
    ]
