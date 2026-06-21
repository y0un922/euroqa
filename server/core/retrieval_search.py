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

_VECTOR_OUTPUT_FIELDS = [
    "chunk_id",
    "source",
    "element_type",
    "doc_type",
    "standard_family",
    "doc_version",
]
_METADATA_FILTER_FIELDS = {"doc_type", "standard_family", "doc_version"}


async def _vector_search(
    collection: object,
    embedding_client: object,
    _config: ServerConfig,
    query: str,
    top_k: int,
    filters: dict,
) -> list[dict]:
    """使用 BGE-M3 编码查询，在 Milvus 中进行向量近似搜索。"""
    field_names = _collection_field_names(collection)
    if field_names is not None and _unsupported_metadata_filters(filters, field_names):
        return []

    embedding = (await embedding_client.embed_texts([query]))[0]

    # 构造 Milvus 布尔过滤表达式（不含 element_type，已改为 boost）
    expr = retrieval_helpers._build_milvus_filter_expr(filters)
    output_fields = _vector_output_fields(field_names)

    results = await asyncio.to_thread(
        collection.search,
        data=[embedding],
        anns_field="embedding",
        param={"metric_type": "COSINE", "params": {"ef": 128}},
        limit=top_k,
        expr=expr,
        output_fields=output_fields,
    )

    results = [
        {
            "chunk_id": hit.entity.get("chunk_id"),
            "source": hit.entity.get("source"),
            "doc_type": hit.entity.get("doc_type"),
            "standard_family": hit.entity.get("standard_family"),
            "doc_version": hit.entity.get("doc_version"),
            "score": hit.score,
        }
        for hit in results[0]
    ]
    return retrieval_helpers._filter_results_by_source(results, filters)


def _collection_field_names(collection: object) -> set[str] | None:
    schema = getattr(collection, "schema", None)
    fields = getattr(schema, "fields", None)
    if fields is None:
        return None
    names = {
        getattr(field, "name", "")
        for field in fields
        if getattr(field, "name", "")
    }
    return names or None


def _unsupported_metadata_filters(filters: dict, field_names: set[str]) -> bool:
    return any(
        field_name in filters and field_name not in field_names
        for field_name in _METADATA_FILTER_FIELDS
    )


def _vector_output_fields(field_names: set[str] | None) -> list[str]:
    if field_names is None:
        return list(_VECTOR_OUTPUT_FIELDS)
    return [
        field_name
        for field_name in _VECTOR_OUTPUT_FIELDS
        if field_name in field_names
    ]


async def _bm25_search(
    es: object,
    config: ServerConfig,
    query: str,
    top_k: int,
    filters: dict,
    fields: list[str] | None = None,
    preferred_element_type: str | None = None,
    soft_boosts: dict | None = None,
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
    should_clauses.extend(retrieval_helpers._build_soft_boost_clauses(soft_boosts))

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
