from __future__ import annotations

import pytest

from server.api.v1.query import _resolve_kb_sources
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
                        {"key": source, "doc_count": 1}
                        for source in self._sources
                    ]
                }
            }
        }


@pytest.mark.asyncio
async def test_resolve_kb_sources_uses_indexed_source_names(tmp_path):
    db = KBDatabase(str(tmp_path / "knowledge_bases.db"))
    await db.initialize()
    try:
        kb = await db.create_kb("Concrete")
        await db.add_documents(kb["id"], [("EN1992-1-1_2004", "EN 1992.pdf")])

        sources = await _resolve_kb_sources(
            QueryRequest(question="材料分项系数是什么？", kbIds=[kb["id"]]),
            db,
            _FakeRetriever(["EN1992-1-1 2004", "DG EN1990"]),
        )

        assert sources == ["EN1992-1-1 2004"]
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_resolve_kb_sources_falls_back_to_doc_id_aliases(tmp_path):
    db = KBDatabase(str(tmp_path / "knowledge_bases.db"))
    await db.initialize()
    try:
        kb = await db.create_kb("Concrete")
        await db.add_documents(kb["id"], [("EN1992-1-1_2004", "EN 1992.pdf")])

        sources = await _resolve_kb_sources(
            QueryRequest(question="材料分项系数是什么？", kbIds=[kb["id"]]),
            db,
            _FakeRetriever([]),
        )

        assert "EN1992-1-1_2004" in sources
        assert "EN1992-1-1 2004" in sources
        assert "EN1992 1 1 2004" in sources
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_resolve_kb_sources_matches_double_underscore_doc_id_to_indexed_source(
    tmp_path,
):
    db = KBDatabase(str(tmp_path / "knowledge_bases.db"))
    await db.initialize()
    try:
        kb = await db.create_kb("Design guide")
        await db.add_documents(
            kb["id"],
            [("DG_EN1992-1-1__-1-2", "DG EN1992.pdf")],
        )

        sources = await _resolve_kb_sources(
            QueryRequest(question="材料分项系数是什么？", kbIds=[kb["id"]]),
            db,
            _FakeRetriever(["DG EN1992-1-1  -1-2", "DG EN1990"]),
        )

        assert sources == ["DG EN1992-1-1  -1-2"]
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_resolve_kb_sources_uses_empty_sentinel_for_empty_scope(tmp_path):
    db = KBDatabase(str(tmp_path / "knowledge_bases.db"))
    await db.initialize()
    try:
        kb = await db.create_kb("Empty")

        sources = await _resolve_kb_sources(
            QueryRequest(question="材料分项系数是什么？", kbIds=[kb["id"]]),
            db,
        )

        assert sources == ["__kb_scope_no_documents__"]
    finally:
        await db.close()
