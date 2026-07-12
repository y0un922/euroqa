"""Unit tests for ABDecide three-state outcomes + hard-gate merge."""

from __future__ import annotations

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from eval_methodology.mvp.loop.decision import (  # noqa: E402
    MetricSnapshot,
    ab_decide,
    candidate_precheck,
    locate_bottleneck,
    merge_hard_gate_decisions,
    pick_single_var_action,
)
from eval_methodology.mvp.runner.client import (  # noqa: E402
    context_sequences_differ,
)


def test_ab_accept_when_ci_above_epsilon():
    baseline = [0.50] * 16
    candidate = [0.90] * 16
    d = ab_decide(
        baseline_values=baseline,
        candidate_values=candidate,
        baseline_repeat_a=baseline,
        baseline_repeat_b=baseline,
        primary_metric="faith",
        epsilon=0.05,
        delta=0.05,
        effective_n=16,
    )
    assert d.state == "accept"
    assert d.ci is not None
    assert d.ci.low > 0.05


def test_ab_reject_when_ci_below_minus_delta():
    baseline = [0.90] * 16
    candidate = [0.40] * 16
    d = ab_decide(
        baseline_values=baseline,
        candidate_values=candidate,
        baseline_repeat_a=baseline,
        baseline_repeat_b=baseline,
        primary_metric="faith",
        epsilon=0.05,
        delta=0.05,
        effective_n=16,
    )
    assert d.state == "reject"
    assert d.ci is not None
    assert d.ci.high < -0.05


def test_ab_inconclusive_when_ci_crosses_threshold():
    """Non-trivial case: mean improvement but CI crosses +ε (audit F3)."""
    # 16 items: mostly small gains, a few zeros → wide-ish CI around ~0.06
    baseline = [0.70] * 16
    candidate = [0.70 + 0.06] * 12 + [0.70 + 0.02] * 4
    d = ab_decide(
        baseline_values=baseline,
        candidate_values=candidate,
        baseline_repeat_a=baseline,
        baseline_repeat_b=baseline,
        primary_metric="faith",
        epsilon=0.05,
        delta=0.05,
        effective_n=16,
    )
    # CI should not be entirely above 0.05 for this mixed series, or if mean is
    # high enough and zero width still accept — force crossing with tiny B noise.
    # With constant per-item deltas of mixed 0.06/0.02, mean=0.05, CI degenerate.
    # Use heterogeneous deltas so bootstrap spreads across 0.05.
    baseline = [0.5 + 0.01 * i for i in range(16)]
    candidate = [b + (0.09 if i < 8 else 0.01) for i, b in enumerate(baseline)]
    d = ab_decide(
        baseline_values=baseline,
        candidate_values=candidate,
        baseline_repeat_a=baseline,
        baseline_repeat_b=baseline,
        primary_metric="faith",
        epsilon=0.05,
        delta=0.05,
        effective_n=16,
    )
    assert d.state == "inconclusive"
    assert d.ci is not None
    # CI crosses the +ε boundary (not entirely above, not entirely below -δ)
    assert d.ci.low <= 0.05
    assert d.ci.high >= -0.05


def test_ab_inconclusive_when_n_below_15():
    baseline = [0.5, 0.6, 0.55]
    candidate = [0.9, 0.95, 0.92]
    d = ab_decide(
        baseline_values=baseline,
        candidate_values=candidate,
        effective_n=3,
    )
    assert d.state == "inconclusive"
    assert "effective n" in d.reason


def test_ab_inconclusive_when_within_self_noise():
    baseline = [0.70 + (i % 3) * 0.01 for i in range(16)]
    candidate = [x + 0.005 for x in baseline]
    rep_a = baseline
    rep_b = [x + 0.02 for x in baseline]
    d = ab_decide(
        baseline_values=baseline,
        candidate_values=candidate,
        baseline_repeat_a=rep_a,
        baseline_repeat_b=rep_b,
        effective_n=16,
        epsilon=0.05,
    )
    assert d.state == "inconclusive"
    assert "self-noise" in d.reason


def test_ab_inconclusive_high_drop_rate():
    baseline = [0.5] * 16
    candidate = [0.9] * 16
    d = ab_decide(
        baseline_values=baseline,
        candidate_values=candidate,
        effective_n=16,
        judge_drop_rate=0.5,
    )
    assert d.state == "inconclusive"
    assert "trend" in d.reason.lower() or "drop" in d.reason.lower()


def test_merge_hard_gates_faith_accept_citp_reject_is_reject():
    faith = ab_decide(
        baseline_values=[0.5] * 16,
        candidate_values=[0.9] * 16,
        effective_n=16,
        mode="improve",
    )
    citp = ab_decide(
        baseline_values=[0.9] * 16,
        candidate_values=[0.4] * 16,
        effective_n=16,
        mode="non_regress",
    )
    assert faith.state == "accept"
    assert citp.state == "reject"
    final = merge_hard_gate_decisions(
        {"faith": faith, "citp": citp}, primary_metric="faith"
    )
    assert final.state == "reject"


def test_merge_hard_gates_faith_improve_citp_flat_is_accept():
    """CitP flat must non-regress pass, not block overall accept (E3 residual)."""
    faith = ab_decide(
        baseline_values=[0.5] * 16,
        candidate_values=[0.9] * 16,
        effective_n=16,
        mode="improve",
    )
    citp = ab_decide(
        baseline_values=[0.7] * 16,
        candidate_values=[0.7] * 16,  # exactly flat
        effective_n=16,
        mode="non_regress",
    )
    assert faith.state == "accept"
    assert citp.state == "accept"
    final = merge_hard_gate_decisions(
        {"faith": faith, "citp": citp}, primary_metric="faith"
    )
    assert final.state == "accept"


def test_non_regress_flat_is_accept_not_inconclusive():
    d = ab_decide(
        baseline_values=[0.7] * 16,
        candidate_values=[0.7] * 16,
        effective_n=16,
        mode="non_regress",
    )
    assert d.state == "accept"
    assert "non-regress" in d.reason


def test_merge_hard_gates_both_improve_accept():
    faith = ab_decide(
        baseline_values=[0.5] * 16,
        candidate_values=[0.9] * 16,
        effective_n=16,
        mode="improve",
    )
    citp = ab_decide(
        baseline_values=[0.5] * 16,
        candidate_values=[0.9] * 16,
        effective_n=16,
        mode="non_regress",
    )
    final = merge_hard_gate_decisions(
        {"faith": faith, "citp": citp}, primary_metric="faith"
    )
    assert final.state == "accept"


def test_merge_hard_gates_primary_inconclusive_blocks_accept():
    faith = ab_decide(
        baseline_values=[0.7] * 16,
        candidate_values=[0.71] * 16,
        effective_n=16,
        mode="improve",
    )
    citp = ab_decide(
        baseline_values=[0.7] * 16,
        candidate_values=[0.7] * 16,
        effective_n=16,
        mode="non_regress",
    )
    assert faith.state == "inconclusive"
    assert citp.state == "accept"
    final = merge_hard_gate_decisions(
        {"faith": faith, "citp": citp}, primary_metric="faith"
    )
    assert final.state == "inconclusive"


def test_locate_bottleneck_l4_from_unresolved():
    snap = MetricSnapshot(
        faith=0.95,
        citp=0.95,
        crec=0.90,
        unresolved_ref_rate=0.40,
        effective_n=16,
    )
    b = locate_bottleneck(snap)
    assert b.stage == "L4"
    pick = pick_single_var_action(b)
    assert pick.action_id == "auto_cross_ref_closure_on"
    assert pick.config_knobs.get("retrieval_auto_cross_ref_closure") is True


def test_locate_bottleneck_l5_from_faith():
    snap = MetricSnapshot(faith=0.50, citp=0.90, crec=0.90, unresolved_ref_rate=0.0)
    b = locate_bottleneck(snap)
    assert b.stage == "L5"


def test_locate_bottleneck_no_weak_l4_for_tiny_unresolved():
    snap = MetricSnapshot(
        faith=0.95, citp=0.95, crec=0.90, unresolved_ref_rate=0.001
    )
    b = locate_bottleneck(snap)
    assert b.stage == "unknown"


def test_precheck_rejects_weak_l4_and_requires_ordered_diff():
    snap = MetricSnapshot(unresolved_ref_rate=0.001, faith=0.9, citp=0.9)
    pre = candidate_precheck(
        baseline=snap,
        context_diff_question_ids=["Q01", "Q02", "Q03"],
    )
    assert pre.ok is False
    assert pre.points_to_l4 is False

    snap_ok = MetricSnapshot(unresolved_ref_rate=0.20, faith=0.9, citp=0.9)
    pre2 = candidate_precheck(
        baseline=snap_ok,
        context_diff_question_ids=["Q01", "Q02"],  # only 2 < 3
    )
    assert pre2.ok is False
    assert pre2.points_to_l4 is True

    pre3 = candidate_precheck(
        baseline=snap_ok,
        context_diff_question_ids=["Q01", "Q02", "Q03"],
    )
    assert pre3.ok is True


def test_ordered_context_sequence_diff_detects_reorder():
    # Same multiset, different order → must count as change (audit B2).
    assert context_sequences_differ(["a", "b"], ["b", "a"]) is True
    assert context_sequences_differ(["a", "b"], ["a", "b"]) is False
    assert context_sequences_differ(
        {"context_chunk_ids": ["a", "b"]},
        {"context_chunk_ids": ["b", "a"]},
    )
