"""End-to-end metric aggregation: Faith, CitP + diagnostics + gates."""

from __future__ import annotations

from typing import Any, Iterable

from eval_methodology.mvp.metrics.diagnostics import (
    crec_score,
    retrieval_gap_ids,
    unresolved_ref_rate,
)
from eval_methodology.mvp.metrics.schemas import AggregateMetrics, PerQuestionMetrics
from eval_methodology.mvp.paths import MAX_JUDGE_DROP_RATE, MIN_EFFECTIVE_N


def per_question_from_parts(
    *,
    question_id: str,
    faith: float | None,
    citp: float | None,
    judge_dropped: bool,
    evidence_locators: list[dict[str, Any]] | None,
    context_chunk_ids: list[str],
    context_chunks: list[dict[str, Any]],
    unresolved_refs: list[str] | None,
    resolved_refs: list[str] | None,
    n_claims: int = 0,
    n_citations: int = 0,
    gold_claim_status: str = "",
    notes: str = "",
) -> PerQuestionMetrics:
    locators = list(evidence_locators or [])
    e_plus_list = [str(item.get("evidence_id") or "") for item in locators]
    # Full question drop nulls both hard metrics (defensive).
    if judge_dropped:
        faith = None
        citp = None
    crec, eligible = crec_score(locators, context_chunks)
    gaps = retrieval_gap_ids(locators, context_chunks)
    return PerQuestionMetrics(
        question_id=question_id,
        faith=faith,
        citp=citp,
        crec=crec,
        unresolved_ref_rate=unresolved_ref_rate(unresolved_refs, resolved_refs),
        judge_dropped=judge_dropped,
        crec_eligible=eligible,
        n_claims=n_claims,
        n_citations=n_citations,
        context_chunk_ids=list(context_chunk_ids),
        e_plus=e_plus_list,
        retrieval_gap_ids=gaps,
        gold_claim_status=gold_claim_status,
        notes=notes,
    )


def _mean(vals: Iterable[float | None]) -> tuple[float | None, int]:
    xs = [v for v in vals if v is not None]
    if not xs:
        return None, 0
    return sum(xs) / len(xs), len(xs)


def aggregate(per_q: list[PerQuestionMetrics]) -> AggregateMetrics:
    n = len(per_q)
    dropped = sum(1 for p in per_q if p.judge_dropped)
    drop_rate = (dropped / n) if n else 0.0

    # Only non-dropped questions contribute to hard-gate means.
    kept = [p for p in per_q if not p.judge_dropped]
    faith_mean, n_faith = _mean(p.faith for p in kept)
    citp_mean, n_citp = _mean(p.citp for p in kept)
    crec_vals = [p.crec for p in per_q if p.crec_eligible and p.crec is not None]
    crec_mean = sum(crec_vals) / len(crec_vals) if crec_vals else None
    urr_mean, _ = _mean(p.unresolved_ref_rate for p in per_q)

    effective = min(n_faith, n_citp) if n_faith and n_citp else max(n_faith, n_citp)
    degraded = False
    reasons: list[str] = []
    if effective < MIN_EFFECTIVE_N:
        degraded = True
        reasons.append(f"effective_n={effective} < {MIN_EFFECTIVE_N}")
    if drop_rate > MAX_JUDGE_DROP_RATE:
        degraded = True
        reasons.append(f"judge_drop_rate={drop_rate:.2%} > {MAX_JUDGE_DROP_RATE:.0%}")

    return AggregateMetrics(
        faith_mean=faith_mean,
        citp_mean=citp_mean,
        crec_mean=crec_mean,
        unresolved_ref_rate_mean=urr_mean,
        effective_n_faith=n_faith,
        effective_n_citp=n_citp,
        crec_eligible_n=len(crec_vals),
        judge_drop_rate=drop_rate,
        degraded_to_trend=degraded,
        degradation_reason="; ".join(reasons),
    )


def paired_series(
    baseline: list[PerQuestionMetrics],
    candidate: list[PerQuestionMetrics],
    metric: str,
) -> tuple[list[float], list[float], list[str]]:
    """Align on question ids where both sides have non-null metric values."""
    bmap = {p.question_id: p for p in baseline}
    cmap = {p.question_id: p for p in candidate}
    ids = sorted(set(bmap) & set(cmap))
    base_vals: list[float] = []
    cand_vals: list[float] = []
    used: list[str] = []
    for qid in ids:
        bv = getattr(bmap[qid], metric)
        cv = getattr(cmap[qid], metric)
        if bv is None or cv is None:
            continue
        base_vals.append(float(bv))
        cand_vals.append(float(cv))
        used.append(qid)
    return base_vals, cand_vals, used


def run_dict_from_stream_and_judge(
    *,
    question_id: str,
    stream_result: dict[str, Any],
    judge_result: Any,
    evidence_locators: list[dict[str, Any]] | None,
    gold_claim_status: str = "",
) -> PerQuestionMetrics:
    return per_question_from_parts(
        question_id=question_id,
        faith=judge_result.faith,
        citp=judge_result.citp,
        judge_dropped=judge_result.dropped,
        evidence_locators=evidence_locators,
        context_chunk_ids=stream_result.get("context_chunk_ids") or [],
        context_chunks=stream_result.get("context_chunks") or [],
        unresolved_refs=stream_result.get("unresolved_refs"),
        resolved_refs=stream_result.get("resolved_refs"),
        n_claims=len(judge_result.units.claims),
        n_citations=len(judge_result.units.citations),
        gold_claim_status=gold_claim_status,
        notes=judge_result.drop_reason,
    )
