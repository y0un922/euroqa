"""Spot-check JSONL recording helpers for retrieval pipeline diagnostics."""
from __future__ import annotations

import asyncio
import json
import os
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import structlog

logger = structlog.get_logger()

_CURRENT_RECORDER: ContextVar["SpotCheckRecorder | None"] = ContextVar(
    "spot_check_recorder",
    default=None,
)
_PENDING_TASKS: set[asyncio.Task[None]] = set()


def is_spot_check_enabled() -> bool:
    """Return whether spot-check recording should be enabled."""
    value = os.getenv("SPOT_CHECK_ENABLED", "").strip().lower()
    return value in {"1", "true", "yes", "on"}


def get_current_recorder() -> "SpotCheckRecorder | None":
    """Return current request recorder, if any."""
    return _CURRENT_RECORDER.get()


def set_current_recorder(recorder: "SpotCheckRecorder | None"):
    """Set the current recorder context var and return its reset token."""
    return _CURRENT_RECORDER.set(recorder)


def reset_current_recorder(token: Any) -> None:
    """Reset the current recorder context var."""
    _CURRENT_RECORDER.reset(token)


def merge_spot_check_usage(usage: dict[str, int]) -> None:
    """Accumulate LLM token usage into the active spot-check recorder."""
    recorder = get_current_recorder()
    if recorder is None:
        return
    existing = recorder.data.get("usage")
    if existing is None:
        recorder.data["usage"] = dict(usage)
    else:
        for key, val in usage.items():
            existing[key] = existing.get(key, 0) + val


def record_spot_check(field: str, value: Any) -> None:
    """Record a field on the active spot-check recorder, if enabled."""
    recorder = get_current_recorder()
    if recorder is not None:
        recorder.record(field, value)


def flush_current_recorder() -> None:
    """Schedule an async flush for the current recorder, if present."""
    recorder = get_current_recorder()
    if recorder is not None:
        recorder.schedule_flush()


async def wait_for_pending_writes() -> None:
    """Wait for pending spot-check file writes."""
    if _PENDING_TASKS:
        await asyncio.gather(*list(_PENDING_TASKS), return_exceptions=True)


class SpotCheckRecorder:
    """Collect and asynchronously write one query spot-check JSONL record."""

    def __init__(
        self,
        *,
        query: str,
        query_id: str | None = None,
        base_dir: str | Path | None = None,
        tag: str | None = None,
    ) -> None:
        self.query = query
        self.query_id = query_id or str(uuid4())
        self.tag = tag or os.getenv("SPOT_CHECK_TAG") or datetime.now().strftime("%Y%m%d")
        self.base_dir = Path(base_dir or os.getenv("SPOT_CHECK_DIR") or "logs/spot_check")
        self.data: dict[str, Any] = {
            "query": query,
            "query_id": self.query_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self._flushed = False

    @property
    def path(self) -> Path:
        return self.base_dir / self.tag / f"{self.query_id}.jsonl"

    def record(self, field: str, value: Any) -> None:
        self.data[field] = value

    async def flush(self) -> None:
        if self._flushed:
            return
        self._flushed = True
        await asyncio.to_thread(self._write_sync)

    def schedule_flush(self) -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            self._write_sync()
            return

        task = loop.create_task(self.flush())
        _PENDING_TASKS.add(task)
        task.add_done_callback(_PENDING_TASKS.discard)

    def _write_sync(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(self.data, ensure_ascii=False, default=str))
                handle.write("\n")
        except Exception:
            logger.warning("spot_check_write_failed", path=str(self.path), exc_info=True)
