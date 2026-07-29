from __future__ import annotations

import pytest
from fastapi import HTTPException

from server.api.v1.query import _resolve_query_sources
from server.models.schemas import QueryRequest
from server.services.kb_database import KBDatabase


class _FakeRetriever:
    def __init__(self, sources: list[str]) -> None:
        self.config = type("Config", (), {"es_index": "chunks"})()
        self._sources = sources

    async def _get_es(self):
        return self

    async def search(self, index, body):
        return {
            "aggregations": {
                "sources": {
                    "buckets": [
                        {"key": source, "doc_count": 1} for source in self._sources
                    ]
                }
            }
        }


@pytest.mark.asyncio
async def test_resolve_query_sources_uses_explicit_doc_ids(tmp_path):
    db = KBDatabase(str(tmp_path / "knowledge_bases.db"))
    await db.initialize()
    try:
        sources = await _resolve_query_sources(
            QueryRequest(
                question="材料分项系数是什么？",
                docIds=["EN1992-1-1_2004", "missing_doc"],
            ),
            db,
            _FakeRetriever(["EN1992-1-1 2004", "DG EN1990"]),
            require_doc_ids=True,
        )
        assert sources == ["EN1992-1-1 2004"]
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_resolve_query_sources_requires_doc_ids_for_stream(tmp_path):
    db = KBDatabase(str(tmp_path / "knowledge_bases.db"))
    await db.initialize()
    try:
        with pytest.raises(HTTPException) as exc_info:
            await _resolve_query_sources(
                QueryRequest(question="hello"),
                db,
                None,
                require_doc_ids=True,
            )
        assert exc_info.value.status_code == 400
        assert "docIds" in str(exc_info.value.detail)
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_resolve_query_sources_internal_allows_empty_doc_ids(tmp_path):
    db = KBDatabase(str(tmp_path / "knowledge_bases.db"))
    await db.initialize()
    try:
        sources = await _resolve_query_sources(
            QueryRequest(question="hello"),
            db,
            None,
            require_doc_ids=False,
        )
        assert sources is None
    finally:
        await db.close()
