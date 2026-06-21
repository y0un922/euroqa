"""Shared Milvus collection schema helpers."""

from __future__ import annotations

from pymilvus import Collection, CollectionSchema, DataType, FieldSchema, utility


CANONICAL_FIELD_NAMES = [
    "chunk_id",
    "embedding",
    "source",
    "element_type",
    "doc_type",
    "standard_family",
    "doc_version",
]


def build_collection_schema() -> CollectionSchema:
    """Build the canonical Eurocode chunk collection schema."""
    fields = [
        FieldSchema(
            CANONICAL_FIELD_NAMES[0], DataType.VARCHAR, is_primary=True, max_length=64
        ),
        FieldSchema(CANONICAL_FIELD_NAMES[1], DataType.FLOAT_VECTOR, dim=1024),
        FieldSchema(CANONICAL_FIELD_NAMES[2], DataType.VARCHAR, max_length=128),
        FieldSchema(CANONICAL_FIELD_NAMES[3], DataType.VARCHAR, max_length=16),
        FieldSchema(CANONICAL_FIELD_NAMES[4], DataType.VARCHAR, max_length=16),
        FieldSchema(CANONICAL_FIELD_NAMES[5], DataType.VARCHAR, max_length=64),
        FieldSchema(CANONICAL_FIELD_NAMES[6], DataType.VARCHAR, max_length=16),
    ]
    return CollectionSchema(fields, description="Eurocode chunks")


def _validate_collection_schema(collection: Collection, name: str) -> None:
    """Raise an actionable error when an existing collection has an old schema."""
    existing_fields = [field.name for field in collection.schema.fields]
    if existing_fields == CANONICAL_FIELD_NAMES:
        return
    raise RuntimeError(
        f"Milvus collection '{name}' schema is incompatible. "
        f"Expected fields {CANONICAL_FIELD_NAMES}, got {existing_fields}. "
        "Drop and rebuild this collection, or set MILVUS_COLLECTION to a new name "
        "and rebuild indexes."
    )


def ensure_collection(name: str) -> Collection:
    """Open or create the canonical Milvus collection.

    The caller must connect to Milvus before calling this function. The returned
    collection is intentionally not loaded.
    """
    if utility.has_collection(name):
        collection = Collection(name)
        _validate_collection_schema(collection, name)
        return collection

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
