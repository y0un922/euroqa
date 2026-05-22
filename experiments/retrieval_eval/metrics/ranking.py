"""Ranking metrics for retrieval-only evaluation."""

from __future__ import annotations

import math
from typing import Any

from experiments.retrieval_eval.dataset.schema import ExpectedDoc
from experiments.retrieval_eval.metrics.recall import chunk_matches_section


def mrr_section(retrieved_chunks: list[Any], expected_sections: list[str]) -> float:
    """Return reciprocal rank of the first chunk matching an expected section."""
    expected = _expected_docs_from_sections(expected_sections)
    if not expected:
        return 1.0

    for rank, chunk in enumerate(retrieved_chunks, start=1):
        if any(chunk_matches_section(chunk, section) for section in expected_sections):
            return 1.0 / rank
    return 0.0


def ndcg_at_k(retrieved_chunks: list[Any], expected_sections: list[str], k: int) -> float:
    """Compute binary-relevance NDCG@k for expected section hits."""
    if not expected_sections:
        return 1.0
    if k <= 0:
        return 0.0

    gains: list[int] = []
    seen_sections: set[str] = set()
    for chunk in retrieved_chunks[:k]:
        matched = None
        for section in expected_sections:
            if section not in seen_sections and chunk_matches_section(chunk, section):
                matched = section
                break
        if matched is None:
            gains.append(0)
        else:
            gains.append(1)
            seen_sections.add(matched)

    dcg = _dcg(gains)
    ideal_hits = min(len(set(expected_sections)), k)
    idcg = _dcg([1] * ideal_hits)
    return dcg / idcg if idcg else 1.0


def _dcg(gains: list[int]) -> float:
    return sum(gain / math.log2(idx + 2) for idx, gain in enumerate(gains))


def _expected_docs_from_sections(sections: list[str]) -> list[ExpectedDoc]:
    return [ExpectedDoc(doc="", sections=list(sections))] if sections else []
