"""Concurrency guard tests for the agent dispatch path."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from openai import APITimeoutError

from server.agents.decompose import AssessOutlineResult, DecomposedQuery
from server.agents.deps import QADeps
from server.agents.evidence import EvidenceBundle
from server.agents import orchestrator as orchestrator_module
from server.config import ServerConfig
from server.core.conversation import ConversationState
from server.core.retrieval import RetrievalResult
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


class _FakeRetriever:
    async def retrieve(self, *_args, **_kwargs):
        return RetrievalResult(
            chunks=[_make_chunk()],
            parent_chunks=[],
            scores=[0.8],
            groundedness="partial",
        )


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
        agent_reply, _bundle, _conv, _deps, _usage = await dispatch()

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
            _usage,
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
        raise asyncio.TimeoutError()
        yield  # noqa: RUF028 - makes this an async generator

    monkeypatch.setattr(orchestrator_module, "_agent_semaphore", None)
    monkeypatch.setattr(orchestrator_module, "_agent_circuit_breaker", None)
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


@pytest.mark.asyncio
async def test_prepare_evidence_streamed_emits_prefetch_tool_trace(monkeypatch):
    async def fake_decompose_query(*_args, **_kwargs):
        return DecomposedQuery(
            rewritten_question="concrete partial factors",
            sub_queries=["concrete partial factors"],
            needs_retrieval=True,
        )

    async def fake_assess_and_outline(*_args, **_kwargs):
        return AssessOutlineResult(
            sufficient=True,
            missing_queries=[],
            reason="covered",
        )

    monkeypatch.setattr(
        orchestrator_module,
        "decompose_query",
        fake_decompose_query,
    )
    monkeypatch.setattr(
        orchestrator_module,
        "assess_and_outline",
        fake_assess_and_outline,
    )
    monkeypatch.setattr(
        orchestrator_module,
        "outline_answer",
        AsyncMock(return_value={}),
    )
    deps = QADeps(
        config=ServerConfig(decompose_llm_model=""),
        retriever=_FakeRetriever(),
        glossary={},
        bundle=EvidenceBundle(),
        conversation_state=ConversationState(conversation_id="conv-1", history=[]),
    )

    events = [
        item.event
        async for item in orchestrator_module._prepare_evidence_for_agent_streamed(
            req=QueryRequest(question="材料分项系数？"),
            deps=deps,
            glossary={},
        )
    ]

    prefetch_results = [
        event
        for event in events
        if event.kind == "tool_result" and event.tool_name == "prefetch_retrieve"
    ]
    assert prefetch_results
    assert prefetch_results[0].tool_trace["tool"] == "prefetch_retrieve"


@pytest.mark.asyncio
async def test_prepare_evidence_streamed_runs_bounded_assessments_before_stopping(
    monkeypatch,
):
    async def fake_decompose_query(*_args, **_kwargs):
        return DecomposedQuery(
            rewritten_question="concrete partial factors",
            sub_queries=["initial query"],
            needs_retrieval=True,
        )

    assessment_calls = 0

    async def fake_assess_and_outline(*_args, **_kwargs):
        nonlocal assessment_calls
        assessment_calls += 1
        return AssessOutlineResult(
            sufficient=False,
            missing_queries=["missing query"],
            reason="needs one more search",
        )

    class RecordingRetriever:
        def __init__(self):
            self.calls = []

        async def retrieve(self, queries, **kwargs):
            self.calls.append((queries, kwargs["top_k"]))
            return RetrievalResult(
                chunks=[_make_chunk()],
                parent_chunks=[],
                scores=[0.8],
                groundedness="partial",
            )

    monkeypatch.setattr(
        orchestrator_module,
        "decompose_query",
        fake_decompose_query,
    )
    monkeypatch.setattr(
        orchestrator_module,
        "assess_and_outline",
        fake_assess_and_outline,
    )
    monkeypatch.setattr(
        orchestrator_module,
        "outline_answer",
        AsyncMock(return_value={}),
    )
    retriever = RecordingRetriever()
    deps = QADeps(
        config=ServerConfig(decompose_llm_model=""),
        retriever=retriever,
        glossary={},
        bundle=EvidenceBundle(),
        conversation_state=ConversationState(conversation_id="conv-1", history=[]),
    )

    events = [
        item.event
        async for item in orchestrator_module._prepare_evidence_for_agent_streamed(
            req=QueryRequest(question="材料分项系数？"),
            deps=deps,
            glossary={},
        )
    ]

    assessment_results = [
        event
        for event in events
        if event.kind == "tool_result" and event.tool_name == "evidence_assessment"
    ]
    prefetch_results = [
        event
        for event in events
        if event.kind == "tool_result" and event.tool_name == "prefetch_retrieve"
    ]

    assert assessment_calls == 2
    assert len(assessment_results) == 2
    assert len(prefetch_results) == 2
    expected_top_k = orchestrator_module._round_top_k(deps.config, 1)
    assert retriever.calls == [
        (["initial query"], expected_top_k),
        (["missing query"], expected_top_k),
    ]


@pytest.mark.asyncio
async def test_prepare_evidence_merges_subqueries_into_single_retrieve(monkeypatch):
    async def fake_decompose_query(*_args, **_kwargs):
        return DecomposedQuery(
            rewritten_question="concrete strength and deformation",
            sub_queries=["strength definitions", "deformation definitions"],
            needs_retrieval=True,
        )

    async def fake_assess_and_outline(*_args, **_kwargs):
        return AssessOutlineResult(sufficient=True, missing_queries=[], reason="ok")

    class RecordingRetriever:
        def __init__(self):
            self.calls = []
            self.prefetch_calls = []

        async def prefetch_vectors(self, query, filters=None):
            self.prefetch_calls.append(query)
            return [{"chunk_id": "orig-1", "source": "EN 1990", "score": 0.9}]

        async def retrieve(self, queries, **kwargs):
            self.calls.append((queries, kwargs))
            return RetrievalResult(
                chunks=[_make_chunk()],
                parent_chunks=[],
                scores=[0.8],
                groundedness="partial",
                per_query_candidate_counts={query: 1 for query in queries},
            )

    monkeypatch.setattr(orchestrator_module, "decompose_query", fake_decompose_query)
    monkeypatch.setattr(orchestrator_module, "assess_and_outline", fake_assess_and_outline)
    monkeypatch.setattr(
        orchestrator_module, "outline_answer", AsyncMock(return_value={})
    )
    retriever = RecordingRetriever()
    deps = QADeps(
        config=ServerConfig(decompose_llm_model=""),
        retriever=retriever,
        glossary={},
        bundle=EvidenceBundle(),
        conversation_state=ConversationState(conversation_id="conv-1", history=[]),
    )

    async for _item in orchestrator_module._prepare_evidence_for_agent_streamed(
        req=QueryRequest(question="混凝土强度与变形？"),
        deps=deps,
        glossary={},
    ):
        pass

    # 一轮 = 一次合并 retrieve 调用；rewritten 向量候选只预取一次并透传
    assert len(retriever.calls) == 1
    queries, kwargs = retriever.calls[0]
    assert queries == ["strength definitions", "deformation definitions"]
    assert kwargs["original_query"] == "concrete strength and deformation"
    assert kwargs["prefetched_original_results"] == [
        {"chunk_id": "orig-1", "source": "EN 1990", "score": 0.9}
    ]
    assert kwargs["top_k"] == orchestrator_module._round_top_k(deps.config, 2)
    assert retriever.prefetch_calls == ["concrete strength and deformation"]
    trace = [
        entry
        for entry in deps.bundle.tool_trace
        if entry.get("tool") == "prefetch_retrieve"
    ]
    assert trace[0]["queries"] == ["strength definitions", "deformation definitions"]
    assert trace[0]["per_query_candidate_counts"] == {
        "strength definitions": 1,
        "deformation definitions": 1,
    }


class _GroundedRetriever:
    async def retrieve(self, *_args, **_kwargs):
        return RetrievalResult(
            chunks=[_make_chunk()],
            parent_chunks=[],
            scores=[0.92],
            groundedness="grounded",
        )


async def _fake_decompose_single(*_args, **_kwargs):
    return DecomposedQuery(
        rewritten_question="material partial factors",
        sub_queries=["material partial factors"],
        needs_retrieval=True,
    )


@pytest.mark.asyncio
async def test_prepare_evidence_skips_assessment_when_grounded(monkeypatch):
    async def _fail_assess(*_args, **_kwargs):
        raise AssertionError("assessment should be skipped when grounded")

    outline_mock = AsyncMock(return_value={"narrative_angle": "直答"})
    monkeypatch.setattr(orchestrator_module, "decompose_query", _fake_decompose_single)
    monkeypatch.setattr(orchestrator_module, "assess_and_outline", _fail_assess)
    monkeypatch.setattr(orchestrator_module, "outline_answer", outline_mock)
    deps = QADeps(
        config=ServerConfig(decompose_llm_model=""),
        retriever=_GroundedRetriever(),
        glossary={},
        bundle=EvidenceBundle(),
        conversation_state=ConversationState(conversation_id="conv-1", history=[]),
    )

    events = [
        item.event
        async for item in orchestrator_module._prepare_evidence_for_agent_streamed(
            req=QueryRequest(question="材料分项系数？"),
            deps=deps,
            glossary={},
        )
    ]

    assert not [e for e in events if e.tool_name == "evidence_assessment"]
    skipped = [
        entry
        for entry in deps.bundle.tool_trace
        if entry.get("tool") == "evidence_assessment" and entry.get("skipped")
    ]
    assert skipped
    outline_mock.assert_awaited_once()
    assert deps.bundle.outline == {"narrative_angle": "直答"}


@pytest.mark.asyncio
async def test_prepare_evidence_uses_combined_outline_without_extra_call(monkeypatch):
    async def fake_assess(*_args, **_kwargs):
        return AssessOutlineResult(
            sufficient=True,
            missing_queries=[],
            reason="covered",
            outline={"narrative_angle": "合并大纲", "sections": []},
        )

    outline_mock = AsyncMock(return_value={"narrative_angle": "不应被调用"})
    monkeypatch.setattr(orchestrator_module, "decompose_query", _fake_decompose_single)
    monkeypatch.setattr(orchestrator_module, "assess_and_outline", fake_assess)
    monkeypatch.setattr(orchestrator_module, "outline_answer", outline_mock)
    deps = QADeps(
        config=ServerConfig(
            decompose_llm_model="",
            assessment_skip_when_grounded=False,
        ),
        retriever=_GroundedRetriever(),
        glossary={},
        bundle=EvidenceBundle(),
        conversation_state=ConversationState(conversation_id="conv-1", history=[]),
    )

    async for _item in orchestrator_module._prepare_evidence_for_agent_streamed(
        req=QueryRequest(question="材料分项系数？"),
        deps=deps,
        glossary={},
    ):
        pass

    outline_mock.assert_not_awaited()
    assert deps.bundle.outline == {"narrative_angle": "合并大纲", "sections": []}
    assessment_trace = [
        entry
        for entry in deps.bundle.tool_trace
        if entry.get("tool") == "evidence_assessment"
    ]
    assert assessment_trace and assessment_trace[0]["outline_included"] is True
