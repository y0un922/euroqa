from __future__ import annotations

import pytest

from server.api.v1.query import _resolve_kb_sources
from server.models.schemas import QueryRequest
from server.services.kb_database import KBDatabase


@pytest.mark.asyncio
async def test_resolve_kb_sources_returns_selected_document_ids(tmp_path):
    db = KBDatabase(str(tmp_path / "knowledge_bases.db"))
    await db.initialize()
    try:
        kb = await db.create_kb("Concrete")
        await db.add_documents(kb["id"], [("EN 1992:2004", "EN 1992.pdf")])

        sources = await _resolve_kb_sources(
            QueryRequest(question="材料分项系数是什么？", kbIds=[kb["id"]]),
            db,
        )

        assert sources == ["EN 1992:2004"]
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
