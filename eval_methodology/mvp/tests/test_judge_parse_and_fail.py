"""Single judge parsing, failure, cache, and model-pin tests."""

from __future__ import annotations

import pytest

from eval_methodology.mvp.metrics.judges import judge
from eval_methodology.mvp.metrics.judges.cache import JudgeCache
from eval_methodology.mvp.metrics import run_eval


@pytest.fixture(autouse=True)
def _no_disk_pin(monkeypatch):
    """Keep tests from writing to the real resolved-model pin file."""
    monkeypatch.delenv("MVP_JUDGE_FAMILY", raising=False)
    monkeypatch.delenv("MVP_JUDGE_MODEL", raising=False)
    monkeypatch.setattr(judge, "pin_resolved_model", lambda *_a, **_k: None)


def test_judge_computes_scores_and_hits_cache(monkeypatch, tmp_path):
    calls = []

    def fake_run(*_args, **_kwargs):
        calls.append(1)
        return {
            "claims": [
                {"text": "a", "supported": True},
                {"text": "b", "supported": False},
            ],
            "citations": [
                {"ref_label": "Ref-1", "valid": True},
                {"ref_label": "Ref-2", "valid": False},
            ],
            "_resolved_model": "claude-test",
        }

    monkeypatch.setattr(judge, "resolve_claude_model_id", lambda: "claude-test")
    monkeypatch.setattr(judge, "run_claude_json", fake_run)
    cache = JudgeCache(tmp_path)
    kwargs = {
        "question": "q",
        "answer": "answer [Ref-1]",
        "context_chunks": [{"chunk_id": "c1", "content": "ctx"}],
        "cache": cache,
    }
    first = judge.judge_question(**kwargs)
    second = judge.judge_question(**kwargs)
    assert first.faith == 0.5
    assert first.citp == 0.5
    assert second == first
    assert len(calls) == 1


def test_judge_no_citations_scores_zero(monkeypatch, tmp_path):
    monkeypatch.setattr(judge, "resolve_claude_model_id", lambda: "claude-test")
    monkeypatch.setattr(
        judge,
        "run_claude_json",
        lambda *_args, **_kwargs: {
            "claims": [{"text": "a", "supported": True}],
            "citations": [],
            "_resolved_model": "claude-test",
        },
    )
    result = judge.judge_question(
        question="q",
        answer="non-empty answer",
        context_chunks=[],
        cache=JudgeCache(tmp_path),
    )
    assert result.faith == 1.0
    assert result.citp == 0.0


def test_judge_failure_returns_null_metrics(monkeypatch, tmp_path):
    monkeypatch.setattr(judge, "resolve_claude_model_id", lambda: "claude-test")

    def fail(*_args, **_kwargs):
        raise RuntimeError("judge down")

    monkeypatch.setattr(judge, "run_claude_json", fail)
    result = judge.judge_question(
        question="q",
        answer="answer",
        context_chunks=[],
        cache=JudgeCache(tmp_path),
    )
    assert result.judge_failed
    assert result.faith is None
    assert result.citp is None
    assert "judge down" in result.fail_reason


def test_judge_model_pin_mismatch_fails(monkeypatch, tmp_path):
    monkeypatch.setenv("MVP_JUDGE_MODEL", "claude-pinned")
    seen_models = []

    def fake_run(*_args, **kwargs):
        seen_models.append(kwargs.get("model"))
        return {
            "claims": [{"text": "a", "supported": True}],
            "citations": [],
            "_resolved_model": "some-other-model",
        }

    monkeypatch.setattr(judge, "run_claude_json", fake_run)
    result = judge.judge_question(
        question="q",
        answer="answer",
        context_chunks=[],
        cache=JudgeCache(tmp_path),
    )
    assert seen_models and all(model == "claude-pinned" for model in seen_models)
    assert result.judge_failed
    assert "pin mismatch" in result.fail_reason


def test_judge_model_pin_tolerates_suffix_and_caches(monkeypatch, tmp_path):
    monkeypatch.setenv("MVP_JUDGE_MODEL", "claude-pinned")
    calls = []

    def fake_run(*_args, **_kwargs):
        calls.append(1)
        return {
            "claims": [{"text": "a", "supported": True}],
            "citations": [],
            "_resolved_model": "claude-pinned[1m]",
        }

    monkeypatch.setattr(judge, "run_claude_json", fake_run)
    cache = JudgeCache(tmp_path)
    kwargs = {
        "question": "q",
        "answer": "answer",
        "context_chunks": [],
        "cache": cache,
    }
    first = judge.judge_question(**kwargs)
    second = judge.judge_question(**kwargs)
    assert not first.judge_failed
    assert first.resolved_model == "claude-pinned[1m]"
    assert second == first
    assert len(calls) == 1


def test_stale_real_model_id_gets_no_alias(monkeypatch, tmp_path):
    """A result judged by a new model must not be reachable under a stale pin."""
    calls = []

    def fake_run(*_args, **_kwargs):
        calls.append(1)
        return {
            "claims": [{"text": "a", "supported": True}],
            "citations": [],
            "_resolved_model": "new-model",
        }

    monkeypatch.setattr(judge, "resolve_claude_model_id", lambda: "old-model")
    monkeypatch.setattr(judge, "run_claude_json", fake_run)
    cache = JudgeCache(tmp_path)
    kwargs = {
        "question": "q",
        "answer": "answer",
        "context_chunks": [],
        "cache": cache,
    }
    judge.judge_question(**kwargs)
    judge.judge_question(**kwargs)
    assert len(calls) == 2


def test_unresolved_placeholder_alias_still_written(monkeypatch, tmp_path):
    calls = []

    def fake_run(*_args, **_kwargs):
        calls.append(1)
        return {
            "claims": [{"text": "a", "supported": True}],
            "citations": [],
            "_resolved_model": "real-model",
        }

    monkeypatch.setattr(judge, "resolve_claude_model_id", lambda: "claude-unresolved")
    monkeypatch.setattr(judge, "run_claude_json", fake_run)
    cache = JudgeCache(tmp_path)
    kwargs = {
        "question": "q",
        "answer": "answer",
        "context_chunks": [],
        "cache": cache,
    }
    judge.judge_question(**kwargs)
    judge.judge_question(**kwargs)
    assert len(calls) == 1


def test_judge_prompt_includes_all_chunks_in_full():
    chunks = [
        {"chunk_id": f"c{i}", "content": f"chunk-{i}-" + "x" * 1200}
        for i in range(1, 41)
    ]
    prompt = judge._judge_prompt("q", "answer [Ref-40]", chunks)
    assert "[Ref-40]" in prompt
    assert "chunk-40-" + "x" * 1200 in prompt  # no per-chunk truncation
    assert "未展示" not in prompt


def test_judge_prompt_declares_omitted_refs_over_budget(monkeypatch):
    monkeypatch.setattr(judge, "JUDGE_MAX_TOTAL_CONTEXT_CHARS", 100)
    chunks = [
        {"chunk_id": "c1", "content": "a" * 60},
        {"chunk_id": "c2", "content": "b" * 60},
        {"chunk_id": "c3", "content": "c" * 60},
    ]
    prompt = judge._judge_prompt("q", "answer", chunks)
    assert "a" * 60 in prompt
    assert "b" * 60 not in prompt
    assert "Ref-2 至 Ref-3" in prompt and "未展示" in prompt


def test_no_judge_skips_cli_and_keeps_diagnostics(monkeypatch):
    monkeypatch.setattr(
        run_eval,
        "judge_question",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("judge called")),
    )
    item = {
        "id": "Q1",
        "question": "q",
        "gold": {
            "gold_claim_status": "supported",
            "evidence": [
                {
                    "evidence_id": "e1",
                    "quote": "a sufficiently long exact evidence quotation",
                }
            ],
        },
    }
    answer = {
        "id": "Q1",
        "status": "ok",
        "answer": "answer",
        "context_chunk_ids": ["c1"],
        "context_chunks": [
            {"chunk_id": "c1", "content": "a sufficiently long exact evidence quotation"}
        ],
        "unresolved_refs": [],
        "resolved_refs": [],
        "elapsed_ms": 1,
    }
    result = run_eval.metrics_from_answers(
        {"Q1": answer},
        [item],
        use_llm_judge=False,
    )
    metric = result["per_question"][0]
    assert metric["faith"] is None and metric["citp"] is None
    assert metric["crec"] == 1.0
    assert result["judge_models"] == []
