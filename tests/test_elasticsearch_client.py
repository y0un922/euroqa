"""Tests for Elasticsearch client helpers."""
from __future__ import annotations

from shared.elasticsearch_client import build_async_elasticsearch


def test_build_async_elasticsearch_uses_es8_compatibility_headers(monkeypatch):
    captured = {}

    class _FakeAsyncElasticsearch:
        def __init__(self, url: str, **kwargs):
            captured["url"] = url
            captured["kwargs"] = kwargs

    monkeypatch.setattr(
        "shared.elasticsearch_client.AsyncElasticsearch",
        _FakeAsyncElasticsearch,
    )

    client = build_async_elasticsearch("http://localhost:9200")

    assert isinstance(client, _FakeAsyncElasticsearch)
    assert captured["url"] == "http://localhost:9200"
    assert captured["kwargs"]["headers"] == {
        "accept": "application/vnd.elasticsearch+json; compatible-with=8",
        "content-type": "application/vnd.elasticsearch+json; compatible-with=8",
    }
