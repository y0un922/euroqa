from __future__ import annotations

import pytest

from server.services.kb_database import KBDatabase


@pytest.mark.asyncio
async def test_kb_database_tracks_documents_and_exclusive_membership(tmp_path):
    db = KBDatabase(str(tmp_path / "knowledge_bases.db"))
    await db.initialize()
    try:
        first = await db.create_kb("Eurocode", "core standards")
        second = await db.create_kb("Concrete")

        assert first["document_count"] == 0

        await db.add_documents(
            first["id"],
            [("EN 1990:2002", "EN 1990.pdf"), ("EN 1992:2004", "EN 1992.pdf")],
        )
        await db.add_documents(second["id"], [("EN 1992:2004", "EN 1992.pdf")])

        assert await db.get_doc_ids_for_kbs([first["id"]]) == [
            "EN 1990:2002",
            "EN 1992:2004",
        ]
        assert await db.get_exclusive_doc_ids(first["id"]) == ["EN 1990:2002"]

        await db.remove_document_everywhere("EN 1992:2004")

        assert await db.get_doc_ids_for_kbs([first["id"], second["id"]]) == [
            "EN 1990:2002"
        ]
    finally:
        await db.close()
