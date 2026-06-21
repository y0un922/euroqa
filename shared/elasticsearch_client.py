"""Shared Elasticsearch client helpers."""
from __future__ import annotations

from elasticsearch import AsyncElasticsearch

ES8_COMPAT_HEADERS = {
    "accept": "application/vnd.elasticsearch+json; compatible-with=8",
    "content-type": "application/vnd.elasticsearch+json; compatible-with=8",
}

ES_INDEX_MAPPING = {
    "mappings": {
        "properties": {
            "chunk_id": {"type": "keyword"},
            "content": {"type": "text", "analyzer": "standard"},
            "embedding_text": {"type": "text", "analyzer": "standard"},
            "source": {"type": "keyword"},
            "source_title": {
                "type": "keyword",
                "fields": {
                    "text": {
                        "type": "text",
                        "analyzer": "standard",
                    }
                },
            },
            "section_path": {
                "type": "keyword",
                "fields": {
                    "text": {
                        "type": "text",
                        "analyzer": "standard",
                    }
                },
            },
            "page_numbers": {"type": "integer"},
            "clause_ids": {
                "type": "keyword",
                "fields": {
                    "text": {
                        "type": "text",
                        "analyzer": "standard",
                    }
                },
            },
            "element_type": {"type": "keyword"},
            "doc_type": {"type": "keyword"},
            "standard_family": {"type": "keyword"},
            "doc_version": {"type": "keyword"},
            "cross_refs": {"type": "keyword"},
            "object_type": {"type": "keyword"},
            "object_label": {"type": "keyword"},
            "object_id": {"type": "keyword"},
            "object_aliases": {
                "type": "keyword",
                "fields": {
                    "text": {
                        "type": "text",
                        "analyzer": "standard",
                    }
                },
            },
            "ref_labels": {
                "type": "keyword",
                "fields": {
                    "text": {
                        "type": "text",
                        "analyzer": "standard",
                    }
                },
            },
            "ref_object_ids": {"type": "keyword"},
            "parent_chunk_id": {"type": "keyword"},
            "parent_text_chunk_id": {"type": "keyword"},
            "bbox": {"type": "float"},
            "bbox_page_idx": {"type": "integer"},
            "page_file_index": {"type": "integer"},
        }
    }
}


def build_async_elasticsearch(es_url: str) -> AsyncElasticsearch:
    """Build an async Elasticsearch client compatible with Elasticsearch 8.x."""
    return AsyncElasticsearch(es_url, headers=ES8_COMPAT_HEADERS)


async def ensure_es_index(es: AsyncElasticsearch, index: str) -> None:
    """Create the canonical Elasticsearch index when it does not exist."""
    if not await es.indices.exists(index=index):
        await es.indices.create(index=index, body=ES_INDEX_MAPPING)
