"""Unit tests for ABDecide three-state outcomes (mock metric series)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from eval_methodology.mvp.loop.decision import (  # noqa: E402
    MetricSnapshot,
    ab_decide,
    candidate_precheck,
    locate_bottleneck,
    pick_single_var_action,
)


def test_ab_accept_when_ci_above_epsilon():
    # Clear improvement on all 16 items.
    baseline = [0.50] * 16
    candidate = [0.90] * 16
    d = ab_decide(
        baseline_values=baseline,
        candidate_values=candidate,
        baseline_repeat_a=baseline,
        baseline_repeat_b=baseline,  # zero self-noise
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
    candidate = [x + 0.005 for x in baseline]  # tiny lift
    # Self-noise larger than the lift.
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


def test_precheck_requires_context_diff():
    snap = MetricSnapshot(unresolved_ref_rate=0.3, faith=0.9, citp=0.9)
    pre = candidate_precheck(
        baseline=snap,
        context_diff_question_ids=["Q01", "Q02"],  # only 2 < 3
    )
    assert pre.ok is False
    assert pre.context_diff_n == 2

    pre2 = candidate_precheck(
        baseline=snap,
        context_diff_question_ids=["Q01", "Q02", "Q03"],
    )
    assert pre2.ok is True
