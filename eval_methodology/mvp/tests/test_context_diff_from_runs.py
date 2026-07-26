"""Stored-answer diff gate tests (context gate for L4, answer gate for L5)."""

from eval_methodology.mvp.loop import run_mvp
from eval_methodology.mvp.loop.decision import (
    answer_diff_from_answers,
    context_diff_from_answers,
)


def test_context_diff_counts_order_changes_and_supports_three_question_gate():
    baseline = {
        "Q1": {"context_chunk_ids": ["a", "b"]},
        "Q2": {"context_chunk_ids": ["c"]},
        "Q3": {"context_chunk_ids": ["d"]},
        "Q4": {"context_chunk_ids": ["same"]},
    }
    candidate = {
        "Q1": {"context_chunk_ids": ["b", "a"]},
        "Q2": {"context_chunk_ids": ["x"]},
        "Q3": {"context_chunk_ids": ["d", "e"]},
        "Q4": {"context_chunk_ids": ["same"]},
    }
    diff_ids, details = context_diff_from_answers(baseline, candidate)
    assert diff_ids == ["Q1", "Q2", "Q3"]
    assert details["Q1"]["changed"]
    assert len(diff_ids) >= 3


def test_context_diff_below_three_does_not_pass_gate():
    baseline = {"Q1": {"context_chunk_ids": ["a"]}, "Q2": {"context_chunk_ids": ["b"]}}
    candidate = {"Q1": {"context_chunk_ids": ["x"]}, "Q2": {"context_chunk_ids": ["b"]}}
    diff_ids, _details = context_diff_from_answers(baseline, candidate)
    assert len(diff_ids) < 3


def test_compare_diff_gate_skips_candidate_judge(monkeypatch, tmp_path):
    items = [{"id": "Q1", "question": "q1"}, {"id": "Q2", "question": "q2"}]
    baseline_answers = {
        "Q1": {"context_chunk_ids": ["a"]},
        "Q2": {"context_chunk_ids": ["b"]},
    }
    candidate_answers = {
        "Q1": {"context_chunk_ids": ["x"]},
        "Q2": {"context_chunk_ids": ["b"]},
    }
    baseline_run = {
        "aggregate": {
            "faith_mean": 0.95,
            "citp_mean": 0.95,
            "crec_mean": 0.9,
            "unresolved_ref_rate_mean": 0.2,
        },
        "per_question": [],
    }
    monkeypatch.setattr(run_mvp, "RUNS_DIR", tmp_path)
    monkeypatch.setattr(run_mvp, "take_snapshot", lambda: object())
    monkeypatch.setattr(run_mvp, "_load_split_items", lambda *_args: items)
    monkeypatch.setattr(
        run_mvp,
        "_build_baseline",
        lambda *_args, **_kwargs: (
            {"cache_key": "key", "baseline_runs": [baseline_run]},
            tmp_path / "baseline",
        ),
    )
    monkeypatch.setattr(
        run_mvp,
        "_generate_variant",
        lambda *_args, **_kwargs: ([candidate_answers], 0.1),
    )
    monkeypatch.setattr(run_mvp, "load_answers", lambda *_args: baseline_answers)
    monkeypatch.setattr(
        run_mvp,
        "_evaluate_runs",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("judge called")),
    )
    monkeypatch.setattr(run_mvp, "_finish", lambda payload, *_args: payload)
    monkeypatch.setattr(run_mvp, "_stamp", lambda: "test")

    payload = run_mvp.run_compare(split="dev")
    assert payload["decision"]["reason"] == "候选未改变检索路径"
    assert "candidate_runs" not in payload


def test_answer_diff_ignores_whitespace_and_counts_text_changes():
    baseline = {
        "Q1": {"answer": "同一段  答案\n换行"},
        "Q2": {"answer": "原答案"},
    }
    candidate = {
        "Q1": {"answer": "同一段 答案 换行"},
        "Q2": {"answer": "新答案"},
    }
    diff_ids, details = answer_diff_from_answers(baseline, candidate)
    assert diff_ids == ["Q2"]
    assert not details["Q1"]["changed"]
    assert details["Q2"]["changed"]


def test_compare_l5_pick_uses_answer_gate_and_skips_judge(monkeypatch, tmp_path):
    items = [{"id": "Q1", "question": "q1"}, {"id": "Q2", "question": "q2"}]
    same_answers = {
        "Q1": {"answer": "a1", "context_chunk_ids": ["a"]},
        "Q2": {"answer": "a2", "context_chunk_ids": ["b"]},
    }
    baseline_run = {
        "aggregate": {
            "faith_mean": 0.5,
            "citp_mean": 0.9,
            "crec_mean": 0.9,
            "unresolved_ref_rate_mean": 0.0,
        },
        "per_question": [],
    }
    generated_with = []

    def fake_generate(candidate, *_args, **_kwargs):
        generated_with.append(candidate)
        return [dict(same_answers)], 0.1

    monkeypatch.setattr(run_mvp, "RUNS_DIR", tmp_path)
    monkeypatch.setattr(run_mvp, "take_snapshot", lambda: object())
    monkeypatch.setattr(run_mvp, "_load_split_items", lambda *_args: items)
    monkeypatch.setattr(
        run_mvp,
        "_build_baseline",
        lambda *_args, **_kwargs: (
            {"cache_key": "key", "baseline_runs": [baseline_run]},
            tmp_path / "baseline",
        ),
    )
    monkeypatch.setattr(run_mvp, "_generate_variant", fake_generate)
    monkeypatch.setattr(run_mvp, "load_answers", lambda *_args: dict(same_answers))
    monkeypatch.setattr(
        run_mvp,
        "_evaluate_runs",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("judge called")),
    )
    monkeypatch.setattr(run_mvp, "_finish", lambda payload, *_args: payload)
    monkeypatch.setattr(run_mvp, "_stamp", lambda: "test")

    payload = run_mvp.run_compare(split="dev")
    assert payload["pick"]["action_id"] == "llm_enable_thinking_on"
    assert generated_with and generated_with[0].llm_enable_thinking is True
    assert payload["precheck"]["diff_kind"] == "answer"
    assert payload["decision"]["reason"] == "候选未改变答案"
    assert "candidate_runs" not in payload
