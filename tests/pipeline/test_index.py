"""Tests for pipeline indexing."""
from __future__ import annotations

import pytest
from pymilvus.exceptions import MilvusException

from pipeline.config import PipelineConfig
from pipeline.index import (
    _init_milvus_collection,
    delete_document_from_milvus,
    delete_document_sources_from_elasticsearch,
    delete_document_sources_from_milvus,
    index_to_milvus,
)
from server.models.schemas import Chunk, ChunkMetadata, ElementType
from shared.elasticsearch_client import ES_INDEX_MAPPING
from shared.milvus_schema import ensure_collection


class _FakeCollection:
    def __init__(self):
        self.inserted = None
        self.insert_calls = []
        self.flushed = False
        self.loaded = False
        self.deleted_expr = None

    def insert(self, data):
        self.inserted = data
        self.insert_calls.append(data)

    def load(self):
        self.loaded = True

    def delete(self, expr: str):
        self.deleted_expr = expr
        return type("DeleteResult", (), {"delete_count": 2})()

    def flush(self):
        self.flushed = True


class _FakeEmbeddingClient:
    def __init__(self):
        self.calls = []

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(texts)
        return [[0.1, 0.2] for _ in texts]


def _chunk(chunk_id: str, embedding_text: str = "Embedding text") -> Chunk:
    return Chunk(
        chunk_id=chunk_id,
        content="Chunk content",
        embedding_text=embedding_text,
        metadata=ChunkMetadata(
            source="EN 1990:2002",
            source_title="Basis",
            section_path=["2.3"],
            page_numbers=[28],
            page_file_index=[27],
            clause_ids=["2.3(1)"],
            element_type=ElementType.TEXT,
        ),
    )


def test_es_mapping_keeps_keyword_fields_with_text_subfields_for_bm25():
    properties = ES_INDEX_MAPPING["mappings"]["properties"]

    for field_name in (
        "source_title",
        "section_path",
        "clause_ids",
        "object_aliases",
        "ref_labels",
    ):
        field = properties[field_name]
        assert field["type"] == "keyword"
        assert field["fields"]["text"] == {
            "type": "text",
            "analyzer": "standard",
        }


@pytest.mark.asyncio
async def test_index_to_milvus_uses_embedding_client(monkeypatch):
    chunk = _chunk("chunk-1")
    collection = _FakeCollection()
    client = _FakeEmbeddingClient()

    monkeypatch.setattr("pipeline.index._build_embedding_client", lambda config: client)
    monkeypatch.setattr("pipeline.index._init_milvus_collection", lambda config: collection)

    count = await index_to_milvus(
        [chunk],
        PipelineConfig(
            embedding_provider="remote",
            embedding_api_url="https://embed.example/v1/embeddings",
            embedding_model="embed-model",
        ),
    )

    assert count == 1
    assert client.calls == [["Embedding text"]]
    assert collection.inserted[0] == ["chunk-1"]
    assert collection.inserted[1] == [[0.1, 0.2]]
    assert collection.flushed is True


@pytest.mark.asyncio
async def test_index_to_milvus_inserts_in_configured_batches(monkeypatch):
    chunks = [
        _chunk("chunk-1", "Embedding text 1"),
        _chunk("chunk-2", "Embedding text 2"),
        _chunk("chunk-3", "Embedding text 3"),
    ]
    collection = _FakeCollection()
    client = _FakeEmbeddingClient()

    monkeypatch.setattr("pipeline.index._build_embedding_client", lambda config: client)
    monkeypatch.setattr("pipeline.index._init_milvus_collection", lambda config: collection)

    count = await index_to_milvus(
        chunks,
        PipelineConfig(
            embedding_provider="remote",
            embedding_api_url="https://embed.example/v1/embeddings",
            embedding_model="embed-model",
            milvus_insert_batch_size=2,
        ),
    )

    assert count == 3
    assert client.calls == [
        ["Embedding text 1", "Embedding text 2"],
        ["Embedding text 3"],
    ]
    assert [call[0] for call in collection.insert_calls] == [
        ["chunk-1", "chunk-2"],
        ["chunk-3"],
    ]
    assert collection.flushed is True


@pytest.mark.asyncio
async def test_delete_document_from_milvus_loads_collection_before_delete(monkeypatch):
    collection = _FakeCollection()
    monkeypatch.setattr("pipeline.index._init_milvus_collection", lambda config: collection)

    count = await delete_document_from_milvus(
        'DG EN1990 "Guide"',
        PipelineConfig(),
    )

    assert count == 2
    assert collection.loaded is True
    assert collection.deleted_expr == 'source in ["DG EN1990 \\"Guide\\""]'
    assert collection.flushed is False


@pytest.mark.asyncio
async def test_delete_document_sources_from_milvus_deletes_sources_once(monkeypatch):
    collection = _FakeCollection()
    monkeypatch.setattr("pipeline.index._init_milvus_collection", lambda config: collection)

    count = await delete_document_sources_from_milvus(
        ['DG EN1990 "Guide"', "DG EN1990 Guide", 'DG EN1990 "Guide"'],
        PipelineConfig(),
    )

    assert count == 2
    assert collection.loaded is True
    assert collection.deleted_expr == (
        'source in ["DG EN1990 \\"Guide\\"", "DG EN1990 Guide"]'
    )
    assert collection.flushed is False


@pytest.mark.asyncio
async def test_delete_document_sources_from_elasticsearch_uses_terms_query(monkeypatch):
    class _FakeIndices:
        async def exists(self, *, index):
            return True

    class _FakeElasticsearch:
        def __init__(self):
            self.indices = _FakeIndices()
            self.delete_call = None
            self.closed = False

        async def delete_by_query(self, **kwargs):
            self.delete_call = kwargs
            return {"deleted": 7}

        async def close(self):
            self.closed = True

    es = _FakeElasticsearch()
    monkeypatch.setattr("pipeline.index.build_async_elasticsearch", lambda _url: es)

    count = await delete_document_sources_from_elasticsearch(
        ["EN_1992_1_1", "EN 1992 1 1", "EN_1992_1_1"],
        PipelineConfig(es_index="chunks"),
    )

    assert count == 7
    assert es.delete_call == {
        "index": "chunks",
        "body": {"query": {"terms": {"source": ["EN_1992_1_1", "EN 1992 1 1"]}}},
        "refresh": False,
        "conflicts": "proceed",
    }
    assert es.closed is True


def test_init_milvus_collection_raises_actionable_error_when_server_unavailable(
    monkeypatch,
):
    def _raise_connect_error(**kwargs):
        raise MilvusException(
            code=2,
            message="Fail connecting to server on localhost:19530, illegal connection params or server unavailable",
        )

    monkeypatch.setattr("pipeline.index.connections.connect", _raise_connect_error)

    with pytest.raises(RuntimeError, match="docker compose up -d milvus") as exc_info:
        _init_milvus_collection(PipelineConfig())

    assert "localhost:19530" in str(exc_info.value)


def test_ensure_collection_creates_canonical_schema_and_hnsw_index(monkeypatch):
    calls: dict[str, object] = {}

    class _FakeCollection:
        def __init__(self, name, schema=None):
            calls["name"] = name
            calls["schema"] = schema
            self.index_args = None

        def create_index(self, field_name, index_params):
            self.index_args = (field_name, index_params)
            calls["index_args"] = self.index_args

    monkeypatch.setattr("shared.milvus_schema.utility.has_collection", lambda name: False)
    monkeypatch.setattr("shared.milvus_schema.Collection", _FakeCollection)

    collection = ensure_collection("chunks")

    assert calls["name"] == "chunks"
    field_names = [field.name for field in calls["schema"].fields]
    assert field_names == ["chunk_id", "embedding", "source", "element_type"]
    assert calls["index_args"] == (
        "embedding",
        {
            "metric_type": "COSINE",
            "index_type": "HNSW",
            "params": {"M": 16, "efConstruction": 256},
        },
    )
    assert collection is not None
