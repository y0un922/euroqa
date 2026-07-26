"""Baseline cache-key scoping and judge-model consistency helpers."""

from __future__ import annotations

from eval_methodology.mvp.loop.run_mvp import _baseline_key, _judge_models_of


def _items(*ids: str) -> list[dict[str, str]]:
    return [{"id": qid} for qid in ids]


def test_baseline_key_stable_for_same_items_and_split():
    assert _baseline_key(_items("Q1", "Q2"), "dev") == _baseline_key(
        _items("Q1", "Q2"), "dev"
    )


def test_baseline_key_differs_by_item_set():
    full = _baseline_key(_items("Q1", "Q2", "Q3"), "dev")
    limited = _baseline_key(_items("Q1", "Q2"), "dev")
    assert full != limited


def test_baseline_key_differs_by_split():
    assert _baseline_key(_items("Q1"), "dev") != _baseline_key(_items("Q1"), "test")


def test_judge_models_union_across_runs():
    runs = [
        {"judge_models": ["model-a"]},
        {"judge_models": ["model-a", "model-b"]},
        {"judge_models": []},
        {},
    ]
    assert _judge_models_of(runs) == {"model-a", "model-b"}
