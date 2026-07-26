from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from server.core.retrieval import RetrievalResult
from server.models.schemas import Chunk


@dataclass
class EvidenceBundle:
    """Evidence accumulated across agent tool calls."""

    chunks: list[Chunk] = field(default_factory=list)
    parent_chunks: list[Chunk] = field(default_factory=list)
    guide_chunks: list[Chunk] = field(default_factory=list)
    guide_example_chunks: list[Chunk] = field(default_factory=list)
    ref_chunks: list[Chunk] = field(default_factory=list)
    scores: list[float] = field(default_factory=list)
    glossary_hits: dict[str, str] = field(default_factory=dict)
    groundedness: str = "not_grounded"
    resolved_refs: list[str] = field(default_factory=list)
    unresolved_refs: list[str] = field(default_factory=list)
    slot_results: list[dict[str, Any]] = field(default_factory=list)
    unresolved_slots: list[str] = field(default_factory=list)
    retrieval_attempts: list[dict[str, Any]] = field(default_factory=list)
    ref_ids_by_chunk_id: dict[str, str] = field(default_factory=dict)
    tool_trace: list[dict] = field(default_factory=list)
    outline: dict[str, Any] | None = None
    question_type: str | None = None
    engineering_context: object | None = None
    intent_label: str | None = None

    def add_retrieval(
        self,
        result: RetrievalResult,
        *,
        query: str | None = None,
    ) -> None:
        """Merge one retrieval result into the bundle, deduplicating by chunk_id."""
        self.chunks, self.scores = _merge_chunks_and_scores(
            self.chunks,
            self.scores,
            result.chunks,
            result.scores,
        )
        self.parent_chunks = _merge_chunks(self.parent_chunks, result.parent_chunks)
        self.guide_chunks = _merge_chunks(self.guide_chunks, result.guide_chunks)
        self.guide_example_chunks = _merge_chunks(
            self.guide_example_chunks,
            result.guide_example_chunks,
        )
        self.ref_chunks = _merge_chunks(self.ref_chunks, result.ref_chunks)
        self.groundedness = _stronger_groundedness(
            self.groundedness,
            result.groundedness,
        )
        self.resolved_refs = _merge_strings(self.resolved_refs, result.resolved_refs)
        self.unresolved_refs = _merge_strings(
            self.unresolved_refs,
            result.unresolved_refs,
        )
        if query is not None:
            max_score = max(result.scores) if result.scores else None
            self.retrieval_attempts.append(
                {
                    "query": query,
                    "chunk_ids": [chunk.chunk_id for chunk in result.chunks],
                    "chunk_count": len(result.chunks),
                    "max_score": max_score,
                    "groundedness": result.groundedness,
                }
            )
        self.ensure_ref_ids(self.citable_chunks())

    def add_glossary_hit(self, term: str, definition: str) -> None:
        """Record a glossary hit from the lookup tool."""
        normalized = term.strip()
        if normalized:
            self.glossary_hits[normalized] = definition

    @property
    def is_empty(self) -> bool:
        return not self.chunks

    @property
    def has_rag_evidence(self) -> bool:
        """Return whether the bundle contains evidence for RAG generation."""
        return bool(
            self.chunks
            or self.ref_chunks
            or self.guide_chunks
            or self.guide_example_chunks
        )

    @property
    def chunk_count(self) -> int:
        return len(self.chunks)

    def citable_chunks(self) -> list[Chunk]:
        """Return citable chunks: primary chunks by rerank score, then supplements."""
        scored = sorted(
            zip(self.chunks, self.scores, strict=False),
            key=lambda pair: pair[1],
            reverse=True,
        )
        primary = [chunk for chunk, _score in scored]
        # 防御：chunks 多于 scores 时保留未计分的尾部
        primary.extend(self.chunks[len(self.scores) :])
        return _merge_chunks(
            [],
            [
                *primary,
                *self.parent_chunks,
                *self.ref_chunks,
                *self.guide_chunks,
                *self.guide_example_chunks,
            ],
        )

    def ensure_ref_ids(self, chunks: list[Chunk]) -> None:
        """Assign stable Ref-N labels to chunks that may be exposed to the agent."""
        for chunk in chunks:
            if chunk.chunk_id in self.ref_ids_by_chunk_id:
                continue
            self.ref_ids_by_chunk_id[chunk.chunk_id] = (
                f"Ref-{len(self.ref_ids_by_chunk_id) + 1}"
            )

    def ref_label_for(self, chunk: Chunk) -> str:
        """Return a stable citation label for a chunk, assigning one if needed."""
        self.ensure_ref_ids([chunk])
        return self.ref_ids_by_chunk_id[chunk.chunk_id]


def _merge_chunks(existing: list[Chunk], incoming: list[Chunk]) -> list[Chunk]:
    seen = {chunk.chunk_id for chunk in existing}
    merged = list(existing)
    for chunk in incoming:
        if chunk.chunk_id in seen:
            continue
        merged.append(chunk)
        seen.add(chunk.chunk_id)
    return merged


def _merge_chunks_and_scores(
    existing_chunks: list[Chunk],
    existing_scores: list[float],
    incoming_chunks: list[Chunk],
    incoming_scores: list[float],
) -> tuple[list[Chunk], list[float]]:
    """Merge chunks while keeping scores aligned with newly retained chunks."""
    seen = {chunk.chunk_id for chunk in existing_chunks}
    merged_chunks = list(existing_chunks)
    merged_scores = list(existing_scores)
    for index, chunk in enumerate(incoming_chunks):
        if chunk.chunk_id in seen:
            continue
        seen.add(chunk.chunk_id)
        merged_chunks.append(chunk)
        if index < len(incoming_scores):
            merged_scores.append(incoming_scores[index])
        else:
            merged_scores.append(0.0)
    return merged_chunks, merged_scores


def _merge_strings(existing: list[str], incoming: list[str]) -> list[str]:
    seen = set(existing)
    merged = list(existing)
    for item in incoming:
        if item in seen:
            continue
        merged.append(item)
        seen.add(item)
    return merged


def _stronger_groundedness(current: str, incoming: str) -> str:
    rank = {"not_grounded": 0, "partial": 1, "grounded": 2}
    return incoming if rank.get(incoming, 0) > rank.get(current, 0) else current
