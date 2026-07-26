"""Unit tests for MVP v2 three-state decisions."""

from __future__ import annotations

import pytest

from eval_methodology.mvp.loop.decision import (
    MetricSnapshot,
    ab_decide,
    candidate_precheck,
    locate_bottleneck,
    merge_hard_gate_decisions,
    pick_single_var_action,
)


def test_ab_accept_and_reject():
    accepted = ab_decide(
        [0.5] * 16,
        [0.9] * 16,
        primary_metric="faith",
        mode="improve",
    )
    rejected = ab_decide(
        [0.9] * 16,
        [0.4] * 16,
        primary_metric="faith",
        mode="improve",
    )
    assert accepted.state == "accept"
    assert rejected.state == "reject"


@pytest.mark.parametrize(
    ("gate_n", "expected"),
    [(12, "accept"), (17, "inconclusive")],
)
def test_ab_gate_n(gate_n: int, expected: str):
    decision = ab_decide(
        [0.5] * 16,
        [0.9] * 16,
        primary_metric="faith",
        gate_n=gate_n,
        mode="improve",
    )
    assert decision.state == expected


def test_ab_inconclusive_for_exploratory_ci():
    baseline = [0.5] * 16
    candidate = [0.9] * 8 + [0.4] * 8
    decision = ab_decide(
        baseline,
        candidate,
        primary_metric="faith",
        mode="improve",
    )
    assert decision.state == "inconclusive"
    assert decision.ci is not None and decision.ci.width > 0.1


def test_non_regress_flat_accepts():
    decision = ab_decide(
        [0.7] * 16,
        [0.7] * 16,
        primary_metric="citp",
        mode="non_regress",
    )
    assert decision.state == "accept"


def test_merge_requires_primary_and_citp_gate():
    faith = ab_decide(
        [0.5] * 16,
        [0.9] * 16,
        primary_metric="faith",
        mode="improve",
    )
    citp = ab_decide(
        [0.7] * 16,
        [0.7] * 16,
        primary_metric="citp",
        mode="non_regress",
    )
    assert merge_hard_gate_decisions({"faith": faith, "citp": citp}).state == "accept"


def test_l4_bottleneck_and_precheck():
    snapshot = MetricSnapshot(
        faith=0.95,
        citp=0.95,
        crec=0.9,
        unresolved_ref_rate=0.2,
    )
    bottleneck = locate_bottleneck(snapshot)
    assert bottleneck.stage == "L4"
    pick = pick_single_var_action(bottleneck)
    assert pick.action_id == "auto_cross_ref_closure_on"
    assert candidate_precheck(baseline=snapshot, pick=pick).ok


def test_precheck_rejects_weak_l4_signal():
    snapshot = MetricSnapshot(faith=0.95, citp=0.95, unresolved_ref_rate=0.01)
    pick = pick_single_var_action(
        locate_bottleneck(MetricSnapshot(unresolved_ref_rate=0.2))
    )
    assert pick.stage == "L4"
    assert not candidate_precheck(baseline=snapshot, pick=pick).ok


def test_l5_bottleneck_picks_thinking_candidate():
    snapshot = MetricSnapshot(
        faith=0.71,
        citp=0.44,
        crec=0.58,
        unresolved_ref_rate=0.30,
    )
    bottleneck = locate_bottleneck(snapshot)
    assert bottleneck.stage == "L5"
    pick = pick_single_var_action(bottleneck)
    assert pick.action_id == "llm_enable_thinking_on"
    assert pick.config_knobs == {"llm_enable_thinking": True}
    assert candidate_precheck(baseline=snapshot, pick=pick).ok


def test_precheck_rejects_l5_pick_on_healthy_baseline():
    healthy = MetricSnapshot(faith=0.95, citp=0.95)
    pick = pick_single_var_action(
        locate_bottleneck(MetricSnapshot(faith=0.5, citp=0.5))
    )
    assert pick.stage == "L5"
    assert not candidate_precheck(baseline=healthy, pick=pick).ok


def test_precheck_rejects_noop_pick():
    snapshot = MetricSnapshot(faith=0.95, citp=0.95, crec=0.9, unresolved_ref_rate=0.0)
    pick = pick_single_var_action(locate_bottleneck(snapshot))
    assert pick.action_id == "noop"
    assert not candidate_precheck(baseline=snapshot, pick=pick).ok
