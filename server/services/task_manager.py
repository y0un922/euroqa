"""内存任务队列：单 worker 串行执行 pipeline，SSE 广播进度。"""
from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

import structlog

logger = structlog.get_logger()


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
    error: str | None = None
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)


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
        self._initialized = True

    # -- 生命周期 --

    async def start(self) -> None:
        if self._worker_task is not None and not self._worker_task.done():
            return
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

        event = self._update_state(
            doc_id=doc_id,
            stage=PipelineStage.PENDING,
            progress=0.0,
            message="排队等待处理",
        )
        self._queue.put_nowait(doc_id)

        with contextlib.suppress(RuntimeError):
            asyncio.get_running_loop().create_task(self._broadcast(event))

        return self._states[doc_id]

    def get_status(self, doc_id: str) -> TaskState | None:
        return self._states.get(doc_id)

    def subscribe(self, doc_id: str) -> asyncio.Queue[ProgressEvent]:
        """订阅指定文档的进度事件流。立即推送当前状态。"""
        queue: asyncio.Queue[ProgressEvent] = asyncio.Queue()
        self._subscribers.setdefault(doc_id, []).append(queue)

        state = self._states.get(doc_id)
        if state is not None:
            queue.put_nowait(ProgressEvent(
                doc_id=state.doc_id,
                stage=state.stage,
                progress=state.progress,
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

    async def _worker(self) -> None:
        from pipeline.config import PipelineConfig
        from server.services.pipeline_runner import run_single_document

        while True:
            doc_id = await self._queue.get()
            try:
                pipeline_config = PipelineConfig()

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
                    )
                    await self._broadcast(event)

                await run_single_document(
                    doc_id=doc_id,
                    pipeline_config=pipeline_config,
                    on_progress=_on_progress,
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.exception("pipeline_task_failed", doc_id=doc_id)
                event = self._update_state(
                    doc_id=doc_id,
                    stage=PipelineStage.ERROR,
                    progress=1.0,
                    message=str(exc),
                    error=str(exc),
                )
                await self._broadcast(event)
            finally:
                self._queue.task_done()

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
    ) -> ProgressEvent:
        now = _utcnow()
        state = self._states.get(doc_id)
        if state is None:
            state = TaskState(doc_id=doc_id, created_at=now, updated_at=now)
            self._states[doc_id] = state

        state.stage = stage
        state.progress = max(0.0, min(1.0, progress))
        state.error = error
        state.updated_at = now

        return ProgressEvent(
            doc_id=doc_id,
            stage=stage,
            progress=state.progress,
            message=message,
            error=error,
            terminal=stage in _TERMINAL_STAGES,
        )


def get_task_manager() -> TaskManager:
    """获取 TaskManager 单例。"""
    return TaskManager()
