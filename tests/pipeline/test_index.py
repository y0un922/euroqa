"""Tests for pipeline indexing."""
from __future__ import annotations

import pytest
from pymilvus.exceptions import MilvusException

from pipeline.config import PipelineConfig
from pipeline.index import (
    _init_milvus_collection,
    delete_document_from_milvus,
    index_to_milvus,
)
from server.models.schemas import Chunk, ChunkMetadata, ElementType


class _FakeCollection:
    def __init__(self):
        self.inserted = None
        self.flushed = False
        self.loaded = False
        self.deleted_expr = None

    def insert(self, data):
        self.inserted = data

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
        return [[0.1, 0.2]]


@pytest.mark.asyncio
async def test_index_to_milvus_uses_embedding_client(monkeypatch):
    chunk = Chunk(
        chunk_id="chunk-1",
        content="Chunk content",
        embedding_text="Embedding text",
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
async def test_delete_document_from_milvus_loads_collection_before_delete(monkeypatch):
    collection = _FakeCollection()
    monkeypatch.setattr("pipeline.index._init_milvus_collection", lambda config: collection)

    count = await delete_document_from_milvus(
        'DG EN1990 "Guide"',
        PipelineConfig(),
    )

    assert count == 2
    assert collection.loaded is True
    assert collection.deleted_expr == 'source == "DG EN1990 \\"Guide\\""'
    assert collection.flushed is True


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
