"""Concurrency guard tests for the agent dispatch path."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from openai import APITimeoutError

from server.agents.evidence import EvidenceBundle
from server.agents import orchestrator as orchestrator_module
from server.config import ServerConfig
from server.errors import LLMUnavailableError
from server.models.schemas import Chunk, ChunkMetadata, ElementType, QueryRequest


class _FakeConversationManager:
    def get_or_create(self, conversation_id):
        return SimpleNamespace(conversation_id=conversation_id or "conv-1", history=[])


class _TimeoutAfterBody:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        raise asyncio.TimeoutError


def _make_chunk() -> Chunk:
    return Chunk(
        chunk_id="chunk-1",
        content="Eurocode evidence.",
        embedding_text="Eurocode evidence",
        metadata=ChunkMetadata(
            source="EN 1990:2002",
            source_title="Basis of structural design",
            section_path=["1"],
            page_numbers=[1],
            page_file_index=[0],
            clause_ids=["1"],
            element_type=ElementType.TEXT,
        ),
    )


@pytest.mark.asyncio
async def test_run_agent_dispatch_limits_agent_concurrency(monkeypatch):
    config = ServerConfig(agent_max_concurrency=2, agent_timeout_seconds=5)
    active = 0
    max_active = 0

    async def fake_runner_run(_agent, _input_items, *, context, **_kwargs):
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        await asyncio.sleep(0.05)
        active -= 1
        assert isinstance(context.bundle, EvidenceBundle)
        return SimpleNamespace(final_output="ok")

    monkeypatch.setattr(orchestrator_module, "_agent_semaphore", None)
    monkeypatch.setattr(
        orchestrator_module, "_get_or_build_agent", lambda _config: object()
    )

    async def dispatch(index: int):
        return await orchestrator_module._run_agent_dispatch(
            req=QueryRequest(question=f"question {index}"),
            runtime_config=config,
            retriever=object(),
            glossary={},
            conv_mgr=_FakeConversationManager(),
        )

    with patch("server.agents.qa_agent.Runner.run", side_effect=fake_runner_run):
        await asyncio.gather(*(dispatch(index) for index in range(6)))

    assert max_active == config.agent_max_concurrency


@pytest.mark.asyncio
async def test_run_agent_dispatch_opens_circuit_breaker(monkeypatch):
    config = ServerConfig(
        agent_circuit_breaker_failure_threshold=1,
        agent_circuit_breaker_recovery_seconds=60.0,
        agent_timeout_seconds=5,
    )
    runner_calls = 0

    async def fake_runner_run(_agent, _input_items, *, context, **_kwargs):
        nonlocal runner_calls
        runner_calls += 1
        raise APITimeoutError(request=None)

    monkeypatch.setattr(orchestrator_module, "_agent_semaphore", None)
    monkeypatch.setattr(orchestrator_module, "_agent_circuit_breaker", None)
    monkeypatch.setattr(
        orchestrator_module, "_get_or_build_agent", lambda _config: object()
    )

    async def dispatch():
        return await orchestrator_module._run_agent_dispatch(
            req=QueryRequest(question="question"),
            runtime_config=config,
            retriever=object(),
            glossary={},
            conv_mgr=_FakeConversationManager(),
        )

    with patch("server.agents.qa_agent.Runner.run", side_effect=fake_runner_run):
        with pytest.raises(LLMUnavailableError):
            await dispatch()
        with pytest.raises(LLMUnavailableError):
            await dispatch()

    assert runner_calls == 2


@pytest.mark.asyncio
async def test_run_agent_dispatch_half_open_success_closes_breaker(monkeypatch):
    clock_now = 0.0

    def fake_clock() -> float:
        return clock_now

    config = ServerConfig(
        agent_circuit_breaker_failure_threshold=1,
        agent_circuit_breaker_recovery_seconds=10.0,
        agent_timeout_seconds=5,
    )
    breaker = orchestrator_module.AsyncCircuitBreaker(
        failure_threshold=config.agent_circuit_breaker_failure_threshold,
        recovery_timeout_seconds=config.agent_circuit_breaker_recovery_seconds,
        clock=fake_clock,
    )
    await breaker.record_failure()

    async def fake_runner_run(_agent, _input_items, *, context, **_kwargs):
        return SimpleNamespace(final_output="ok")

    monkeypatch.setattr(orchestrator_module, "_agent_semaphore", None)
    monkeypatch.setattr(orchestrator_module, "_agent_circuit_breaker", breaker)
    monkeypatch.setattr(
        orchestrator_module, "_get_or_build_agent", lambda _config: object()
    )

    async def dispatch():
        return await orchestrator_module._run_agent_dispatch(
            req=QueryRequest(question="question"),
            runtime_config=config,
            retriever=object(),
            glossary={},
            conv_mgr=_FakeConversationManager(),
        )

    with patch("server.agents.qa_agent.Runner.run", side_effect=fake_runner_run):
        with pytest.raises(LLMUnavailableError):
            await dispatch()

        clock_now = 10.0
        agent_reply, _bundle, _conv, _deps = await dispatch()

    assert agent_reply == "ok"
    assert breaker.state == "closed"


@pytest.mark.asyncio
async def test_run_agent_dispatch_timeout_returns_existing_evidence(monkeypatch):
    config = ServerConfig(agent_timeout_seconds=1)

    async def fake_runner_run(_agent, _input_items, *, context, **_kwargs):
        context.bundle.chunks.append(_make_chunk())
        context.bundle.groundedness = "grounded"
        return SimpleNamespace(final_output="too late")

    monkeypatch.setattr(orchestrator_module, "_agent_semaphore", None)
    monkeypatch.setattr(orchestrator_module, "_agent_circuit_breaker", None)
    monkeypatch.setattr(
        orchestrator_module.asyncio,
        "timeout",
        lambda _seconds: _TimeoutAfterBody(),
    )
    monkeypatch.setattr(
        orchestrator_module, "_get_or_build_agent", lambda _config: object()
    )

    with patch("server.agents.qa_agent.Runner.run", side_effect=fake_runner_run):
        (
            agent_reply,
            bundle,
            _conv,
            _deps,
        ) = await orchestrator_module._run_agent_dispatch(
            req=QueryRequest(question="钢筋的主要特性有哪些？"),
            runtime_config=config,
            retriever=object(),
            glossary={},
            conv_mgr=_FakeConversationManager(),
        )

    assert agent_reply == "已检索到相关规范证据，正在整理回答。"
    assert bundle.has_rag_evidence
    assert bundle.groundedness == "grounded"


@pytest.mark.asyncio
async def test_run_agent_dispatch_stream_timeout_returns_existing_evidence(
    monkeypatch,
):
    config = ServerConfig(agent_timeout_seconds=1)

    async def fake_run_qa_agent_streamed(_agent, _question, deps, **_kwargs):
        deps.bundle.chunks.append(_make_chunk())
        deps.bundle.groundedness = "grounded"
        return
        yield

    monkeypatch.setattr(orchestrator_module, "_agent_semaphore", None)
    monkeypatch.setattr(orchestrator_module, "_agent_circuit_breaker", None)
    monkeypatch.setattr(
        orchestrator_module.asyncio,
        "timeout",
        lambda _seconds: _TimeoutAfterBody(),
    )
    monkeypatch.setattr(
        orchestrator_module, "_get_or_build_agent", lambda _config: object()
    )
    monkeypatch.setattr(
        orchestrator_module,
        "run_qa_agent_streamed",
        fake_run_qa_agent_streamed,
    )

    results = [
        item
        async for item in orchestrator_module.dispatch_agent_streamed(
            question="钢筋的主要特性有哪些？",
            req=QueryRequest(question="钢筋的主要特性有哪些？"),
            config=config,
            retriever=object(),
            glossary={},
            conv_mgr=_FakeConversationManager(),
        )
    ]

    assert len(results) == 1
    result = results[0]
    assert isinstance(result, orchestrator_module.AgentResult)
    assert result.agent_reply == "已检索到相关规范证据，正在整理回答。"
    assert result.bundle.has_rag_evidence
    assert result.bundle.groundedness == "grounded"
