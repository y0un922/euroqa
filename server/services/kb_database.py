"""SQLite metadata store for logical knowledge-base groupings."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiosqlite

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS knowledge_bases (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    description TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS kb_documents (
    kb_id TEXT NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE,
    doc_id TEXT NOT NULL,
    file_name TEXT NOT NULL DEFAULT '',
    added_at TEXT NOT NULL,
    PRIMARY KEY (kb_id, doc_id)
);

CREATE INDEX IF NOT EXISTS idx_kb_documents_doc_id
    ON kb_documents(doc_id);
"""


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _row_dict(row: aiosqlite.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


class KBDatabase:
    """Small async SQLite store for knowledge-base metadata."""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._db: aiosqlite.Connection | None = None

    async def initialize(self) -> None:
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(self._db_path)
        self._db.row_factory = aiosqlite.Row
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._db.execute("PRAGMA foreign_keys=ON")
        await self._db.executescript(_SCHEMA_SQL)
        await self._db.commit()

    async def close(self) -> None:
        if self._db is None:
            return
        await self._db.close()
        self._db = None

    def _connection(self) -> aiosqlite.Connection:
        if self._db is None:
            raise RuntimeError("KBDatabase is not initialized")
        return self._db

    async def create_kb(self, name: str, description: str = "") -> dict[str, Any]:
        db = self._connection()
        now = _utc_iso()
        kb_id = str(uuid.uuid4())
        await db.execute(
            """
            INSERT INTO knowledge_bases (id, name, description, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (kb_id, name.strip(), description, now, now),
        )
        await db.commit()
        created = await self.get_kb(kb_id)
        if created is None:
            raise RuntimeError("created knowledge base could not be loaded")
        return created

    async def list_kbs(self) -> list[dict[str, Any]]:
        db = self._connection()
        cursor = await db.execute(
            """
            SELECT
                kb.id,
                kb.name,
                kb.description,
                kb.created_at,
                kb.updated_at,
                COUNT(kbd.doc_id) AS document_count
            FROM knowledge_bases AS kb
            LEFT JOIN kb_documents AS kbd ON kbd.kb_id = kb.id
            GROUP BY kb.id
            ORDER BY kb.updated_at DESC, kb.name ASC
            """
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def get_kb(self, kb_id: str) -> dict[str, Any] | None:
        db = self._connection()
        cursor = await db.execute(
            """
            SELECT
                kb.id,
                kb.name,
                kb.description,
                kb.created_at,
                kb.updated_at,
                COUNT(kbd.doc_id) AS document_count
            FROM knowledge_bases AS kb
            LEFT JOIN kb_documents AS kbd ON kbd.kb_id = kb.id
            WHERE kb.id = ?
            GROUP BY kb.id
            """,
            (kb_id,),
        )
        return _row_dict(await cursor.fetchone())

    async def update_kb(
        self,
        kb_id: str,
        *,
        name: str | None = None,
        description: str | None = None,
    ) -> dict[str, Any] | None:
        updates: list[str] = []
        values: list[Any] = []
        if name is not None:
            updates.append("name = ?")
            values.append(name.strip())
        if description is not None:
            updates.append("description = ?")
            values.append(description)
        if not updates:
            return await self.get_kb(kb_id)

        updates.append("updated_at = ?")
        values.append(_utc_iso())
        values.append(kb_id)
        db = self._connection()
        cursor = await db.execute(
            f"UPDATE knowledge_bases SET {', '.join(updates)} WHERE id = ?",
            values,
        )
        await db.commit()
        if cursor.rowcount == 0:
            return None
        return await self.get_kb(kb_id)

    async def delete_kb(self, kb_id: str) -> bool:
        db = self._connection()
        cursor = await db.execute("DELETE FROM knowledge_bases WHERE id = ?", (kb_id,))
        await db.commit()
        return cursor.rowcount > 0

    async def kb_exists(self, kb_id: str) -> bool:
        db = self._connection()
        cursor = await db.execute(
            "SELECT 1 FROM knowledge_bases WHERE id = ?",
            (kb_id,),
        )
        return await cursor.fetchone() is not None

    async def add_documents(self, kb_id: str, docs: list[tuple[str, str]]) -> int:
        if not docs:
            return 0
        db = self._connection()
        added_at = _utc_iso()
        before = db.total_changes
        await db.executemany(
            """
            INSERT OR IGNORE INTO kb_documents
                (kb_id, doc_id, file_name, added_at)
            VALUES (?, ?, ?, ?)
            """,
            [(kb_id, doc_id, file_name, added_at) for doc_id, file_name in docs],
        )
        changed = db.total_changes - before
        await db.execute(
            "UPDATE knowledge_bases SET updated_at = ? WHERE id = ?",
            (_utc_iso(), kb_id),
        )
        await db.commit()
        return changed

    async def remove_documents(self, kb_id: str, doc_ids: list[str]) -> int:
        if not doc_ids:
            return 0
        db = self._connection()
        before = db.total_changes
        await db.executemany(
            "DELETE FROM kb_documents WHERE kb_id = ? AND doc_id = ?",
            [(kb_id, doc_id) for doc_id in doc_ids],
        )
        changed = db.total_changes - before
        await db.execute(
            "UPDATE knowledge_bases SET updated_at = ? WHERE id = ?",
            (_utc_iso(), kb_id),
        )
        await db.commit()
        return changed

    async def list_documents(self, kb_id: str) -> list[dict[str, Any]]:
        db = self._connection()
        cursor = await db.execute(
            """
            SELECT doc_id, file_name, added_at
            FROM kb_documents
            WHERE kb_id = ?
            ORDER BY added_at DESC, file_name ASC
            """,
            (kb_id,),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def get_kb_doc_ids(self, kb_id: str) -> list[str]:
        return [row["doc_id"] for row in await self.list_documents(kb_id)]

    async def get_exclusive_doc_ids(self, kb_id: str) -> list[str]:
        db = self._connection()
        cursor = await db.execute(
            """
            SELECT current.doc_id
            FROM kb_documents AS current
            WHERE current.kb_id = ?
              AND NOT EXISTS (
                  SELECT 1
                  FROM kb_documents AS other
                  WHERE other.doc_id = current.doc_id
                    AND other.kb_id <> current.kb_id
              )
            ORDER BY current.doc_id ASC
            """,
            (kb_id,),
        )
        rows = await cursor.fetchall()
        return [str(row["doc_id"]) for row in rows]
