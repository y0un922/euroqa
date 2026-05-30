from __future__ import annotations

from typing import Any

from server.config import ServerConfig
from server.core.generation.sources import (
    _resolve_chunk_display_title,
    _resolve_document_id,
)
from server.models.schemas import Chunk, RetrievalContext


def _build_retrieval_context(
    chunks: list[Chunk],
    parent_chunks: list[Chunk],
    guide_chunks: list[Chunk] | None = None,
    guide_example_chunks: list[Chunk] | None = None,
    ref_chunks: list[Chunk] | None = None,
    scores: list[float] | None = None,
    resolved_refs: list[str] | None = None,
    unresolved_refs: list[str] | None = None,
    config: ServerConfig | None = None,
) -> RetrievalContext:
    """Build the export-ready retrieval context snapshot for one answer turn."""
    chunk_items = [
        _build_retrieval_context_entry(
            chunk,
            score=scores[index] if scores and index < len(scores) else None,
            config=config,
        )
        for index, chunk in enumerate(chunks)
    ]
    parent_chunk_items = [
        _build_retrieval_context_entry(chunk, config=config) for chunk in parent_chunks
    ]
    guide_chunk_items = [
        _build_retrieval_context_entry(chunk, config=config)
        for chunk in (guide_chunks or [])
    ]
    guide_example_chunk_items = [
        _build_retrieval_context_entry(chunk, config=config)
        for chunk in (guide_example_chunks or [])
    ]
    ref_chunk_items = [
        _build_retrieval_context_entry(chunk, config=config)
        for chunk in (ref_chunks or [])
    ]
    return RetrievalContext(
        chunks=chunk_items,
        parent_chunks=parent_chunk_items,
        guide_chunks=guide_chunk_items,
        guide_example_chunks=guide_example_chunk_items,
        ref_chunks=ref_chunk_items,
        resolved_refs=list(resolved_refs or []),
        unresolved_refs=list(unresolved_refs or []),
    )


def _build_retrieval_context_entry(
    chunk: Chunk,
    score: float | None = None,
    config: ServerConfig | None = None,
) -> dict[str, Any]:
    """Build a frontend-exportable retrieval snapshot item from a chunk."""
    meta = chunk.metadata
    document_id = _resolve_document_id(chunk)
    display_title = _resolve_chunk_display_title(chunk, config, document_id)
    entry: dict[str, Any] = {
        "chunk_id": chunk.chunk_id,
        "document_id": document_id,
        "file": meta.source,
        "title": display_title,
        "display_title": display_title,
        "section": " > ".join(meta.section_path),
        "page": str(meta.page_numbers[0]) if meta.page_numbers else "",
        "clause": ", ".join(meta.clause_ids[:2]) if meta.clause_ids else "",
        "content": chunk.content,
    }
    if score is not None:
        entry["score"] = score
    return entry


def _dedupe_chunks_by_id(chunks: list[Chunk] | None) -> list[Chunk]:
    """Return chunks with duplicate chunk_id entries removed, preserving order."""
    deduped: list[Chunk] = []
    seen: set[str] = set()
    for chunk in chunks or []:
        if chunk.chunk_id in seen:
            continue
        seen.add(chunk.chunk_id)
        deduped.append(chunk)
    return deduped


def _dedupe_chunks_and_scores(
    chunks: list[Chunk],
    scores: list[float] | None,
) -> tuple[list[Chunk], list[float] | None]:
    """Deduplicate chunks while keeping the first matching score aligned."""
    deduped_chunks: list[Chunk] = []
    deduped_scores: list[float] = []
    seen: set[str] = set()
    if scores is None:
        for chunk in chunks:
            if chunk.chunk_id in seen:
                continue
            seen.add(chunk.chunk_id)
            deduped_chunks.append(chunk)
        return deduped_chunks, None

    score_values = list(scores or [])

    for index, chunk in enumerate(chunks):
        if chunk.chunk_id in seen:
            continue
        seen.add(chunk.chunk_id)
        deduped_chunks.append(chunk)
        deduped_scores.append(score_values[index] if index < len(score_values) else 0.0)
    return deduped_chunks, deduped_scores
