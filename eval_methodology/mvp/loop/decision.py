"""Bottleneck selection, candidate precheck, and three-state A/B decisions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Sequence

from eval_methodology.mvp.metrics.bootstrap import BootstrapCI, paired_bootstrap_ci
from eval_methodology.mvp.paths import DEFAULT_DELTA, DEFAULT_EPSILON

DecisionState = Literal["accept", "reject", "inconclusive"]
Stage = Literal["L1", "L2", "L3", "L4", "L5", "ops", "unknown"]

FAITH_LOW = 0.85
CITP_LOW = 0.80
CREC_LOW = 0.70
UNRESOLVED_REF_HIGH = 0.15


@dataclass(frozen=True)
class MetricSnapshot:
    """Aggregate metrics used for bottleneck selection."""

    faith: float | None = None
    citp: float | None = None
    crec: float | None = None
    unresolved_ref_rate: float | None = None
    effective_n: int = 0
    judge_fail_rate: float = 0.0
    crec_eligible_n: int = 0
    degraded_to_trend: bool = False

    @classmethod
    def from_aggregate(cls, aggregate: dict[str, Any]) -> MetricSnapshot:
        """Build a snapshot from serialized aggregate metrics."""
        n_faith = int(aggregate.get("effective_n_faith") or 0)
        n_citp = int(aggregate.get("effective_n_citp") or 0)
        effective = min(n_faith, n_citp) if n_faith and n_citp else max(n_faith, n_citp)
        return cls(
            faith=aggregate.get("faith_mean"),
            citp=aggregate.get("citp_mean"),
            crec=aggregate.get("crec_mean"),
            unresolved_ref_rate=aggregate.get("unresolved_ref_rate_mean"),
            effective_n=effective,
            judge_fail_rate=float(aggregate.get("judge_fail_rate") or 0.0),
            crec_eligible_n=int(aggregate.get("crec_eligible_n") or 0),
            degraded_to_trend=bool(aggregate.get("degraded_to_trend")),
        )


@dataclass
class BottleneckResult:
    stage: Stage
    reason: str
    metric_signals: dict[str, Any] = field(default_factory=dict)


@dataclass
class CandidatePick:
    action_id: str
    stage: Stage
    config_knobs: dict[str, Any]
    reason: str


@dataclass
class PrecheckResult:
    ok: bool
    points_to_l4: bool
    context_diff_n: int = 0
    reasons: list[str] = field(default_factory=list)


@dataclass
class ABDecision:
    state: DecisionState
    reason: str
    primary_metric: str
    delta_mean: float | None = None
    ci: BootstrapCI | None = None
    effective_n: int = 0
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "reason": self.reason,
            "primary_metric": self.primary_metric,
            "delta_mean": self.delta_mean,
            "ci": None
            if self.ci is None
            else {
                "mean": self.ci.mean,
                "low": self.ci.low,
                "high": self.ci.high,
                "width": self.ci.width,
                "n": self.ci.n,
                "exploratory": self.ci.exploratory,
            },
            "effective_n": self.effective_n,
            "details": self.details,
        }


def locate_bottleneck(
    baseline: MetricSnapshot,
    *,
    faith_low: float = FAITH_LOW,
    citp_low: float = CITP_LOW,
    crec_low: float = CREC_LOW,
    unresolved_high: float = UNRESOLVED_REF_HIGH,
) -> BottleneckResult:
    """Map aggregate signals to the first actionable pipeline stage."""
    signals = {
        "faith": baseline.faith,
        "citp": baseline.citp,
        "crec": baseline.crec,
        "unresolved_ref_rate": baseline.unresolved_ref_rate,
    }
    if baseline.faith is not None and baseline.faith < faith_low:
        return BottleneckResult("L5", f"Faith={baseline.faith:.3f} < {faith_low}", signals)
    if baseline.citp is not None and baseline.citp < citp_low:
        return BottleneckResult("L5", f"CitP={baseline.citp:.3f} < {citp_low}", signals)
    if baseline.unresolved_ref_rate is not None and baseline.unresolved_ref_rate >= unresolved_high:
        return BottleneckResult(
            "L4",
            f"unresolved_ref_rate={baseline.unresolved_ref_rate:.3f} >= {unresolved_high}",
            signals,
        )
    if baseline.crec is not None and baseline.crec < crec_low:
        return BottleneckResult("L2", f"CRec={baseline.crec:.3f} < {crec_low}", signals)
    return BottleneckResult("unknown", "no clear bottleneck", signals)


def pick_single_var_action(bottleneck: BottleneckResult) -> CandidatePick:
    """Pick the implemented MVP candidate for the located bottleneck stage."""
    if bottleneck.stage == "L5":
        return CandidatePick(
            action_id="llm_enable_thinking_on",
            stage="L5",
            config_knobs={"llm_enable_thinking": True},
            reason="answer LLM thinking mode off -> on (qa_agent extra_body)",
        )
    if bottleneck.stage == "L4":
        return CandidatePick(
            action_id="auto_cross_ref_closure_on",
            stage="L4",
            config_knobs={"retrieval_auto_cross_ref_closure": True},
            reason="retrieval_auto_cross_ref_closure off -> on",
        )
    return CandidatePick(
        action_id="noop",
        stage=bottleneck.stage,
        config_knobs={},
        reason=bottleneck.reason,
    )


def candidate_precheck(
    *,
    baseline: MetricSnapshot,
    pick: CandidatePick,
    unresolved_high: float = UNRESOLVED_REF_HIGH,
    faith_low: float = FAITH_LOW,
    citp_low: float = CITP_LOW,
) -> PrecheckResult:
    """Require a baseline signal that actually points at the picked stage."""
    if pick.stage == "L4":
        rate = baseline.unresolved_ref_rate
        points_to_l4 = rate is not None and rate >= unresolved_high
        reason = (
            f"L4 signal ok: unresolved_ref_rate={rate:.3f} >= {unresolved_high}"
            if points_to_l4
            else f"baseline unresolved_ref_rate={rate} does not reach {unresolved_high}"
        )
        return PrecheckResult(ok=points_to_l4, points_to_l4=points_to_l4, reasons=[reason])
    if pick.stage == "L5":
        faith_bad = baseline.faith is not None and baseline.faith < faith_low
        citp_bad = baseline.citp is not None and baseline.citp < citp_low
        ok = faith_bad or citp_bad
        reason = (
            f"L5 signal ok: faith={baseline.faith} citp={baseline.citp} "
            f"below thresholds ({faith_low}/{citp_low})"
            if ok
            else f"baseline faith={baseline.faith} citp={baseline.citp} look healthy"
        )
        return PrecheckResult(ok=ok, points_to_l4=False, reasons=[reason])
    return PrecheckResult(
        ok=False,
        points_to_l4=False,
        reasons=[f"no implemented candidate for stage {pick.stage}: {pick.reason}"],
    )


def context_diff_from_answers(
    baseline_answers: dict[str, dict[str, Any]],
    candidate_answers: dict[str, dict[str, Any]],
) -> tuple[list[str], dict[str, Any]]:
    """Compare ordered context chunk-id sequences from stored answers."""
    diff_ids: list[str] = []
    details: dict[str, Any] = {}
    for qid in sorted(set(baseline_answers) & set(candidate_answers)):
        baseline = baseline_answers[qid]
        candidate = candidate_answers[qid]
        base_ids = tuple(str(value) for value in baseline.get("context_chunk_ids") or [])
        cand_ids = tuple(str(value) for value in candidate.get("context_chunk_ids") or [])
        changed = base_ids != cand_ids
        details[qid] = {
            "changed": changed,
            "baseline_seq_n": len(base_ids),
            "candidate_seq_n": len(cand_ids),
            "baseline_seq_head": list(base_ids[:8]),
            "candidate_seq_head": list(cand_ids[:8]),
            "only_baseline": sorted(set(base_ids) - set(cand_ids))[:10],
            "only_candidate": sorted(set(cand_ids) - set(base_ids))[:10],
        }
        if changed:
            diff_ids.append(qid)
    return diff_ids, details


def answer_diff_from_answers(
    baseline_answers: dict[str, dict[str, Any]],
    candidate_answers: dict[str, dict[str, Any]],
) -> tuple[list[str], dict[str, Any]]:
    """Compare answer texts from stored answers (change gate for L5 candidates).

    A generation-level candidate must not be required to change retrieval, so
    the "candidate actually changed something" gate compares whitespace-
    normalized answer text instead of context chunk-id sequences.
    """
    diff_ids: list[str] = []
    details: dict[str, Any] = {}
    for qid in sorted(set(baseline_answers) & set(candidate_answers)):
        base_text = " ".join(str(baseline_answers[qid].get("answer") or "").split())
        cand_text = " ".join(str(candidate_answers[qid].get("answer") or "").split())
        changed = base_text != cand_text
        details[qid] = {
            "changed": changed,
            "baseline_chars": len(base_text),
            "candidate_chars": len(cand_text),
        }
        if changed:
            diff_ids.append(qid)
    return diff_ids, details


def merge_hard_gate_decisions(
    per_metric: dict[str, ABDecision],
    *,
    primary_metric: str = "faith",
    non_regress_metrics: Sequence[str] = ("citp",),
) -> ABDecision:
    """Merge the primary improvement decision with non-regression gates."""
    details = {
        "per_metric": {key: value.to_dict() for key, value in per_metric.items()},
        "primary_metric": primary_metric,
        "non_regress_metrics": list(non_regress_metrics),
    }
    primary = per_metric.get(primary_metric)
    if primary is None:
        return ABDecision("inconclusive", f"primary metric {primary_metric!r} missing", primary_metric, details=details)
    rejects = [name for name, decision in per_metric.items() if decision.state == "reject"]
    if rejects:
        return ABDecision(
            "reject",
            f"reject on: {', '.join(rejects)}",
            primary_metric,
            primary.delta_mean,
            primary.ci,
            primary.effective_n,
            details,
        )
    gates_pass = all(
        per_metric.get(metric) is not None and per_metric[metric].state == "accept"
        for metric in non_regress_metrics
    )
    if primary.state == "accept" and gates_pass:
        return ABDecision(
            "accept",
            f"primary {primary_metric} improved and non-regression gates passed",
            primary_metric,
            primary.delta_mean,
            primary.ci,
            primary.effective_n,
            details,
        )
    return ABDecision(
        "inconclusive",
        f"primary={primary.state}; non-regression gates did not all pass",
        primary_metric,
        primary.delta_mean,
        primary.ci,
        primary.effective_n,
        details,
    )


def ab_decide(
    baseline_values: Sequence[float],
    candidate_values: Sequence[float],
    *,
    primary_metric: str,
    epsilon: float = DEFAULT_EPSILON,
    delta: float = DEFAULT_DELTA,
    gate_n: int = 12,
    mode: Literal["improve", "non_regress"],
) -> ABDecision:
    """Return accept, reject, or inconclusive from a paired bootstrap CI."""
    n = len(baseline_values)
    details = {"epsilon": epsilon, "delta": delta, "gate_n": gate_n, "mode": mode}
    if n != len(candidate_values):
        raise ValueError("baseline and candidate values must be paired")
    if n < gate_n:
        return ABDecision(
            "inconclusive",
            f"n={n} < gate_n={gate_n}",
            primary_metric,
            effective_n=n,
            details=details,
        )

    ci = paired_bootstrap_ci(baseline_values, candidate_values)
    if ci.high < -delta:
        state: DecisionState = "reject"
        reason = f"CI [{ci.low:.3f}, {ci.high:.3f}] entirely below -delta={delta}"
    elif ci.width > 0.1:
        state = "inconclusive"
        reason = f"CI width={ci.width:.3f} > 0.1 (exploratory)"
    elif mode == "improve" and ci.low > epsilon:
        state = "accept"
        reason = f"CI [{ci.low:.3f}, {ci.high:.3f}] entirely above +epsilon={epsilon}"
    elif mode == "non_regress":
        state = "accept"
        reason = "no significant regression"
    else:
        state = "inconclusive"
        reason = f"CI [{ci.low:.3f}, {ci.high:.3f}] does not clear +epsilon={epsilon}"
    return ABDecision(state, reason, primary_metric, ci.mean, ci, n, details)
