"""Concurrency guard tests for the agent dispatch path."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from openai import APITimeoutError

from server.agents.evidence import EvidenceBundle
from server.agents.qa_agent import AgentDecision
from server.api.v1 import query as query_module
from server.config import ServerConfig
from server.errors import LLMUnavailableError
from server.models.schemas import QueryRequest


class _FakeConversationManager:
    def get_or_create(self, conversation_id):
        return SimpleNamespace(conversation_id=conversation_id or "conv-1", history=[])


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
        return SimpleNamespace(
            final_output=AgentDecision(action="chat", direct_reply="ok")
        )

    monkeypatch.setattr(query_module, "_agent_semaphore", None)
    monkeypatch.setattr(query_module, "_get_or_build_agent", lambda _config: object())

    async def dispatch(index: int):
        return await query_module._run_agent_dispatch(
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

    monkeypatch.setattr(query_module, "_agent_semaphore", None)
    monkeypatch.setattr(query_module, "_agent_circuit_breaker", None)
    monkeypatch.setattr(query_module, "_get_or_build_agent", lambda _config: object())

    async def dispatch():
        return await query_module._run_agent_dispatch(
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
    breaker = query_module.AsyncCircuitBreaker(
        failure_threshold=config.agent_circuit_breaker_failure_threshold,
        recovery_timeout_seconds=config.agent_circuit_breaker_recovery_seconds,
        clock=fake_clock,
    )
    await breaker.record_failure()

    async def fake_runner_run(_agent, _input_items, *, context, **_kwargs):
        return SimpleNamespace(
            final_output=AgentDecision(action="chat", direct_reply="ok")
        )

    monkeypatch.setattr(query_module, "_agent_semaphore", None)
    monkeypatch.setattr(query_module, "_agent_circuit_breaker", breaker)
    monkeypatch.setattr(query_module, "_get_or_build_agent", lambda _config: object())

    async def dispatch():
        return await query_module._run_agent_dispatch(
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
        decision, _bundle, _conv, _deps = await dispatch()

    assert decision.action == "chat"
    assert breaker.state == "closed"
