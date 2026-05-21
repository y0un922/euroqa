"""Tests for spot-check recorder helpers."""
from __future__ import annotations

import json

import pytest

from shared.spot_check import (
    SpotCheckRecorder,
    get_current_recorder,
    reset_current_recorder,
    set_current_recorder,
    wait_for_pending_writes,
)


@pytest.mark.asyncio
async def test_spot_check_recorder_writes_jsonl(tmp_path):
    recorder = SpotCheckRecorder(
        query="What is Table 3.1?",
        query_id="query-1",
        base_dir=tmp_path,
        tag="baseline",
    )
    recorder.record(
        "query_signals",
        {
            "legacy_question_type": "parameter",
            "exact_refs": [],
            "procedural_cues": False,
        },
    )
    recorder.schedule_flush()

    await wait_for_pending_writes()

    path = tmp_path / "baseline" / "query-1.jsonl"
    payload = json.loads(path.read_text(encoding="utf-8").strip())
    assert payload["query"] == "What is Table 3.1?"
    assert payload["query_id"] == "query-1"
    assert payload["query_signals"] == {
        "legacy_question_type": "parameter",
        "exact_refs": [],
        "procedural_cues": False,
    }
    assert "question_type" not in payload


def test_current_recorder_context_var_resets():
    recorder = SpotCheckRecorder(query="q")
    token = set_current_recorder(recorder)
    try:
        assert get_current_recorder() is recorder
    finally:
        reset_current_recorder(token)

    assert get_current_recorder() is None
