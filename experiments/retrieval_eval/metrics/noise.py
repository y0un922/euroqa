"""Noise and direct-reference metrics."""

from __future__ import annotations

from typing import Any

from experiments.retrieval_eval.metrics.recall import normalize_for_text_match


def noise_intrusion_rate(retrieved_chunks: list[Any], must_not_include: list[str]) -> float:
    """Return fraction of retrieved chunks containing any forbidden string."""
    if not retrieved_chunks:
        return 0.0
    forbidden = [normalize_for_text_match(term) for term in must_not_include if str(term or "").strip()]
    if not forbidden:
        return 0.0

    noisy = 0
    for chunk in retrieved_chunks:
        text = _chunk_search_text(chunk)
        if any(term and term in text for term in forbidden):
            noisy += 1
    return noisy / len(retrieved_chunks)


def direct_ref_resolution_rate(result: Any, expected_direct_refs: list[str]) -> float:
    """Return fraction of expected table/figure/equation refs resolved by retrieval."""
    refs = [ref for ref in expected_direct_refs if str(ref or "").strip()]
    if not refs:
        return 1.0

    resolved_text = " ".join(
        [
            " ".join(getattr(result, "resolved_refs", []) or []),
            " ".join(_chunk_ref_text(chunk) for chunk in getattr(result, "ref_chunks", []) or []),
            " ".join(_chunk_ref_text(chunk) for chunk in getattr(result, "chunks", []) or []),
        ]
    )
    normalized = normalize_for_text_match(resolved_text)
    compact = normalized.replace(" ", "")

    hits = 0
    for ref in refs:
        candidate = normalize_for_text_match(ref)
        if candidate in normalized or candidate.replace(" ", "") in compact:
            hits += 1
    return hits / len(refs)


def _chunk_search_text(chunk: Any) -> str:
    return normalize_for_text_match(
        " ".join(
            [
                getattr(chunk, "content", "") or "",
                getattr(chunk, "embedding_text", "") or "",
                _chunk_ref_text(chunk),
            ]
        )
    )


def _chunk_ref_text(chunk: Any) -> str:
    meta = getattr(chunk, "metadata", None)
    if meta is None:
        return ""
    values = [
        getattr(meta, "object_label", "") or "",
        getattr(meta, "object_id", "") or "",
        " ".join(getattr(meta, "object_aliases", []) or []),
        " ".join(getattr(meta, "ref_labels", []) or []),
    ]
    return " ".join(values)
