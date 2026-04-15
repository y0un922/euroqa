"""Shared Elasticsearch client helpers."""
from __future__ import annotations

from elasticsearch import AsyncElasticsearch

ES8_COMPAT_HEADERS = {
    "accept": "application/vnd.elasticsearch+json; compatible-with=8",
    "content-type": "application/vnd.elasticsearch+json; compatible-with=8",
}


def build_async_elasticsearch(es_url: str) -> AsyncElasticsearch:
    """Build an async Elasticsearch client compatible with Elasticsearch 8.x."""
    return AsyncElasticsearch(es_url, headers=ES8_COMPAT_HEADERS)
