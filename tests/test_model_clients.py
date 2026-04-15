"""Tests for shared embedding and rerank clients."""
from __future__ import annotations

import pytest

from shared.model_clients import EmbeddingClient, RerankClient


class _FakeResponse:
    def __init__(self, json_data=None, *, status_code: int = 200):
        self._json_data = json_data
        self.status_code = status_code

    def json(self):
        return self._json_data

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class _FakeAsyncClient:
    def __init__(self, responses, calls):
        self._responses = responses
        self._calls = calls

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url: str, **kwargs):
        self._calls.append(("POST", url, kwargs))
        return self._responses[("POST", url)].pop(0)


@pytest.mark.asyncio
async def test_remote_embedding_client_uses_configured_url_key_and_model(monkeypatch):
    calls = []
    responses = {
        ("POST", "https://embed.example/v1/embeddings"): [
            _FakeResponse(
                {
                    "data": [
                        {"index": 1, "embedding": [0.2, 0.3]},
                        {"index": 0, "embedding": [0.1, 0.2]},
                    ]
                }
            )
        ]
    }

    monkeypatch.setattr(
        "shared.model_clients.httpx.AsyncClient",
        lambda **kwargs: _FakeAsyncClient(responses, calls),
    )

    client = EmbeddingClient(
        provider="remote",
        model="embed-model",
        api_url="https://embed.example/v1/embeddings",
        api_key="embed-key",
    )

    embeddings = await client.embed_texts(["first", "second"])

    assert embeddings == [[0.1, 0.2], [0.2, 0.3]]
    post_call = calls[0]
    assert post_call[0] == "POST"
    assert post_call[1] == "https://embed.example/v1/embeddings"
    assert post_call[2]["headers"]["Authorization"] == "Bearer embed-key"
    assert post_call[2]["json"] == {
        "model": "embed-model",
        "input": ["first", "second"],
    }


@pytest.mark.asyncio
async def test_remote_embedding_client_accepts_openai_compatible_base_url(monkeypatch):
    calls = []
    responses = {
        ("POST", "https://api.siliconflow.cn/v1/embeddings"): [
            _FakeResponse({"data": [{"index": 0, "embedding": [0.1, 0.2]}]})
        ]
    }

    monkeypatch.setattr(
        "shared.model_clients.httpx.AsyncClient",
        lambda **kwargs: _FakeAsyncClient(responses, calls),
    )

    client = EmbeddingClient(
        provider="remote",
        model="BAAI/bge-m3",
        api_url="https://api.siliconflow.cn/v1",
        api_key="embed-key",
    )

    embeddings = await client.embed_texts(["first"])

    assert embeddings == [[0.1, 0.2]]
    assert calls[0][1] == "https://api.siliconflow.cn/v1/embeddings"


@pytest.mark.asyncio
async def test_remote_embedding_client_batches_large_requests(monkeypatch):
    calls = []
    responses = {
        ("POST", "https://embed.example/v1/embeddings"): [
            _FakeResponse(
                {
                    "data": [
                        {"index": 0, "embedding": [0.1, 0.2]},
                        {"index": 1, "embedding": [0.2, 0.3]},
                    ]
                }
            ),
            _FakeResponse({"data": [{"index": 0, "embedding": [0.3, 0.4]}]}),
        ]
    }

    monkeypatch.setattr(
        "shared.model_clients.httpx.AsyncClient",
        lambda **kwargs: _FakeAsyncClient(responses, calls),
    )

    client = EmbeddingClient(
        provider="remote",
        model="embed-model",
        api_url="https://embed.example/v1/embeddings",
        api_key="embed-key",
        batch_size=2,
    )

    embeddings = await client.embed_texts(["first", "second", "third"])

    assert embeddings == [[0.1, 0.2], [0.2, 0.3], [0.3, 0.4]]
    assert len(calls) == 2
    assert calls[0][2]["json"]["input"] == ["first", "second"]
    assert calls[1][2]["json"]["input"] == ["third"]


@pytest.mark.asyncio
async def test_remote_rerank_client_uses_configured_url_key_and_model(monkeypatch):
    calls = []
    responses = {
        ("POST", "https://rerank.example/v1/rerank"): [
            _FakeResponse(
                {
                    "results": [
                        {"index": 2, "relevance_score": 0.91},
                        {"index": 0, "relevance_score": 0.63},
                    ]
                }
            )
        ]
    }

    monkeypatch.setattr(
        "shared.model_clients.httpx.AsyncClient",
        lambda **kwargs: _FakeAsyncClient(responses, calls),
    )

    client = RerankClient(
        provider="remote",
        model="rerank-model",
        api_url="https://rerank.example/v1/rerank",
        api_key="rerank-key",
    )

    results = await client.rerank(
        query="wind load",
        documents=["doc-a", "doc-b", "doc-c"],
        top_n=2,
    )

    assert results == [(2, 0.91), (0, 0.63)]
    post_call = calls[0]
    assert post_call[0] == "POST"
    assert post_call[1] == "https://rerank.example/v1/rerank"
    assert post_call[2]["headers"]["Authorization"] == "Bearer rerank-key"
    assert post_call[2]["json"] == {
        "model": "rerank-model",
        "query": "wind load",
        "documents": ["doc-a", "doc-b", "doc-c"],
        "top_n": 2,
    }


@pytest.mark.asyncio
async def test_remote_rerank_client_accepts_openai_compatible_base_url(monkeypatch):
    calls = []
    responses = {
        ("POST", "https://api.siliconflow.cn/v1/rerank"): [
            _FakeResponse({"results": [{"index": 0, "relevance_score": 0.91}]})
        ]
    }

    monkeypatch.setattr(
        "shared.model_clients.httpx.AsyncClient",
        lambda **kwargs: _FakeAsyncClient(responses, calls),
    )

    client = RerankClient(
        provider="remote",
        model="BAAI/bge-reranker-v2-m3",
        api_url="https://api.siliconflow.cn/v1",
        api_key="rerank-key",
    )

    results = await client.rerank(
        query="wind load",
        documents=["doc-a"],
        top_n=1,
    )

    assert results == [(0, 0.91)]
    assert calls[0][1] == "https://api.siliconflow.cn/v1/rerank"
