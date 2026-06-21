"""Index administration helpers for Milvus and Elasticsearch."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from elasticsearch import AsyncElasticsearch
from pymilvus import Collection, connections, utility
from pymilvus.exceptions import MilvusException

from pipeline.chunk import create_chunks, validate_unique_chunk_ids
from pipeline.config import PipelineConfig
from pipeline.index import (
    delete_document_sources,
    index_to_elasticsearch,
    index_to_milvus,
)
from pipeline.structure import (
    TreePruningConfig,
    parse_markdown_to_tree,
    prune_document_tree,
)
from server.deps import invalidate_retriever_cache
from shared.elasticsearch_client import build_async_elasticsearch
from shared.milvus_schema import CANONICAL_FIELD_NAMES, ensure_collection


def source_names_for_doc_id(doc_id: str) -> list[str]:
    """Return current and legacy source names used by indexes for a document."""
    return list(dict.fromkeys([doc_id, doc_id.replace("_", " ")]))


def connect_milvus(config: PipelineConfig) -> None:
    """Connect to Milvus using the pipeline configuration."""
    connections.connect(host=config.milvus_host, port=config.milvus_port)


def _milvus_collection_stats(config: PipelineConfig) -> dict[str, Any]:
    try:
        connect_milvus(config)
        exists = utility.has_collection(config.milvus_collection)
        if not exists:
            return {
                "exists": False,
                "collection": config.milvus_collection,
                "fields": [],
                "entity_count": 0,
                "schema_ok": False,
            }
        collection = Collection(config.milvus_collection)
        fields = [field.name for field in collection.schema.fields]
        return {
            "exists": True,
            "collection": config.milvus_collection,
            "fields": fields,
            "entity_count": int(collection.num_entities),
            "schema_ok": fields == CANONICAL_FIELD_NAMES,
        }
    except Exception as exc:
        return {
            "exists": False,
            "collection": config.milvus_collection,
            "fields": [],
            "entity_count": 0,
            "schema_ok": False,
            "error": str(exc),
        }


async def _es_index_stats(
    es: AsyncElasticsearch,
    config: PipelineConfig,
) -> dict[str, Any]:
    exists = await es.indices.exists(index=config.es_index)
    if not exists:
        return {
            "exists": False,
            "index": config.es_index,
            "document_count": 0,
            "mapping_fields": [],
        }
    count_response = await es.count(index=config.es_index)
    mapping_response = await es.indices.get_mapping(index=config.es_index)
    mapping = mapping_response.get(config.es_index, {}).get("mappings", {})
    properties = mapping.get("properties", {})
    return {
        "exists": True,
        "index": config.es_index,
        "document_count": int(count_response.get("count", 0) or 0),
        "mapping_fields": sorted(properties.keys()),
    }


async def _es_sources(
    es: AsyncElasticsearch, config: PipelineConfig
) -> list[dict[str, Any]]:
    if not await es.indices.exists(index=config.es_index):
        return []
    response = await es.search(
        index=config.es_index,
        size=0,
        body={
            "aggs": {
                "sources": {
                    "terms": {
                        "field": "source",
                        "size": 1000,
                        "order": {"_key": "asc"},
                    }
                }
            }
        },
    )
    buckets = response.get("aggregations", {}).get("sources", {}).get("buckets", [])
    return [
        {"source": bucket.get("key"), "elasticsearch_count": bucket.get("doc_count", 0)}
        for bucket in buckets
    ]


async def index_overview(config: PipelineConfig | None = None) -> dict[str, Any]:
    """Return Milvus and Elasticsearch index health and source aggregates."""
    cfg = config or PipelineConfig()
    milvus = _milvus_collection_stats(cfg)
    es = build_async_elasticsearch(cfg.es_url)
    try:
        elasticsearch = await _es_index_stats(es, cfg)
        sources = await _es_sources(es, cfg)
    finally:
        await es.close()
    return {"milvus": milvus, "elasticsearch": elasticsearch, "sources": sources}


def _milvus_count_for_sources(config: PipelineConfig, sources: list[str]) -> int:
    try:
        connect_milvus(config)
        if not utility.has_collection(config.milvus_collection):
            return 0
        collection = ensure_collection(config.milvus_collection)
        collection.load()
        expr = "source in [" + ", ".join(json.dumps(source) for source in sources) + "]"
        result = collection.query(expr=expr, output_fields=["chunk_id"], limit=16384)
        return len(result)
    except MilvusException:
        return 0


async def _es_samples_for_sources(
    es: AsyncElasticsearch,
    config: PipelineConfig,
    sources: list[str],
    sample_size: int,
) -> tuple[int, list[dict[str, Any]]]:
    if not await es.indices.exists(index=config.es_index):
        return 0, []
    response = await es.search(
        index=config.es_index,
        size=sample_size,
        body={
            "query": {"terms": {"source": sources}},
            "_source": [
                "chunk_id",
                "source",
                "source_title",
                "section_path",
                "page_numbers",
                "clause_ids",
                "element_type",
                "content",
            ],
            "sort": [{"chunk_id": {"order": "asc"}}],
        },
    )
    total = response.get("hits", {}).get("total", {})
    if isinstance(total, dict):
        count = int(total.get("value", 0) or 0)
    else:
        count = int(total or 0)
    samples = []
    for hit in response.get("hits", {}).get("hits", []):
        source = hit.get("_source", {})
        content = str(source.get("content") or "")
        samples.append(
            {
                "chunk_id": source.get("chunk_id"),
                "source": source.get("source"),
                "source_title": source.get("source_title"),
                "section_path": source.get("section_path") or [],
                "page_numbers": source.get("page_numbers") or [],
                "clause_ids": source.get("clause_ids") or [],
                "element_type": source.get("element_type"),
                "content_preview": content[:500],
            }
        )
    return count, samples


async def inspect_document_index(
    doc_id: str,
    *,
    sample_size: int = 5,
    config: PipelineConfig | None = None,
) -> dict[str, Any]:
    """Return index counts and sample chunks for one document id."""
    cfg = config or PipelineConfig()
    sources = source_names_for_doc_id(doc_id)
    milvus_count = _milvus_count_for_sources(cfg, sources)
    es = build_async_elasticsearch(cfg.es_url)
    try:
        es_count, samples = await _es_samples_for_sources(es, cfg, sources, sample_size)
    finally:
        await es.close()
    return {
        "doc_id": doc_id,
        "sources": sources,
        "milvus_count": milvus_count,
        "elasticsearch_count": es_count,
        "samples": samples,
    }


async def delete_document_index(
    doc_id: str,
    *,
    config: PipelineConfig | None = None,
) -> dict[str, Any]:
    """Delete one document from Milvus and Elasticsearch indexes only."""
    cfg = config or PipelineConfig()
    deleted = await delete_document_sources(source_names_for_doc_id(doc_id), cfg)
    await invalidate_retriever_cache()
    return {
        "doc_id": doc_id,
        "sources": source_names_for_doc_id(doc_id),
        "deleted": {
            "milvus": int(deleted.get("milvus", 0) or 0),
            "elasticsearch": int(deleted.get("elasticsearch", 0) or 0),
        },
    }


def _load_parsed_tree(doc_id: str, config: PipelineConfig):
    parsed_dir = Path(config.parsed_dir) / doc_id
    md_path = parsed_dir / f"{doc_id}.md"
    content_list_path = parsed_dir / f"{doc_id}_content_list.json"
    meta_path = parsed_dir / f"{doc_id}_meta.json"
    if not md_path.is_file() or not content_list_path.is_file():
        raise FileNotFoundError(f"parsed document not found: {parsed_dir}")

    markdown = md_path.read_text(encoding="utf-8")
    content_list = json.loads(content_list_path.read_text(encoding="utf-8"))
    meta = (
        json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.is_file() else {}
    )
    source_title = meta.get("title") or doc_id.replace("_", " ")
    pruning_config = TreePruningConfig.from_pipeline_settings(
        enabled=config.tree_pruning_enabled,
        body_start_titles=config.tree_pruning_body_start_titles,
    )
    tree = prune_document_tree(
        parse_markdown_to_tree(markdown, source=doc_id, content_list=content_list),
        pruning_config,
    )
    return tree, source_title


async def rebuild_document_index(
    doc_id: str,
    *,
    delete_first: bool = True,
    config: PipelineConfig | None = None,
) -> dict[str, Any]:
    """Rebuild one document index from data/parsed without reparsing the PDF."""
    cfg = config or PipelineConfig()
    tree, source_title = _load_parsed_tree(doc_id, cfg)
    chunks = create_chunks(tree, source_title=source_title)
    validate_unique_chunk_ids(chunks)

    deleted = {"milvus": 0, "elasticsearch": 0}
    if delete_first:
        deleted = await delete_document_sources(source_names_for_doc_id(doc_id), cfg)

    milvus_count = await index_to_milvus(chunks, cfg)
    es_count = await index_to_elasticsearch(chunks, cfg)
    await invalidate_retriever_cache()
    return {
        "doc_id": doc_id,
        "chunks": len(chunks),
        "deleted": {
            "milvus": int(deleted.get("milvus", 0) or 0),
            "elasticsearch": int(deleted.get("elasticsearch", 0) or 0),
        },
        "indexed": {"milvus": milvus_count, "elasticsearch": es_count},
    }
