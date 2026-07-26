"""compare-runs code-change gate: stored-run pairing, latency, decisions."""

import json

import pytest

from eval_methodology.mvp.loop import run_mvp


def _write_run(tmp_path, name, *, item_ids, answers, git_head="head"):
    run_dir = tmp_path / name
    answer_dir = run_dir / "answers" / "baseline"
    answer_dir.mkdir(parents=True)
    payload = {
        "run_id": name,
        "mode": "baseline",
        "split": "dev",
        "item_ids": item_ids,
        "git_head": git_head,
    }
    (run_dir / "payload.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )
    for qid, record in answers.items():
        (answer_dir / f"{qid}.json").write_text(
            json.dumps({"id": qid, "status": "ok", **record}, ensure_ascii=False),
            encoding="utf-8",
        )
    return run_dir


def _answers(elapsed_ms, contexts):
    return {
        qid: {
            "question": f"q-{qid}",
            "answer": f"answer-{qid}",
            "context_chunk_ids": chunk_ids,
            "elapsed_ms": elapsed_ms,
        }
        for qid, chunk_ids in contexts.items()
    }


def _fake_evaluate(faith_by_qid):
    def evaluate(answer_runs, _items, _candidate, *, use_llm_judge):
        runs = []
        for answers in answer_runs:
            runs.append(
                {
                    "aggregate": {},
                    "judge_models": ["judge-x"],
                    "per_question": [
                        {
                            "question_id": qid,
                            "faith": faith_by_qid[qid],
                            "citp": 1.0,
                        }
                        for qid in sorted(answers)
                    ],
                }
            )
        return runs, 0.0

    return evaluate


def test_compare_runs_accepts_non_regressing_code_change(monkeypatch, tmp_path):
    item_ids = [f"Q{i}" for i in range(1, 4)]
    items = [{"id": qid, "question": f"q-{qid}"} for qid in item_ids]
    baseline_dir = _write_run(
        tmp_path,
        "baseline-old",
        item_ids=item_ids,
        answers=_answers(2000, {qid: ["a", "b"] for qid in item_ids}),
        git_head="old",
    )
    candidate_dir = _write_run(
        tmp_path,
        "baseline-new",
        item_ids=item_ids,
        answers=_answers(1000, {qid: ["b", "a"] for qid in item_ids}),
        git_head="new",
    )

    monkeypatch.setattr(run_mvp, "RUNS_DIR", tmp_path / "out")
    monkeypatch.setattr(run_mvp, "take_snapshot", lambda: object())
    monkeypatch.setattr(run_mvp, "_load_split_items", lambda *_args: items)
    monkeypatch.setattr(
        run_mvp, "_evaluate_runs", _fake_evaluate({qid: 0.9 for qid in item_ids})
    )
    monkeypatch.setattr(run_mvp, "_finish", lambda payload, *_args: payload)
    monkeypatch.setattr(run_mvp, "_stamp", lambda: "test")

    payload = run_mvp.run_compare_runs(
        baseline_run_dir=baseline_dir,
        candidate_run_dir=candidate_dir,
        gate_n=3,
    )

    assert payload["mode"] == "compare_runs"
    assert payload["baseline_git_head"] == "old"
    assert payload["candidate_git_head"] == "new"
    assert payload["precheck"]["diff_n"] == 3
    assert payload["latency"]["baseline"]["p50_ms"] == 2000
    assert payload["latency"]["candidate"]["p95_ms"] == 1000
    assert payload["decision"]["state"] == "accept"
    assert payload["decision_faith"]["details"]["mode"] == "non_regress"


def test_compare_runs_rejects_mismatched_item_sets(monkeypatch, tmp_path):
    baseline_dir = _write_run(
        tmp_path,
        "baseline-old",
        item_ids=["Q1", "Q2"],
        answers=_answers(1000, {"Q1": ["a"], "Q2": ["b"]}),
    )
    candidate_dir = _write_run(
        tmp_path,
        "baseline-new",
        item_ids=["Q1", "Q3"],
        answers=_answers(1000, {"Q1": ["a"], "Q3": ["c"]}),
    )
    monkeypatch.setattr(run_mvp, "take_snapshot", lambda: object())

    with pytest.raises(RuntimeError, match="different item sets"):
        run_mvp.run_compare_runs(
            baseline_run_dir=baseline_dir,
            candidate_run_dir=candidate_dir,
        )


def test_compare_runs_rejects_incomplete_answers(monkeypatch, tmp_path):
    item_ids = ["Q1", "Q2"]
    items = [{"id": qid, "question": f"q-{qid}"} for qid in item_ids]
    baseline_dir = _write_run(
        tmp_path,
        "baseline-old",
        item_ids=item_ids,
        answers=_answers(1000, {"Q1": ["a"], "Q2": ["b"]}),
    )
    candidate_dir = _write_run(
        tmp_path,
        "baseline-new",
        item_ids=item_ids,
        answers=_answers(1000, {"Q1": ["a"]}),
    )
    monkeypatch.setattr(run_mvp, "take_snapshot", lambda: object())
    monkeypatch.setattr(run_mvp, "_load_split_items", lambda *_args: items)

    with pytest.raises(RuntimeError, match="candidate run has incomplete"):
        run_mvp.run_compare_runs(
            baseline_run_dir=baseline_dir,
            candidate_run_dir=candidate_dir,
        )
