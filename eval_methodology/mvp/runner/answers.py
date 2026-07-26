"""Concurrent answer generation with per-question checkpoints."""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from eval_methodology.mvp.runner.client import query_stream


def _write_record(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def _generate_one(
    handle: Any,
    item: dict[str, Any],
    *,
    retries: int,
    timeout_s: float,
) -> dict[str, Any]:
    qid = str(item["id"])
    question = str(item["question"])
    started = time.monotonic()
    last_error: Exception | None = None
    for _attempt in range(retries + 1):
        try:
            result = query_stream(handle.stream_url, question, timeout_s=timeout_s)
            raw_done = result.get("raw_done") or {}
            return {
                "id": qid,
                "question": question,
                "answer": result.get("answer") or "",
                "context_chunk_ids": result.get("context_chunk_ids") or [],
                "context_chunks": result.get("context_chunks") or [],
                "sources": result.get("sources") or [],
                "unresolved_refs": result.get("unresolved_refs") or [],
                "resolved_refs": result.get("resolved_refs") or [],
                "elapsed_ms": result.get("elapsed_ms")
                or int((time.monotonic() - started) * 1000),
                "usage": raw_done.get("usage") if isinstance(raw_done, dict) else None,
                "status": "ok",
                "error": None,
            }
        except Exception as exc:  # noqa: BLE001
            last_error = exc
    assert last_error is not None
    return {
        "id": qid,
        "question": question,
        "answer": "",
        "context_chunk_ids": [],
        "context_chunks": [],
        "sources": [],
        "unresolved_refs": [],
        "resolved_refs": [],
        "elapsed_ms": int((time.monotonic() - started) * 1000),
        "usage": None,
        "status": "error",
        "error": {
            "type": type(last_error).__name__,
            "message": str(last_error),
        },
    }


def generate_answers(
    handle: Any,
    items: list[dict[str, Any]],
    run_dir: Path,
    *,
    concurrency: int = 2,
    retries: int = 1,
    timeout_s: float = 180.0,
    on_record: Callable[[dict[str, Any]], None] | None = None,
) -> list[dict[str, Any]]:
    """Generate answers and checkpoint every completed question.

    Args:
        handle: Running sidecar handle exposing ``stream_url``.
        items: Dataset items containing ``id`` and ``question``.
        run_dir: Directory containing one ``<qid>.json`` per question.
        concurrency: Maximum concurrent requests.
        retries: Retry count after the first failed attempt.
        timeout_s: Per-request timeout in seconds.
        on_record: Optional callback invoked after each checkpoint write.

    Returns:
        Records ordered like ``items``.
    """
    run_dir.mkdir(parents=True, exist_ok=True)
    records = load_answers(run_dir)
    pending = [item for item in items if records.get(str(item["id"]), {}).get("status") != "ok"]

    if pending:
        with ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
            futures = {
                pool.submit(
                    _generate_one,
                    handle,
                    item,
                    retries=max(0, retries),
                    timeout_s=timeout_s,
                ): str(item["id"])
                for item in pending
            }
            for future in as_completed(futures):
                record = future.result()
                _write_record(run_dir / f"{record['id']}.json", record)
                records[record["id"]] = record
                if on_record:
                    on_record(record)

    return [records[str(item["id"])] for item in items if str(item["id"]) in records]


def load_answers(run_dir: Path) -> dict[str, dict[str, Any]]:
    """Load answer checkpoints keyed by question id.

    Args:
        run_dir: Directory containing per-question JSON records.

    Returns:
        Mapping from qid to record. Invalid non-record JSON files are ignored.
    """
    if not run_dir.is_dir():
        return {}
    out: dict[str, dict[str, Any]] = {}
    for path in sorted(run_dir.glob("*.json")):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(record, dict):
            continue
        qid = str(record.get("id") or path.stem)
        out[qid] = record
    return out
