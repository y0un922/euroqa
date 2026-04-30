"""Stage 4: Embedding generation + Milvus/ES indexing.

bge-m3 generates dense vectors → Milvus stores dense vectors.
Chunk text + metadata → Elasticsearch for BM25 + metadata queries.
"""
from __future__ import annotations

import structlog
from pymilvus.exceptions import MilvusException
from pymilvus import (
    Collection,
    CollectionSchema,
    DataType,
    FieldSchema,
    connections,
    utility,
)

from pipeline.config import PipelineConfig
from shared.elasticsearch_client import build_async_elasticsearch
from shared.model_clients import build_embedding_client
from server.models.schemas import Chunk

logger = structlog.get_logger()


def _build_embedding_client(config: PipelineConfig):
    return build_embedding_client(config)


def _init_milvus_collection(config: PipelineConfig) -> Collection:
    """Create or get Milvus collection."""
    try:
        connections.connect(host=config.milvus_host, port=config.milvus_port)
    except MilvusException as exc:
        host_port = f"{config.milvus_host}:{config.milvus_port}"
        raise RuntimeError(
            "Milvus is unavailable at "
            f"{host_port}. Start it with `docker compose up -d milvus` "
            "or update MILVUS_HOST/MILVUS_PORT before rerunning Stage 4."
        ) from exc

    if utility.has_collection(config.milvus_collection):
        return Collection(config.milvus_collection)

    fields = [
        FieldSchema("chunk_id", DataType.VARCHAR, is_primary=True, max_length=64),
        FieldSchema("embedding", DataType.FLOAT_VECTOR, dim=1024),
        FieldSchema("source", DataType.VARCHAR, max_length=128),
        FieldSchema("element_type", DataType.VARCHAR, max_length=16),
    ]
    schema = CollectionSchema(fields, description="Eurocode chunks")
    collection = Collection(config.milvus_collection, schema)
    collection.create_index(
        "embedding",
        {"metric_type": "COSINE", "index_type": "HNSW", "params": {"M": 16, "efConstruction": 256}},
    )
    return collection


async def index_to_milvus(chunks: list[Chunk], config: PipelineConfig) -> int:
    """Index chunk dense vectors into Milvus."""
    collection = _init_milvus_collection(config)

    to_embed = [c for c in chunks if c.embedding_text]
    if not to_embed:
        return 0

    texts = [c.embedding_text for c in to_embed]
    embeddings = await _build_embedding_client(config).embed_texts(texts)

    data = [
        [c.chunk_id for c in to_embed],
        embeddings,
        [c.metadata.source for c in to_embed],
        [c.metadata.element_type.value for c in to_embed],
    ]
    collection.insert(data)
    collection.flush()
    logger.info("milvus_indexed", count=len(to_embed))
    return len(to_embed)


_ES_MAPPING = {
    "mappings": {
        "properties": {
            "chunk_id": {"type": "keyword"},
            "content": {"type": "text", "analyzer": "standard"},
            "embedding_text": {"type": "text", "analyzer": "standard"},
            "source": {"type": "keyword"},
            "source_title": {"type": "keyword"},
            "section_path": {"type": "keyword"},
            "page_numbers": {"type": "integer"},
            "clause_ids": {"type": "keyword"},
            "element_type": {"type": "keyword"},
            "cross_refs": {"type": "keyword"},
            "object_type": {"type": "keyword"},
            "object_label": {"type": "keyword"},
            "object_id": {"type": "keyword"},
            "object_aliases": {"type": "keyword"},
            "ref_labels": {"type": "keyword"},
            "ref_object_ids": {"type": "keyword"},
            "parent_chunk_id": {"type": "keyword"},
            "parent_text_chunk_id": {"type": "keyword"},
            "bbox": {"type": "float"},
            "bbox_page_idx": {"type": "integer"},
            "page_file_index": {"type": "integer"},
        }
    }
}


async def delete_document_from_milvus(
    source_name: str,
    config: PipelineConfig,
) -> int:
    """删除指定 source 在 Milvus 中的所有 chunks。"""
    collection = _init_milvus_collection(config)
    collection.load()
    escaped = source_name.replace("\\", "\\\\").replace('"', '\\"')
    result = collection.delete(expr=f'source == "{escaped}"')
    collection.flush()
    deleted = int(getattr(result, "delete_count", 0) or 0)
    logger.info("milvus_document_deleted", source=source_name, deleted=deleted)
    return deleted


async def delete_document_from_elasticsearch(
    source_name: str,
    config: PipelineConfig,
) -> int:
    """删除指定 source 在 Elasticsearch 中的所有 chunks。"""
    es = build_async_elasticsearch(config.es_url)
    try:
        if not await es.indices.exists(index=config.es_index):
            return 0
        response = await es.delete_by_query(
            index=config.es_index,
            body={"query": {"term": {"source": source_name}}},
            refresh=True,
            conflicts="proceed",
        )
        deleted = int(response.get("deleted", 0) or 0)
        logger.info("es_document_deleted", source=source_name, deleted=deleted)
        return deleted
    finally:
        await es.close()


async def delete_document_chunks(
    source_name: str,
    config: PipelineConfig,
) -> dict[str, int]:
    """删除指定文档在 Milvus 和 Elasticsearch 中的所有 chunks。"""
    milvus_deleted = await delete_document_from_milvus(source_name, config)
    es_deleted = await delete_document_from_elasticsearch(source_name, config)
    return {"milvus": milvus_deleted, "elasticsearch": es_deleted}


async def index_to_elasticsearch(chunks: list[Chunk], config: PipelineConfig) -> int:
    """Index chunks into Elasticsearch for BM25 + metadata queries."""
    es = build_async_elasticsearch(config.es_url)

    try:
        if not await es.indices.exists(index=config.es_index):
            await es.indices.create(index=config.es_index, body=_ES_MAPPING)

        for chunk in chunks:
            doc = {
                "chunk_id": chunk.chunk_id,
                "content": chunk.content,
                "embedding_text": chunk.embedding_text,
                **chunk.metadata.model_dump(),
            }
            await es.index(index=config.es_index, id=chunk.chunk_id, document=doc)

        await es.indices.refresh(index=config.es_index)
        logger.info("es_indexed", count=len(chunks))
        return len(chunks)
    finally:
        await es.close()
