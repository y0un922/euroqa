"""Tests for persistent document parse task state."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from server.services import task_manager as task_manager_module
from server.services.task_manager import PipelineStage, TaskManager


def _new_manager() -> TaskManager:
    manager = TaskManager()
    manager._queue = asyncio.Queue()
    manager._states = {}
    manager._subscribers = {}
    manager._worker_task = None
    manager._current_doc_id = None
    manager._current_inner_task = None
    manager._watchdog_cancel_reasons = {}
    manager._capacity = 100
    return manager


def _write_status(
    parsed_dir: Path,
    doc_id: str,
    *,
    stage: str,
    attempts: int = 0,
) -> None:
    doc_dir = parsed_dir / doc_id
    doc_dir.mkdir(parents=True)
    (doc_dir / "status.json").write_text(
        json.dumps(
            {
                "doc_id": doc_id,
                "stage": stage,
                "progress": 0.5,
                "message": "old message",
                "error": None,
                "attempts": attempts,
                "created_at": "2026-05-29T00:00:00Z",
                "updated_at": "2026-05-29T00:00:00Z",
                "heartbeat_at": "2026-05-29T00:00:00Z",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def test_update_state_persists_status_json_atomically(tmp_path: Path):
    parsed_dir = tmp_path / "parsed"
    manager = _new_manager()

    manager._update_state(
        doc_id="DOC_1",
        stage=PipelineStage.PARSING,
        progress=0.2,
        message="正在解析 PDF",
        attempts=1,
        parsed_dir=str(parsed_dir),
    )

    status_path = parsed_dir / "DOC_1" / "status.json"
    assert status_path.is_file()
    assert not (parsed_dir / "DOC_1" / "status.json.tmp").exists()
    payload = json.loads(status_path.read_text(encoding="utf-8"))
    assert payload["doc_id"] == "DOC_1"
    assert payload["stage"] == "parsing"
    assert payload["message"] == "正在解析 PDF"
    assert payload["attempts"] == 1
    assert payload["heartbeat_at"]


def test_recover_interrupted_tasks_marks_non_terminal_error(tmp_path: Path):
    parsed_dir = tmp_path / "parsed"
    _write_status(parsed_dir, "DOC_1", stage="summarizing", attempts=2)
    manager = _new_manager()

    manager.recover_interrupted_tasks(str(parsed_dir))

    state = manager.get_status("DOC_1")
    assert state is not None
    assert state.stage == PipelineStage.ERROR
    assert state.error == "服务重启导致解析中断,请重试"
    assert state.attempts == 3
    payload = json.loads(
        (parsed_dir / "DOC_1" / "status.json").read_text(encoding="utf-8")
    )
    assert payload["stage"] == "error"
    assert payload["attempts"] == 3


def test_recover_interrupted_tasks_prefers_index_marker_ready(tmp_path: Path):
    parsed_dir = tmp_path / "parsed"
    _write_status(parsed_dir, "DOC_1", stage="indexing", attempts=2)
    (parsed_dir / "DOC_1" / ".indexed").write_text("{}", encoding="utf-8")
    manager = _new_manager()

    manager.recover_interrupted_tasks(str(parsed_dir))

    state = manager.get_status("DOC_1")
    assert state is not None
    assert state.stage == PipelineStage.READY
    assert state.error is None
    assert state.attempts == 2
    payload = json.loads(
        (parsed_dir / "DOC_1" / "status.json").read_text(encoding="utf-8")
    )
    assert payload["stage"] == "ready"


def test_get_status_or_persisted_reads_status_json_and_prefers_index_marker(
    tmp_path: Path,
):
    parsed_dir = tmp_path / "parsed"
    _write_status(parsed_dir, "DOC_1", stage="error", attempts=1)
    manager = _new_manager()

    state = manager.get_status_or_persisted("DOC_1", str(parsed_dir))
    assert state is not None
    assert state.stage == PipelineStage.ERROR

    (parsed_dir / "DOC_1" / ".indexed").write_text("{}", encoding="utf-8")
    ready_state = manager.get_status_or_persisted("DOC_1", str(parsed_dir))
    assert ready_state is not None
    assert ready_state.stage == PipelineStage.READY


@pytest.mark.asyncio
async def test_watchdog_cancels_stale_doc_and_worker_continues(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    parsed_dir = tmp_path / "parsed"
    pdf_dir = tmp_path / "pdfs"
    manager = _new_manager()
    processed: list[str] = []
    first_started = asyncio.Event()

    class _Config:
        parse_watchdog_interval_seconds = 0.01
        parse_stale_timeout_seconds = 0.0

        def __init__(self):
            self.parsed_dir = str(parsed_dir)
            self.pdf_dir = str(pdf_dir)

    async def fake_run_single_document(doc_id, pipeline_config, on_progress=None):
        if doc_id == "stale":
            first_started.set()
            await asyncio.sleep(60)
        processed.append(doc_id)
        if on_progress is not None:
            await on_progress("ready", 1.0, "完成")
        return {"chunks": 1}

    monkeypatch.setattr(task_manager_module, "TaskManager", lambda: manager)
    monkeypatch.setattr(
        "pipeline.config.PipelineConfig",
        lambda: _Config(),
    )
    monkeypatch.setattr(
        "server.services.pipeline_runner.run_single_document",
        fake_run_single_document,
    )

    await manager.start()
    manager.enqueue("stale")
    await first_started.wait()
    manager.enqueue("next")

    for _ in range(200):
        stale_state = manager.get_status("stale")
        next_state = manager.get_status("next")
        if (
            stale_state is not None
            and stale_state.stage == PipelineStage.ERROR
            and next_state is not None
            and next_state.stage == PipelineStage.READY
        ):
            break
        await asyncio.sleep(0.01)
    await manager.stop()

    stale_state = manager.get_status("stale")
    next_state = manager.get_status("next")
    assert stale_state is not None
    assert stale_state.stage == PipelineStage.ERROR
    assert stale_state.error == "解析卡住超过 20 分钟无进度,已中止,请重试"
    assert next_state is not None
    assert next_state.stage == PipelineStage.READY
    assert processed == ["next"]


def test_queue_stats_and_capacity_limit(tmp_path: Path):
    manager = _new_manager()
    manager.set_capacity(2)
    parsed_dir = str(tmp_path / "parsed")

    manager.enqueue("DOC_1")
    manager.enqueue("DOC_2")
    stats = manager.get_queue_stats()
    assert stats["capacity"] == 2
    assert stats["used"] == 2
    assert stats["remaining"] == 0
    assert stats["queued"] == 2
    assert stats["active"] == 0
    assert stats["max_files_per_request"] == 20

    # Already-active doc does not consume a new slot.
    again = manager.enqueue("DOC_1")
    assert again.doc_id == "DOC_1"
    assert manager.count_unfinished() == 2

    with pytest.raises(RuntimeError, match="parse queue is full"):
        manager.enqueue("DOC_3")

    # Mark DOC_1 complete -> frees a slot.
    manager._update_state(
        doc_id="DOC_1",
        stage=PipelineStage.READY,
        progress=1.0,
        message="done",
        parsed_dir=parsed_dir,
    )
    assert manager.remaining_slots() == 1
    manager.enqueue("DOC_3")
    assert manager.count_unfinished() == 2
