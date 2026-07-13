"""Deterministic diagnostics: CRec + unresolved_ref_rate (no judge)."""

from __future__ import annotations

import unicodedata
from typing import Any

MIN_EVIDENCE_QUOTE_CHARS = 20


def _normalize_text(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).split())


def _evidence_coverage(
    evidence_locators: list[dict[str, Any]],
    context_chunks: list[dict[str, Any]],
) -> tuple[set[str], set[str]]:
    context = [
        _normalize_text(str(chunk.get("content") or "")) for chunk in context_chunks
    ]
    found: set[str] = set()
    all_ids: set[str] = set()
    for locator in evidence_locators:
        evidence_id = str(locator.get("evidence_id") or "")
        quote = _normalize_text(str(locator.get("quote") or ""))
        if not evidence_id:
            continue
        all_ids.add(evidence_id)
        if len(quote) >= MIN_EVIDENCE_QUOTE_CHARS and any(
            quote in content for content in context
        ):
            found.add(evidence_id)
    return all_ids, found


def crec_score(
    evidence_locators: list[dict[str, Any]],
    context_chunks: list[dict[str, Any]],
) -> tuple[float | None, bool]:
    """CRec = fraction of exact gold evidence quotes present in actual C.

    Evidence is discovered independently from parsed Markdown, so matching uses
    normalized verbatim quotes rather than application index chunk IDs.
    """
    all_ids, found = _evidence_coverage(evidence_locators, context_chunks)
    if not all_ids:
        return None, False
    return len(found) / len(all_ids), True


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
    evidence_locators: list[dict[str, Any]],
    context_chunks: list[dict[str, Any]],
) -> list[str]:
    """Gold evidence locators whose exact quotes are absent from C."""
    all_ids, found = _evidence_coverage(evidence_locators, context_chunks)
    return sorted(all_ids - found)
