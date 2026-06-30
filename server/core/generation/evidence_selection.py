"""Select a compact, citeable evidence set for answer generation."""

from __future__ import annotations

from dataclasses import dataclass

from server.config import ServerConfig
from server.core.evidence_guard import (
    EvidenceRequirement,
    chunk_matches_requirement,
)
from server.core.generation.tokens import _count_tokens
from server.models.schemas import Chunk, ElementType

_MAX_PROTECTED_CHUNKS_PER_REQUIREMENT = 1


@dataclass
class SelectedEvidence:
    """Evidence lists after generation-budget selection."""

    chunks: list[Chunk]
    parent_chunks: list[Chunk]
    ref_chunks: list[Chunk]
    guide_chunks: list[Chunk]
    guide_example_chunks: list[Chunk]
    scores: list[float]


@dataclass
class _Candidate:
    chunk: Chunk
    bucket: str
    score: float | None
    priority: int
    order: int


def select_generation_evidence(
    *,
    chunks: list[Chunk],
    parent_chunks: list[Chunk],
    ref_chunks: list[Chunk] | None = None,
    guide_chunks: list[Chunk] | None = None,
    guide_example_chunks: list[Chunk] | None = None,
    scores: list[float] | None = None,
    required_evidence: list[EvidenceRequirement] | None = None,
    config: ServerConfig | None = None,
) -> SelectedEvidence:
    """Return compact evidence while preserving required matches and citation order."""
    cfg = config or ServerConfig()
    budget = max(0, int(cfg.generation_context_token_budget or 0))
    if budget <= 0:
        return SelectedEvidence(
            chunks=list(chunks),
            parent_chunks=list(parent_chunks),
            ref_chunks=list(ref_chunks or []),
            guide_chunks=list(guide_chunks or []),
            guide_example_chunks=list(guide_example_chunks or []),
            scores=list(scores or []),
        )

    candidates = _build_candidates(
        chunks=chunks,
        parent_chunks=parent_chunks,
        ref_chunks=ref_chunks or [],
        guide_chunks=guide_chunks or [],
        guide_example_chunks=guide_example_chunks or [],
        scores=scores or [],
        required_evidence=required_evidence or [],
    )
    selected: list[_Candidate] = []
    used_ids: set[str] = set()
    used_tokens = 0
    for candidate in candidates:
        if candidate.chunk.chunk_id in used_ids:
            continue
        token_cost = _chunk_token_cost(candidate.chunk, cfg)
        required_match = candidate.priority == 0
        if not required_match and used_tokens + token_cost > budget:
            continue
        selected.append(candidate)
        used_ids.add(candidate.chunk.chunk_id)
        used_tokens += token_cost

    return _candidates_to_selected(
        selected,
        chunks,
        parent_chunks,
        ref_chunks or [],
        guide_chunks or [],
        guide_example_chunks or [],
        scores or [],
    )


def _build_candidates(
    *,
    chunks: list[Chunk],
    parent_chunks: list[Chunk],
    ref_chunks: list[Chunk],
    guide_chunks: list[Chunk],
    guide_example_chunks: list[Chunk],
    scores: list[float],
    required_evidence: list[EvidenceRequirement],
) -> list[_Candidate]:
    candidates: list[_Candidate] = []
    order = 0
    main_score_by_id = {
        chunk.chunk_id: scores[index] if index < len(scores) else None
        for index, chunk in enumerate(chunks)
    }
    for bucket, bucket_chunks in (
        ("chunks", chunks),
        ("ref_chunks", ref_chunks),
        ("parent_chunks", parent_chunks),
        ("guide_chunks", guide_chunks),
        ("guide_example_chunks", guide_example_chunks),
    ):
        for chunk in bucket_chunks:
            candidates.append(
                _Candidate(
                    chunk=chunk,
                    bucket=bucket,
                    score=main_score_by_id.get(chunk.chunk_id),
                    priority=99,
                    order=order,
                )
            )
            order += 1
    protected_required_ids = _select_protected_required_ids(
        candidates,
        required_evidence,
    )
    for candidate in candidates:
        candidate.priority = _priority_for_chunk(
            candidate.bucket,
            candidate.chunk,
            protected_required_ids,
        )
    return sorted(candidates, key=_candidate_sort_key)


def _priority_for_chunk(
    bucket: str,
    chunk: Chunk,
    protected_required_ids: set[str],
) -> int:
    if chunk.chunk_id in protected_required_ids:
        return 0
    if chunk.metadata.object_label or chunk.metadata.clause_ids:
        return 1
    if bucket == "chunks":
        return 2
    if bucket == "ref_chunks":
        return 3
    if bucket == "parent_chunks":
        return 4
    if bucket == "guide_chunks":
        return 5
    return 6


def _candidate_sort_key(candidate: _Candidate) -> tuple[int, int, float, int]:
    type_rank = 0 if candidate.chunk.metadata.element_type in {
        ElementType.TABLE,
        ElementType.FORMULA,
    } else 1
    score = candidate.score if candidate.score is not None else -1.0
    return (candidate.priority, type_rank, -score, candidate.order)


def _select_protected_required_ids(
    candidates: list[_Candidate],
    required_evidence: list[EvidenceRequirement],
) -> set[str]:
    selected_ids: set[str] = set()
    for requirement in required_evidence:
        if not requirement.required:
            continue
        matches = [
            candidate
            for candidate in candidates
            if chunk_matches_requirement(candidate.chunk, requirement)
        ]
        for candidate in sorted(matches, key=_required_candidate_sort_key)[
            :_MAX_PROTECTED_CHUNKS_PER_REQUIREMENT
        ]:
            selected_ids.add(candidate.chunk.chunk_id)
    return selected_ids


def _required_candidate_sort_key(candidate: _Candidate) -> tuple[int, int, float, int]:
    type_rank = 0 if candidate.chunk.metadata.element_type in {
        ElementType.TABLE,
        ElementType.FORMULA,
    } else 1
    bucket_rank = {
        "chunks": 0,
        "ref_chunks": 1,
        "parent_chunks": 2,
        "guide_chunks": 3,
        "guide_example_chunks": 4,
    }.get(candidate.bucket, 9)
    score = candidate.score if candidate.score is not None else -1.0
    return (type_rank, bucket_rank, -score, candidate.order)


def _chunk_token_cost(chunk: Chunk, config: ServerConfig) -> int:
    token_count, _is_estimate = _count_tokens(chunk.content, config)
    return max(1, token_count)


def _candidates_to_selected(
    selected: list[_Candidate],
    original_chunks: list[Chunk],
    original_parent_chunks: list[Chunk],
    original_ref_chunks: list[Chunk],
    original_guide_chunks: list[Chunk],
    original_guide_example_chunks: list[Chunk],
    original_scores: list[float],
) -> SelectedEvidence:
    selected_ids = {candidate.chunk.chunk_id for candidate in selected}
    filtered_scores = [
        original_scores[index]
        for index, chunk in enumerate(original_chunks)
        if index < len(original_scores)
        and chunk.chunk_id in selected_ids
    ]
    return SelectedEvidence(
        chunks=_filter_selected(original_chunks, selected_ids),
        parent_chunks=_filter_selected(original_parent_chunks, selected_ids),
        ref_chunks=_filter_selected(original_ref_chunks, selected_ids),
        guide_chunks=_filter_selected(original_guide_chunks, selected_ids),
        guide_example_chunks=_filter_selected(
            original_guide_example_chunks,
            selected_ids,
        ),
        scores=filtered_scores,
    )


def _filter_selected(chunks: list[Chunk], selected_ids: set[str]) -> list[Chunk]:
    return [chunk for chunk in chunks if chunk.chunk_id in selected_ids]
