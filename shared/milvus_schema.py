"""Shared Milvus collection schema helpers."""
from __future__ import annotations

from pymilvus import Collection, CollectionSchema, DataType, FieldSchema, utility


def build_collection_schema() -> CollectionSchema:
    """Build the canonical Eurocode chunk collection schema."""
    fields = [
        FieldSchema("chunk_id", DataType.VARCHAR, is_primary=True, max_length=64),
        FieldSchema("embedding", DataType.FLOAT_VECTOR, dim=1024),
        FieldSchema("source", DataType.VARCHAR, max_length=128),
        FieldSchema("element_type", DataType.VARCHAR, max_length=16),
    ]
    return CollectionSchema(fields, description="Eurocode chunks")


def ensure_collection(name: str) -> Collection:
    """Open or create the canonical Milvus collection.

    The caller must connect to Milvus before calling this function. The returned
    collection is intentionally not loaded.
    """
    if utility.has_collection(name):
        return Collection(name)

    collection = Collection(name, build_collection_schema())
    collection.create_index(
        "embedding",
        {
            "metric_type": "COSINE",
            "index_type": "HNSW",
            "params": {"M": 16, "efConstruction": 256},
        },
    )
    return collection
