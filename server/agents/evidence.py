from __future__ import annotations

from dataclasses import dataclass, field

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
    tool_trace: list[dict] = field(default_factory=list)
    question_type: str | None = None
    engineering_context: object | None = None
    intent_label: str | None = None

    def add_retrieval(self, result: RetrievalResult) -> None:
        """Merge one retrieval result into the bundle, deduplicating by chunk_id."""
        self.chunks = _merge_chunks(self.chunks, result.chunks)
        self.parent_chunks = _merge_chunks(self.parent_chunks, result.parent_chunks)
        self.guide_chunks = _merge_chunks(self.guide_chunks, result.guide_chunks)
        self.guide_example_chunks = _merge_chunks(
            self.guide_example_chunks,
            result.guide_example_chunks,
        )
        self.ref_chunks = _merge_chunks(self.ref_chunks, result.ref_chunks)
        self.scores.extend(result.scores)
        self.groundedness = _stronger_groundedness(
            self.groundedness,
            result.groundedness,
        )
        self.resolved_refs = _merge_strings(self.resolved_refs, result.resolved_refs)
        self.unresolved_refs = _merge_strings(
            self.unresolved_refs,
            result.unresolved_refs,
        )

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


def _merge_chunks(existing: list[Chunk], incoming: list[Chunk]) -> list[Chunk]:
    seen = {chunk.chunk_id for chunk in existing}
    merged = list(existing)
    for chunk in incoming:
        if chunk.chunk_id in seen:
            continue
        merged.append(chunk)
        seen.add(chunk.chunk_id)
    return merged


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
