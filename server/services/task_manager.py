"""持久化任务队列：单 worker 串行执行 pipeline，SSE 广播进度。"""
from __future__ import annotations

import asyncio
import contextlib
import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

import structlog

logger = structlog.get_logger()
_INDEX_READY_SENTINEL = ".indexed"
_RESTART_INTERRUPTED_MESSAGE = "服务重启导致解析中断,请重试"
_STALE_CANCEL_MESSAGE = "解析卡住超过 20 分钟无进度,已中止,请重试"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class PipelineStage(str, Enum):
    PENDING = "pending"
    PARSING = "parsing"
    STRUCTURING = "structuring"
    CHUNKING = "chunking"
    SUMMARIZING = "summarizing"
    INDEXING = "indexing"
    READY = "ready"
    ERROR = "error"


_TERMINAL_STAGES = {PipelineStage.READY, PipelineStage.ERROR}


@dataclass(slots=True)
class ProgressEvent:
    doc_id: str
    stage: PipelineStage
    progress: float
    message: str = ""
    error: str | None = None
    terminal: bool = False


@dataclass(slots=True)
class TaskState:
    doc_id: str
    stage: PipelineStage = PipelineStage.PENDING
    progress: float = 0.0
    message: str = ""
    error: str | None = None
    attempts: int = 0
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)
    heartbeat_at: datetime = field(default_factory=_utcnow)


class TaskManager:
    """FIFO 任务管理器，单 worker 串行处理 pipeline 任务。"""

    _instance: TaskManager | None = None

    def __new__(cls) -> TaskManager:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._states: dict[str, TaskState] = {}
        self._subscribers: dict[str, list[asyncio.Queue[ProgressEvent]]] = {}
        self._worker_task: asyncio.Task[None] | None = None
        self._current_doc_id: str | None = None
        self._current_inner_task: asyncio.Task[dict[str, int]] | None = None
        self._watchdog_cancel_reasons: dict[str, str] = {}
        self._initialized = True

    # -- 生命周期 --

    async def start(self) -> None:
        if self._worker_task is not None and not self._worker_task.done():
            return
        from pipeline.config import PipelineConfig

        self.recover_interrupted_tasks(PipelineConfig().parsed_dir)
        self._worker_task = asyncio.create_task(
            self._worker(), name="pipeline-task-manager"
        )

    async def stop(self) -> None:
        if self._worker_task is None:
            return
        self._worker_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._worker_task
        self._worker_task = None

    # -- 公开接口 --

    def enqueue(self, doc_id: str) -> TaskState:
        """将文档加入处理队列。如果已在活跃状态则返回当前状态。"""
        existing = self._states.get(doc_id)
        if existing is not None and existing.stage not in _TERMINAL_STAGES:
            return existing

        attempts = existing.attempts + 1 if existing is not None else 1
        event = self._update_state(
            doc_id=doc_id,
            stage=PipelineStage.PENDING,
            progress=0.0,
            message="排队等待处理",
            attempts=attempts,
        )
        self._queue.put_nowait(doc_id)

        with contextlib.suppress(RuntimeError):
            asyncio.get_running_loop().create_task(self._broadcast(event))

        return self._states[doc_id]

    def get_status(self, doc_id: str) -> TaskState | None:
        return self._states.get(doc_id)

    def get_persisted_status(self, doc_id: str, parsed_dir: str) -> TaskState | None:
        """Return persisted state, with .indexed marker taking precedence."""
        state = self._state_from_ready_marker(doc_id, parsed_dir)
        if state is not None:
            self._states[doc_id] = state
            return state

        state = self._read_status_file(doc_id, parsed_dir)
        if state is not None:
            self._states[doc_id] = state
        return state

    def get_status_or_persisted(
        self,
        doc_id: str,
        parsed_dir: str,
    ) -> TaskState | None:
        """Return in-memory state or persisted status.json state."""
        state = self._states.get(doc_id)
        if state is not None:
            ready_state = self._state_from_ready_marker(doc_id, parsed_dir)
            if ready_state is not None:
                self._states[doc_id] = ready_state
                return ready_state
            if state.stage in _TERMINAL_STAGES and not self._status_path(
                doc_id, parsed_dir
            ).is_file():
                self._states.pop(doc_id, None)
                return self.get_persisted_status(doc_id, parsed_dir)
            return state
        return self.get_persisted_status(doc_id, parsed_dir)

    def subscribe(
        self,
        doc_id: str,
        parsed_dir: str | None = None,
    ) -> asyncio.Queue[ProgressEvent]:
        """订阅指定文档的进度事件流。立即推送当前状态。"""
        queue: asyncio.Queue[ProgressEvent] = asyncio.Queue()
        self._subscribers.setdefault(doc_id, []).append(queue)

        state = (
            self.get_status_or_persisted(doc_id, parsed_dir)
            if parsed_dir is not None
            else self._states.get(doc_id)
        )
        if state is not None:
            queue.put_nowait(ProgressEvent(
                doc_id=state.doc_id,
                stage=state.stage,
                progress=state.progress,
                message=state.message,
                error=state.error,
                terminal=state.stage in _TERMINAL_STAGES,
            ))
        return queue

    def unsubscribe(self, doc_id: str, queue: asyncio.Queue[ProgressEvent]) -> None:
        subscribers = self._subscribers.get(doc_id)
        if not subscribers:
            return
        with contextlib.suppress(ValueError):
            subscribers.remove(queue)
        if not subscribers:
            self._subscribers.pop(doc_id, None)

    # -- 内部 --

    def recover_interrupted_tasks(self, parsed_dir: str) -> None:
        """Mark non-terminal persisted tasks as interrupted after service restart."""
        parsed_root = Path(parsed_dir)
        if not parsed_root.is_dir():
            return

        for status_path in parsed_root.glob("*/status.json"):
            doc_id = status_path.parent.name
            ready_state = self._state_from_ready_marker(doc_id, parsed_dir)
            if ready_state is not None:
                self._states[doc_id] = ready_state
                self._write_status_file(ready_state, parsed_dir)
                continue

            state = self._read_status_file(doc_id, parsed_dir)
            if state is None or state.stage in _TERMINAL_STAGES:
                if state is not None:
                    self._states[doc_id] = state
                continue

            event = self._update_state(
                doc_id=doc_id,
                stage=PipelineStage.ERROR,
                progress=1.0,
                message=_RESTART_INTERRUPTED_MESSAGE,
                error=_RESTART_INTERRUPTED_MESSAGE,
                attempts=state.attempts + 1,
                parsed_dir=parsed_dir,
            )
            with contextlib.suppress(RuntimeError):
                asyncio.get_running_loop().create_task(self._broadcast(event))

    async def _worker(self) -> None:
        from pipeline.config import PipelineConfig
        from server.services.pipeline_runner import run_single_document

        while True:
            doc_id = await self._queue.get()
            try:
                pipeline_config = PipelineConfig()
                parsed_dir = pipeline_config.parsed_dir

                async def _on_progress(
                    stage: PipelineStage | str,
                    progress: float,
                    message: str,
                ) -> None:
                    stage_value = (
                        stage if isinstance(stage, PipelineStage)
                        else PipelineStage(str(stage))
                    )
                    event = self._update_state(
                        doc_id=doc_id,
                        stage=stage_value,
                        progress=progress,
                        message=message,
                        parsed_dir=parsed_dir,
                    )
                    await self._broadcast(event)

                start_event = self._update_state(
                    doc_id=doc_id,
                    stage=PipelineStage.PARSING,
                    progress=0.01,
                    message="正在解析 PDF",
                    parsed_dir=parsed_dir,
                )
                await self._broadcast(start_event)

                inner_task = asyncio.create_task(
                    run_single_document(
                        doc_id=doc_id,
                        pipeline_config=pipeline_config,
                        on_progress=_on_progress,
                    ),
                    name=f"pipeline-run-{doc_id}",
                )
                self._current_doc_id = doc_id
                self._current_inner_task = inner_task
                watchdog_task = asyncio.create_task(
                    self._watch_current_task(doc_id, inner_task, pipeline_config),
                    name=f"pipeline-watchdog-{doc_id}",
                )
                try:
                    await inner_task
                except asyncio.CancelledError:
                    cancel_reason = self._watchdog_cancel_reasons.pop(doc_id, None)
                    if cancel_reason is None:
                        if not inner_task.done():
                            inner_task.cancel()
                            with contextlib.suppress(asyncio.CancelledError):
                                await inner_task
                        raise
                    event = self._update_state(
                        doc_id=doc_id,
                        stage=PipelineStage.ERROR,
                        progress=1.0,
                        message=cancel_reason,
                        error=cancel_reason,
                        parsed_dir=parsed_dir,
                    )
                    await self._broadcast(event)
                finally:
                    watchdog_task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await watchdog_task
                    self._current_doc_id = None
                    self._current_inner_task = None
                # run_single_document emits the final READY event itself.
            except asyncio.CancelledError:
                if (
                    self._current_doc_id == doc_id
                    and self._current_inner_task is not None
                    and not self._current_inner_task.done()
                ):
                    self._current_inner_task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await self._current_inner_task
                raise
            except Exception as exc:
                logger.exception("pipeline_task_failed", doc_id=doc_id)
                parsed_dir = (
                    pipeline_config.parsed_dir
                    if "pipeline_config" in locals()
                    else PipelineConfig().parsed_dir
                )
                event = self._update_state(
                    doc_id=doc_id,
                    stage=PipelineStage.ERROR,
                    progress=1.0,
                    message=str(exc),
                    error=str(exc),
                    parsed_dir=parsed_dir,
                )
                await self._broadcast(event)
            finally:
                self._queue.task_done()

    async def _watch_current_task(
        self,
        doc_id: str,
        inner_task: asyncio.Task[dict[str, int]],
        pipeline_config,
    ) -> None:
        interval = max(0.1, float(pipeline_config.parse_watchdog_interval_seconds))
        stale_timeout = float(pipeline_config.parse_stale_timeout_seconds)
        while not inner_task.done():
            await asyncio.sleep(interval)
            if inner_task.done():
                return
            if self._current_doc_id != doc_id:
                return
            state = self._states.get(doc_id)
            if state is None:
                continue
            stale_seconds = (_utcnow() - state.heartbeat_at).total_seconds()
            if stale_seconds > stale_timeout:
                self._watchdog_cancel_reasons[doc_id] = _STALE_CANCEL_MESSAGE
                inner_task.cancel()
                return

    async def _broadcast(self, event: ProgressEvent) -> None:
        for queue in list(self._subscribers.get(event.doc_id, [])):
            queue.put_nowait(event)

    def _update_state(
        self,
        doc_id: str,
        stage: PipelineStage,
        progress: float,
        message: str,
        error: str | None = None,
        attempts: int | None = None,
        parsed_dir: str | None = None,
    ) -> ProgressEvent:
        now = _utcnow()
        state = self._states.get(doc_id)
        if state is None:
            state = TaskState(doc_id=doc_id, created_at=now, updated_at=now)
            self._states[doc_id] = state

        state.stage = stage
        state.progress = max(0.0, min(1.0, progress))
        state.message = message
        state.error = error
        if attempts is not None:
            state.attempts = attempts
        state.updated_at = now
        state.heartbeat_at = now

        if parsed_dir is None:
            from pipeline.config import PipelineConfig

            parsed_dir = PipelineConfig().parsed_dir
        self._write_status_file(state, parsed_dir)

        return ProgressEvent(
            doc_id=doc_id,
            stage=stage,
            progress=state.progress,
            message=message,
            error=error,
            terminal=stage in _TERMINAL_STAGES,
        )

    def _status_path(self, doc_id: str, parsed_dir: str) -> Path:
        return Path(parsed_dir) / doc_id / "status.json"

    def _state_from_ready_marker(self, doc_id: str, parsed_dir: str) -> TaskState | None:
        marker = Path(parsed_dir) / doc_id / _INDEX_READY_SENTINEL
        if not marker.is_file():
            return None
        now = _utcnow()
        existing = self._states.get(doc_id) or self._read_status_file(doc_id, parsed_dir)
        attempts = existing.attempts if existing is not None else 0
        created_at = existing.created_at if existing is not None else now
        return TaskState(
            doc_id=doc_id,
            stage=PipelineStage.READY,
            progress=1.0,
            message="解析完成",
            error=None,
            attempts=attempts,
            created_at=created_at,
            updated_at=now,
            heartbeat_at=now,
        )

    def _read_status_file(self, doc_id: str, parsed_dir: str) -> TaskState | None:
        path = self._status_path(doc_id, parsed_dir)
        if not path.is_file():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return TaskState(
                doc_id=str(data.get("doc_id") or doc_id),
                stage=PipelineStage(str(data.get("stage") or PipelineStage.PENDING.value)),
                progress=float(data.get("progress") or 0.0),
                message=str(data.get("message") or ""),
                error=data.get("error"),
                attempts=int(data.get("attempts") or 0),
                created_at=self._parse_datetime(data.get("created_at")),
                updated_at=self._parse_datetime(data.get("updated_at")),
                heartbeat_at=self._parse_datetime(data.get("heartbeat_at")),
            )
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            logger.warning("document_status_read_failed", doc_id=doc_id, path=str(path))
            return None

    def _write_status_file(self, state: TaskState, parsed_dir: str) -> None:
        path = self._status_path(state.doc_id, parsed_dir)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_name(f"{path.name}.tmp")
        tmp_path.write_text(
            json.dumps(
                {
                    "doc_id": state.doc_id,
                    "stage": state.stage.value,
                    "progress": state.progress,
                    "message": state.message,
                    "error": state.error,
                    "attempts": state.attempts,
                    "created_at": self._format_datetime(state.created_at),
                    "updated_at": self._format_datetime(state.updated_at),
                    "heartbeat_at": self._format_datetime(state.heartbeat_at),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        os.replace(tmp_path, path)

    def _parse_datetime(self, value: object) -> datetime:
        if isinstance(value, str) and value:
            with contextlib.suppress(ValueError):
                return datetime.fromisoformat(value.replace("Z", "+00:00"))
        return _utcnow()

    def _format_datetime(self, value: datetime) -> str:
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def get_task_manager() -> TaskManager:
    """获取 TaskManager 单例。"""
    return TaskManager()
