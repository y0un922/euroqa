from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class ToolSubStep:
    tool_name: str
    step_id: str
    status: str
    title: str
    summary: str
    metadata: dict = field(default_factory=dict)
    elapsed_ms: int = 0
    parent_step_id: str | None = None


@runtime_checkable
class ToolProgressCallback(Protocol):
    async def on_tool_sub_step(self, step: ToolSubStep) -> None:
        """Receive one observable tool sub-step event."""


class ToolProgressEmitter:
    def __init__(
        self,
        tool_name: str,
        callback: ToolProgressCallback | None,
    ) -> None:
        self.tool_name = tool_name
        self.callback = callback
        self._step_starts: dict[str, float] = {}

    async def start(
        self,
        step_id: str,
        title: str,
        summary: str = "",
        parent_step_id: str | None = None,
    ) -> None:
        self._step_starts[step_id] = time.perf_counter()
        await self._emit(
            ToolSubStep(
                tool_name=self.tool_name,
                step_id=step_id,
                status="running",
                title=title,
                summary=summary,
                parent_step_id=parent_step_id,
            )
        )

    async def complete(
        self,
        step_id: str,
        title: str,
        summary: str,
        metadata: dict | None = None,
        parent_step_id: str | None = None,
    ) -> None:
        started_at = self._step_starts.pop(step_id, None)
        elapsed_ms = (
            int((time.perf_counter() - started_at) * 1000)
            if started_at is not None
            else 0
        )
        await self._emit(
            ToolSubStep(
                tool_name=self.tool_name,
                step_id=step_id,
                status="completed",
                title=title,
                summary=summary,
                metadata=metadata or {},
                elapsed_ms=elapsed_ms,
                parent_step_id=parent_step_id,
            )
        )

    async def skip(
        self,
        step_id: str,
        title: str,
        summary: str,
        parent_step_id: str | None = None,
    ) -> None:
        await self._emit(
            ToolSubStep(
                tool_name=self.tool_name,
                step_id=step_id,
                status="skipped",
                title=title,
                summary=summary,
                elapsed_ms=0,
                parent_step_id=parent_step_id,
            )
        )

    async def _emit(self, step: ToolSubStep) -> None:
        if self.callback is None:
            return
        try:
            await self.callback.on_tool_sub_step(step)
        except Exception as exc:
            logger.warning(
                "tool_progress_callback_failed",
                tool_name=step.tool_name,
                step_id=step.step_id,
                status=step.status,
                error_type=type(exc).__name__,
                error=str(exc),
            )


class _NullEmitter:
    async def start(
        self,
        step_id: str,
        title: str,
        summary: str = "",
        parent_step_id: str | None = None,
    ) -> None:
        return None

    async def complete(
        self,
        step_id: str,
        title: str,
        summary: str,
        metadata: dict | None = None,
        parent_step_id: str | None = None,
    ) -> None:
        return None

    async def skip(
        self,
        step_id: str,
        title: str,
        summary: str,
        parent_step_id: str | None = None,
    ) -> None:
        return None


RETRIEVE_STEPS = {
    "query_understanding": {
        "title": "理解问题",
        "icon": "brain",
        "order": 10,
    },
    "metadata_probe": {
        "title": "元数据定向检索",
        "icon": "target",
        "order": 20,
        "parent": "hybrid_search",
    },
    "hybrid_search": {
        "title": "混合检索",
        "icon": "search",
        "order": 30,
    },
    "vector_search": {
        "title": "向量检索",
        "icon": "layers",
        "order": 40,
        "parent": "hybrid_search",
    },
    "bm25_search": {
        "title": "BM25 检索",
        "icon": "list-search",
        "order": 50,
        "parent": "hybrid_search",
    },
    "fusion_rerank": {
        "title": "融合重排",
        "icon": "shuffle",
        "order": 60,
        "parent": "hybrid_search",
    },
    "parent_retrieval": {
        "title": "上下文扩展",
        "icon": "file-stack",
        "order": 70,
    },
    "cross_ref_closure": {
        "title": "交叉引用补齐",
        "icon": "link",
        "order": 80,
    },
    "guide_retrieval": {
        "title": "设计指南检索",
        "icon": "book-open",
        "order": 90,
    },
}
