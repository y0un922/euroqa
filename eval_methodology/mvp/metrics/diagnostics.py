"""Deterministic diagnostics: CRec + unresolved_ref_rate (no judge)."""

from __future__ import annotations

from typing import Any


def crec_score(
    e_plus: list[str] | set[str],
    context_chunk_ids: list[str] | set[str],
) -> tuple[float | None, bool]:
    """CRec = |E⁺ ∩ C| / |E⁺|.

    Returns (score, eligible). corpus_gap items with empty E⁺ are ineligible
    and must not enter the CRec denominator (MVP_PLAN §E.2).
    """
    e = set(e_plus or [])
    if not e:
        return None, False
    c = set(context_chunk_ids or [])
    return len(e & c) / len(e), True


def unresolved_ref_rate(
    unresolved_refs: list[str] | None,
    resolved_refs: list[str] | None = None,
) -> float:
    """Fraction of required refs left unresolved.

    If no refs were required, rate is 0.0 (no L4 gap signal).
    """
    unresolved = list(unresolved_refs or [])
    resolved = list(resolved_refs or [])
    denom = len(unresolved) + len(resolved)
    if denom == 0:
        return 0.0
    return len(unresolved) / denom


def mean_unresolved_ref_rate(results: list[dict[str, Any]]) -> float:
    if not results:
        return 0.0
    rates = [
        unresolved_ref_rate(r.get("unresolved_refs"), r.get("resolved_refs"))
        for r in results
    ]
    return sum(rates) / len(rates)


def retrieval_gap_ids(
    e_plus: list[str],
    context_chunk_ids: list[str],
) -> list[str]:
    """E⁺ chunks missing from C — counted by CRec as misses."""
    c = set(context_chunk_ids or [])
    return sorted(eid for eid in e_plus if eid not in c)
