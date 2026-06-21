import pytest

from server.services.kb_database import KBDatabase


@pytest.mark.asyncio
async def test_kb_database_tracks_many_to_many_documents(tmp_path):
    db = KBDatabase(str(tmp_path / "knowledge_bases.db"))
    await db.initialize()
    try:
        first = await db.create_kb("Project A", "first")
        second = await db.create_kb("Project B", "second")

        assert await db.add_documents(
            first["id"],
            [("EN_1992", "EN 1992.pdf"), ("Guide_1992", "Guide.pdf")],
        ) == 2
        assert await db.add_documents(second["id"], [("EN_1992", "EN 1992.pdf")]) == 1
        assert await db.add_documents(first["id"], [("EN_1992", "EN 1992.pdf")]) == 0

        first_docs = await db.get_kb_doc_ids(first["id"])
        assert set(first_docs) == {"EN_1992", "Guide_1992"}
        assert await db.get_exclusive_doc_ids(first["id"]) == ["Guide_1992"]

        assert await db.remove_documents(first["id"], ["EN_1992"]) == 1
        assert await db.get_kb_doc_ids(first["id"]) == ["Guide_1992"]

        listed = await db.list_kbs()
        counts = {row["id"]: row["document_count"] for row in listed}
        assert counts[first["id"]] == 1
        assert counts[second["id"]] == 1
    finally:
        await db.close()
