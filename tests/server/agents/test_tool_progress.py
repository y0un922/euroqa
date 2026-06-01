from __future__ import annotations

import pytest

from server.agents.tool_progress import ToolProgressEmitter, ToolSubStep, _NullEmitter


class _Collector:
    def __init__(self) -> None:
        self.steps: list[ToolSubStep] = []

    async def on_tool_sub_step(self, step: ToolSubStep) -> None:
        self.steps.append(step)


class _RaisingCallback:
    async def on_tool_sub_step(self, step: ToolSubStep) -> None:
        raise RuntimeError(f"boom: {step.step_id}")


@pytest.mark.asyncio
async def test_emitter_start_complete_records_elapsed_ms(monkeypatch):
    collector = _Collector()
    times = iter([10.0, 10.125])
    monkeypatch.setattr(
        "server.agents.tool_progress.time.perf_counter",
        lambda: next(times),
    )
    emitter = ToolProgressEmitter("retrieve", collector)

    await emitter.start("query_understanding", "理解问题", "开始")
    await emitter.complete("query_understanding", "理解问题", "完成")

    assert [step.status for step in collector.steps] == ["running", "completed"]
    assert collector.steps[0].elapsed_ms == 0
    assert collector.steps[1].elapsed_ms == 125


@pytest.mark.asyncio
async def test_skip_emits_skipped_with_zero_elapsed_ms():
    collector = _Collector()
    emitter = ToolProgressEmitter("retrieve", collector)

    await emitter.skip("guide_retrieval", "设计指南检索", "无需检索")

    assert len(collector.steps) == 1
    assert collector.steps[0].status == "skipped"
    assert collector.steps[0].elapsed_ms == 0


@pytest.mark.asyncio
async def test_callback_none_does_not_raise():
    emitter = ToolProgressEmitter("retrieve", None)

    await emitter.start("step", "标题")
    await emitter.complete("step", "标题", "完成")
    await emitter.skip("step", "标题", "跳过")


@pytest.mark.asyncio
async def test_null_emitter_does_not_raise():
    emitter = _NullEmitter()

    await emitter.start("step", "标题")
    await emitter.complete("step", "标题", "完成")
    await emitter.skip("step", "标题", "跳过")


@pytest.mark.asyncio
async def test_callback_exception_is_swallowed():
    emitter = ToolProgressEmitter("retrieve", _RaisingCallback())

    await emitter.start("query_understanding", "理解问题")
    await emitter.complete("query_understanding", "理解问题", "完成")
    await emitter.skip("guide_retrieval", "设计指南检索", "无需检索")
