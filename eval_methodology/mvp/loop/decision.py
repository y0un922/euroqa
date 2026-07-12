"""LocateBottleneck + PickSingleVarAction + ABDecide (single iteration).

Table 5 / Table 6 mapping from main.tex, with MVP_PLAN §E.2 additions:
  - unresolved_ref_rate high → L4 (auto_cross_ref candidate)
  - baseline self-noise as inconclusive floor
  - effective n < 15 or drop rate > 30% → trend / inconclusive
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Sequence

from eval_methodology.mvp.metrics.bootstrap import (
    BootstrapCI,
    paired_bootstrap_ci,
    self_noise_bound,
)
from eval_methodology.mvp.paths import (
    CONTEXT_DIFF_MIN_QUESTIONS,
    DEFAULT_DELTA,
    DEFAULT_EPSILON,
    MAX_JUDGE_DROP_RATE,
    MIN_EFFECTIVE_N,
)

DecisionState = Literal["accept", "reject", "inconclusive"]
Stage = Literal["L1", "L2", "L3", "L4", "L5", "ops", "unknown"]

# Soft thresholds for "metric is down" on [0,1] scales (MVP defaults).
FAITH_LOW = 0.85
CITP_LOW = 0.80
CREC_LOW = 0.70
UNRESOLVED_REF_HIGH = 0.15


@dataclass(frozen=True)
class MetricSnapshot:
    """Minimal metric dict for bottleneck / A/B (mockable in unit tests)."""

    faith: float | None = None
    citp: float | None = None
    crec: float | None = None
    unresolved_ref_rate: float | None = None
    effective_n: int = 0
    judge_drop_rate: float = 0.0
    crec_eligible_n: int = 0
    degraded_to_trend: bool = False

    @classmethod
    def from_aggregate(cls, agg: dict[str, Any]) -> MetricSnapshot:
        n_f = int(agg.get("effective_n_faith") or 0)
        n_c = int(agg.get("effective_n_citp") or 0)
        eff = min(n_f, n_c) if n_f and n_c else max(n_f, n_c)
        return cls(
            faith=agg.get("faith_mean"),
            citp=agg.get("citp_mean"),
            crec=agg.get("crec_mean"),
            unresolved_ref_rate=agg.get("unresolved_ref_rate_mean"),
            effective_n=eff,
            judge_drop_rate=float(agg.get("judge_drop_rate") or 0.0),
            crec_eligible_n=int(agg.get("crec_eligible_n") or 0),
            degraded_to_trend=bool(agg.get("degraded_to_trend")),
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
    context_diff_n: int
    reasons: list[str] = field(default_factory=list)


@dataclass
class ABDecision:
    state: DecisionState
    reason: str
    primary_metric: str
    delta_mean: float | None = None
    ci: BootstrapCI | None = None
    self_noise: float | None = None
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
            "self_noise": self.self_noise,
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
    """Map baseline metrics → stage (main.tex table 5 + unresolved_ref_rate→L4)."""
    signals: dict[str, Any] = {
        "faith": baseline.faith,
        "citp": baseline.citp,
        "crec": baseline.crec,
        "unresolved_ref_rate": baseline.unresolved_ref_rate,
    }

    # Hard-gate issues first (Faith / CitP → L5).
    if baseline.faith is not None and baseline.faith < faith_low:
        return BottleneckResult(
            stage="L5",
            reason=f"Faith={baseline.faith:.3f} < {faith_low} → generation/citation discipline (L5)",
            metric_signals=signals,
        )
    if baseline.citp is not None and baseline.citp < citp_low:
        return BottleneckResult(
            stage="L5",
            reason=f"CitP={baseline.citp:.3f} < {citp_low} → citation postprocess (L5)",
            metric_signals=signals,
        )

    # L4 signal from unresolved refs (needed for auto_cross_ref candidate).
    if (
        baseline.unresolved_ref_rate is not None
        and baseline.unresolved_ref_rate >= unresolved_high
    ):
        return BottleneckResult(
            stage="L4",
            reason=(
                f"unresolved_ref_rate={baseline.unresolved_ref_rate:.3f} ≥ {unresolved_high} "
                "→ cross-ref closure / parent-chunk (L4)"
            ),
            metric_signals=signals,
        )

    # CRec low → L1/L2 (prefer L2 config knobs; L1 is code/prompt).
    if baseline.crec is not None and baseline.crec < crec_low:
        return BottleneckResult(
            stage="L2",
            reason=f"CRec={baseline.crec:.3f} < {crec_low} → retrieval budget/decompose (L1→L2)",
            metric_signals=signals,
        )

    # Default: if mild unresolved, still L4; else unknown.
    if baseline.unresolved_ref_rate and baseline.unresolved_ref_rate > 0:
        return BottleneckResult(
            stage="L4",
            reason=(
                f"residual unresolved_ref_rate={baseline.unresolved_ref_rate:.3f} "
                "→ try L4 closure"
            ),
            metric_signals=signals,
        )

    return BottleneckResult(
        stage="unknown",
        reason="no clear bottleneck from Faith/CitP/CRec/unresolved_ref_rate",
        metric_signals=signals,
    )


def pick_single_var_action(bottleneck: BottleneckResult) -> CandidatePick:
    """Table 6: one action. MVP only implements L4 auto_cross_ref off→on."""
    if bottleneck.stage == "L4":
        return CandidatePick(
            action_id="auto_cross_ref_closure_on",
            stage="L4",
            config_knobs={"retrieval_auto_cross_ref_closure": True},
            reason="MVP A: retrieval_auto_cross_ref_closure off→on",
        )
    if bottleneck.stage == "L5":
        return CandidatePick(
            action_id="deferred_l5_prompt",
            stage="L5",
            config_knobs={},
            reason="L5 needs code/prompt overlay (option B) — not in this MVP",
        )
    if bottleneck.stage in ("L1", "L2"):
        return CandidatePick(
            action_id="deferred_retrieval_budget",
            stage=bottleneck.stage,
            config_knobs={},
            reason=(
                "vector/bm25/rerank knobs are no-ops under _INITIAL_TOP_K clamp; "
                "code-level overlay deferred"
            ),
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
    context_diff_question_ids: Sequence[str],
    unresolved_high: float = UNRESOLVED_REF_HIGH,
    min_diff_questions: int = CONTEXT_DIFF_MIN_QUESTIONS,
) -> PrecheckResult:
    """Two gates before expensive judge on candidate (MVP_PLAN §E.1 / §C)."""
    reasons: list[str] = []
    urr = baseline.unresolved_ref_rate
    points_l4 = urr is not None and urr >= unresolved_high
    # Also allow residual > 0 when LocateBottleneck already chose L4.
    if not points_l4 and urr is not None and urr > 0:
        points_l4 = True
        reasons.append(
            f"unresolved_ref_rate={urr:.3f} > 0 (weak L4 signal accepted for MVP)"
        )
    if not points_l4:
        reasons.append(
            f"baseline unresolved_ref_rate={urr} does not point to L4 "
            f"(need ≥ {unresolved_high} or > 0 residual)"
        )

    diff_n = len(set(context_diff_question_ids))
    if diff_n < min_diff_questions:
        reasons.append(
            f"context chunk-id set changed on {diff_n} questions "
            f"(need ≥ {min_diff_questions})"
        )

    ok = points_l4 and diff_n >= min_diff_questions
    if ok:
        reasons.append("precheck passed")
    return PrecheckResult(
        ok=ok,
        points_to_l4=points_l4,
        context_diff_n=diff_n,
        reasons=reasons,
    )


def ab_decide(
    *,
    baseline_values: Sequence[float],
    candidate_values: Sequence[float],
    baseline_repeat_a: Sequence[float] | None = None,
    baseline_repeat_b: Sequence[float] | None = None,
    primary_metric: str = "faith",
    epsilon: float = DEFAULT_EPSILON,
    delta: float = DEFAULT_DELTA,
    effective_n: int | None = None,
    judge_drop_rate: float = 0.0,
    degraded_to_trend: bool = False,
) -> ABDecision:
    """Three-state A/B decision via paired bootstrap + self-noise floor.

    accept:       CI entirely above +epsilon (and improvement > self-noise)
    reject:       CI entirely below -delta (regression)
    inconclusive: otherwise, or n/drop gates, or improvement < self-noise
    """
    n = len(baseline_values)
    eff = effective_n if effective_n is not None else n
    details: dict[str, Any] = {
        "epsilon": epsilon,
        "delta": delta,
        "judge_drop_rate": judge_drop_rate,
        "degraded_to_trend": degraded_to_trend,
    }

    if n == 0 or eff < MIN_EFFECTIVE_N:
        return ABDecision(
            state="inconclusive",
            reason=f"effective n={eff} < {MIN_EFFECTIVE_N} (or empty series)",
            primary_metric=primary_metric,
            effective_n=eff,
            details=details,
        )
    if judge_drop_rate > MAX_JUDGE_DROP_RATE or degraded_to_trend:
        return ABDecision(
            state="inconclusive",
            reason=(
                f"degraded to trend reference "
                f"(drop_rate={judge_drop_rate:.2%}, degraded={degraded_to_trend})"
            ),
            primary_metric=primary_metric,
            effective_n=eff,
            details=details,
        )

    ci = paired_bootstrap_ci(baseline_values, candidate_values)
    details["ci_exploratory"] = ci.exploratory

    noise = 0.0
    if baseline_repeat_a is not None and baseline_repeat_b is not None:
        noise = self_noise_bound(baseline_repeat_a, baseline_repeat_b)
    details["self_noise"] = noise

    # Improvement smaller than baseline self-noise → inconclusive.
    if abs(ci.mean) <= noise and noise > 0:
        return ABDecision(
            state="inconclusive",
            reason=(
                f"|Δ|={abs(ci.mean):.4f} ≤ baseline self-noise={noise:.4f}"
            ),
            primary_metric=primary_metric,
            delta_mean=ci.mean,
            ci=ci,
            self_noise=noise,
            effective_n=eff,
            details=details,
        )

    if ci.exploratory:
        return ABDecision(
            state="inconclusive",
            reason=f"CI width={ci.width:.3f} > 0.1 → exploratory only",
            primary_metric=primary_metric,
            delta_mean=ci.mean,
            ci=ci,
            self_noise=noise,
            effective_n=eff,
            details=details,
        )

    # Accept: lower bound > epsilon (significant improvement).
    if ci.low > epsilon:
        return ABDecision(
            state="accept",
            reason=f"CI [{ci.low:.3f}, {ci.high:.3f}] entirely above +ε={epsilon}",
            primary_metric=primary_metric,
            delta_mean=ci.mean,
            ci=ci,
            self_noise=noise,
            effective_n=eff,
            details=details,
        )

    # Reject: upper bound < -delta (significant regression).
    if ci.high < -delta:
        return ABDecision(
            state="reject",
            reason=f"CI [{ci.low:.3f}, {ci.high:.3f}] entirely below -δ={delta}",
            primary_metric=primary_metric,
            delta_mean=ci.mean,
            ci=ci,
            self_noise=noise,
            effective_n=eff,
            details=details,
        )

    return ABDecision(
        state="inconclusive",
        reason=(
            f"CI [{ci.low:.3f}, {ci.high:.3f}] crosses decision thresholds "
            f"(ε={epsilon}, δ={delta})"
        ),
        primary_metric=primary_metric,
        delta_mean=ci.mean,
        ci=ci,
        self_noise=noise,
        effective_n=eff,
        details=details,
    )
