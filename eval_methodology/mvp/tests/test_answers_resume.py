"""Answer checkpoint and resume behavior."""

from __future__ import annotations

from types import SimpleNamespace

from eval_methodology.mvp.loop.run_mvp import _complete
from eval_methodology.mvp.runner import answers


def _result(question: str) -> dict:
    return {
        "answer": f"answer:{question}",
        "context_chunk_ids": [question],
        "context_chunks": [{"chunk_id": question, "content": question}],
        "sources": [{"id": question}],
        "unresolved_refs": [],
        "resolved_refs": ["Ref-1"],
        "elapsed_ms": 5,
        "raw_done": {"usage": {"total_tokens": 7}},
    }


def test_generate_answers_checkpoints_resumes_and_continues(monkeypatch, tmp_path):
    items = [
        {"id": "Q1", "question": "one"},
        {"id": "Q2", "question": "two"},
        {"id": "Q3", "question": "three"},
    ]
    attempts = []

    def first_call(_url, question, *, timeout_s):
        attempts.append((question, timeout_s))
        if question == "two":
            raise RuntimeError("boom")
        return _result(question)

    monkeypatch.setattr(answers, "query_stream", first_call)
    records = answers.generate_answers(
        SimpleNamespace(stream_url="http://sidecar"),
        items,
        tmp_path,
        concurrency=2,
        retries=1,
    )
    by_id = {record["id"]: record for record in records}
    assert by_id["Q1"]["status"] == "ok"
    assert by_id["Q2"]["status"] == "error"
    assert by_id["Q3"]["usage"] == {"total_tokens": 7}
    assert len(list(tmp_path.glob("*.json"))) == 3

    resumed_calls = []

    def second_call(_url, question, *, timeout_s):
        resumed_calls.append(question)
        return _result(question)

    monkeypatch.setattr(answers, "query_stream", second_call)
    resumed = answers.generate_answers(
        SimpleNamespace(stream_url="http://sidecar"),
        items,
        tmp_path,
    )
    assert resumed_calls == ["two"]
    assert all(record["status"] == "ok" for record in resumed)


def test_baseline_cache_is_incomplete_when_any_answer_failed():
    items = [{"id": "Q1"}, {"id": "Q2"}]
    assert _complete(
        [{"Q1": {"status": "ok"}, "Q2": {"status": "ok"}}], items
    )
    assert not _complete(
        [{"Q1": {"status": "ok"}, "Q2": {"status": "error"}}], items
    )
