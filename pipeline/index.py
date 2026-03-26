"""Stage 4: Embedding generation + Milvus/ES indexing.

bge-m3 generates dense vectors → Milvus stores dense vectors.
Chunk text + metadata → Elasticsearch for BM25 + metadata queries.
"""
from __future__ import annotations

import structlog
from FlagEmbedding import BGEM3FlagModel
from elasticsearch import AsyncElasticsearch
from pymilvus import (
    Collection,
    CollectionSchema,
    DataType,
    FieldSchema,
    connections,
    utility,
)

from pipeline.config import PipelineConfig
from server.models.schemas import Chunk

logger = structlog.get_logger()

_embed_model: BGEM3FlagModel | None = None


def _get_embed_model() -> BGEM3FlagModel:
    global _embed_model
    if _embed_model is None:
        _embed_model = BGEM3FlagModel("BAAI/bge-m3", use_fp16=True)
    return _embed_model


def _embed_texts(texts: list[str]) -> list[list[float]]:
    """Batch generate dense embeddings."""
    model = _get_embed_model()
    result = model.encode(texts, return_dense=True, return_sparse=False, return_colbert_vecs=False)
    return result["dense_vecs"].tolist()


def _init_milvus_collection(config: PipelineConfig) -> Collection:
    """Create or get Milvus collection."""
    connections.connect(host=config.milvus_host, port=config.milvus_port)

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
    embeddings = _embed_texts(texts)

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
            "parent_chunk_id": {"type": "keyword"},
            "parent_text_chunk_id": {"type": "keyword"},
        }
    }
}


async def index_to_elasticsearch(chunks: list[Chunk], config: PipelineConfig) -> int:
    """Index chunks into Elasticsearch for BM25 + metadata queries."""
    es = AsyncElasticsearch(config.es_url)

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
