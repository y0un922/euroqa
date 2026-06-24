# Database Guidelines

> Database patterns and conventions for this project.

---

## Overview

Knowledge-base management uses a small local SQLite metadata store at
`ServerConfig.knowledge_base_db_path`. It stores logical KB groups and document
membership only. Indexed retrieval data remains in Milvus and Elasticsearch.

---

## Query Patterns

Keep KB query scoping as a source filter over existing indexed `source` values.
Do not add KB-only fields to the Milvus schema unless the full indexing pipeline
is intentionally migrated and rebuilt.

---

## Migrations

The KB SQLite schema is created idempotently during application startup. Schema
changes should remain backward-compatible or include an explicit migration path.

---

## Naming Conventions

Use snake_case table and column names. KB tables currently use
`knowledge_bases` and `kb_documents`.

---

## Common Mistakes

Do not import document-type metadata or expanded Milvus fields when adding KB
management to the 2026-06-13 baseline. That baseline expects the original
Milvus schema: `chunk_id`, `embedding`, `source`, and `element_type`.
