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
        "max_length": 8192,
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


@pytest.mark.asyncio
async def test_remote_embedding_records_official_usage(monkeypatch):
    from shared.usage import collect_usage

    calls = []
    responses = {
        ("POST", "https://api.siliconflow.cn/v1/embeddings"): [
            _FakeResponse(
                {
                    "data": [{"index": 0, "embedding": [0.1, 0.2]}],
                    "usage": {"prompt_tokens": 12, "total_tokens": 12},
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
        model="BAAI/bge-m3",
        api_url="https://api.siliconflow.cn/v1",
        api_key="embed-key",
    )

    with collect_usage() as ledger:
        await client.embed_texts(["first"])

    report = ledger.report()
    assert report["usage"]["input_tokens"] == 12
    assert report["cost"]["items"][0]["model"] == "BAAI/bge-m3"
    assert report["cost"]["items"][0]["vendor"] == "siliconflow"
    assert report["cost"]["items"][0]["cny"] == 0.0
    assert report["cost"]["unpriced"] == []


@pytest.mark.asyncio
async def test_remote_rerank_records_official_usage(monkeypatch):
    from shared.usage import collect_usage

    calls = []
    responses = {
        ("POST", "https://dashscope.aliyuncs.com/compatible-api/v1/reranks"): [
            _FakeResponse(
                {
                    "results": [{"index": 0, "relevance_score": 0.91}],
                    "usage": {"prompt_tokens": 40, "total_tokens": 40},
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
        model="qwen3-rerank",
        api_url="https://dashscope.aliyuncs.com/compatible-api/v1/reranks",
        api_key="rerank-key",
    )

    with collect_usage() as ledger:
        await client.rerank(query="wind", documents=["doc-a"], top_n=1)

    report = ledger.report()
    assert report["usage"]["input_tokens"] == 40
    assert report["cost"]["items"][0]["model"] == "qwen3-rerank"
    assert report["cost"]["items"][0]["cny"] == pytest.approx(40 * 0.5 / 1_000_000)


@pytest.mark.asyncio
async def test_remote_rerank_client_retries_without_max_length_on_400(monkeypatch):
    calls = []
    responses = {
        ("POST", "https://rerank.example/v1/rerank"): [
            _FakeResponse({"error": "max_length unsupported"}, status_code=400),
            _FakeResponse({"results": [{"index": 0, "relevance_score": 0.91}]}),
            _FakeResponse({"results": [{"index": 0, "relevance_score": 0.92}]}),
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
        max_length=8192,
    )

    first = await client.rerank("wind load", ["doc-a"], 1)
    second = await client.rerank("wind load", ["doc-a"], 1)

    assert first == [(0, 0.91)]
    assert second == [(0, 0.92)]
    assert "max_length" in calls[0][2]["json"]
    assert "max_length" not in calls[1][2]["json"]
    assert "max_length" not in calls[2][2]["json"]
    assert client.supports_max_length is False
