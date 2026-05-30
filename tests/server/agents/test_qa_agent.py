from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from agents import RunContextWrapper

from server.agents.deps import QADeps
from server.agents.evidence import EvidenceBundle
from server.agents.qa_agent import (
    AgentDecision,
    _QA_AGENT_INSTRUCTIONS,
    build_qa_agent,
    run_qa_agent,
)
from server.agents.tools.retrieve import _retrieve_impl
from server.config import ServerConfig
from server.core.query_understanding import QueryAnalysis
from server.core.retrieval import RetrievalResult
from server.models.schemas import Chunk, ChunkMetadata, ElementType, QuestionType


class FakeRetriever:
    def __init__(self, result: RetrievalResult | None = None) -> None:
        self.result = result or RetrievalResult(chunks=[], parent_chunks=[], scores=[])
        self.calls: list[dict] = []

    async def retrieve(self, queries: list[str], **kwargs) -> RetrievalResult:
        self.calls.append({"queries": queries, **kwargs})
        return self.result


def _make_deps(
    *,
    retriever: FakeRetriever | None = None,
    bundle: EvidenceBundle | None = None,
    glossary: dict[str, str] | None = None,
) -> QADeps:
    return QADeps(
        config=ServerConfig(),
        retriever=retriever or FakeRetriever(),
        glossary=glossary or {},
        bundle=bundle or EvidenceBundle(),
    )


def _make_chunk(chunk_id: str = "chunk-1") -> Chunk:
    return Chunk(
        chunk_id=chunk_id,
        content="Design working life shall be specified according to EN 1990.",
        embedding_text="Design working life EN 1990",
        metadata=ChunkMetadata(
            source="EN 1990:2002",
            source_title="Basis of structural design",
            section_path=["2.3", "Design working life"],
            page_numbers=[28],
            page_file_index=[27],
            clause_ids=["2.3"],
            element_type=ElementType.TEXT,
        ),
    )


async def _fake_runner_result(decision: AgentDecision):
    return SimpleNamespace(final_output=decision)


@pytest.mark.asyncio
async def test_chat_greeting():
    deps = _make_deps()
    decision = AgentDecision(
        action="chat", direct_reply="你好，有什么欧标问题可以帮你？"
    )

    with patch(
        "server.agents.qa_agent.Runner.run",
        return_value=await _fake_runner_result(decision),
    ):
        result, bundle = await run_qa_agent(
            agent=object(),
            question="hi",
            deps=deps,
        )

    assert result.action == "chat"
    assert result.direct_reply
    assert bundle.is_empty


def test_qa_agent_instructions_mention_json():
    assert "json" in _QA_AGENT_INSTRUCTIONS.lower()


def test_build_qa_agent_does_not_configure_trace_processors():
    with patch("agents.set_trace_processors") as set_trace_processors:
        build_qa_agent(ServerConfig())

    set_trace_processors.assert_not_called()


@pytest.mark.asyncio
async def test_rag_eurocode_question():
    chunk = _make_chunk()
    retriever = FakeRetriever(
        RetrievalResult(
            chunks=[chunk],
            parent_chunks=[],
            scores=[0.93],
            groundedness="grounded",
        )
    )
    deps = _make_deps(retriever=retriever)
    analysis = QueryAnalysis(
        original_question="设计使用年限是什么？",
        expanded_queries=["design working life"],
        filters={"source": "EN 1990"},
        question_type=QuestionType.RULE,
        intent_label="definition",
    )

    async def fake_runner_run(_agent, _input, *, context, **_kwargs):
        await _retrieve_impl(
            RunContextWrapper(context),
            "设计使用年限是什么？",
        )
        return SimpleNamespace(final_output=AgentDecision(action="compose_rag"))

    with (
        patch("server.agents.qa_agent.Runner.run", side_effect=fake_runner_run),
        patch("server.agents.tools.retrieve.analyze_query", return_value=analysis),
    ):
        result, bundle = await run_qa_agent(
            agent=object(),
            question="设计使用年限是什么？",
            deps=deps,
        )

    assert result.action == "compose_rag"
    assert not bundle.is_empty
    assert bundle.chunk_count == 1
    assert bundle.groundedness == "grounded"
    assert retriever.calls[0]["queries"] == ["design working life"]
    assert retriever.calls[0]["filters"] == {"source": "EN 1990"}


@pytest.mark.asyncio
async def test_clarify_vague_question():
    deps = _make_deps()
    decision = AgentDecision(action="clarify", direct_reply="请补充规范号或构件类型。")

    with patch(
        "server.agents.qa_agent.Runner.run",
        return_value=await _fake_runner_result(decision),
    ):
        result, bundle = await run_qa_agent(
            agent=object(),
            question="这个参数是多少",
            deps=deps,
        )

    assert result.action == "clarify"
    assert result.direct_reply
    assert "补充" in result.direct_reply or "哪" in result.direct_reply
    assert bundle.is_empty


@pytest.mark.asyncio
async def test_max_turns_with_evidence():
    bundle = EvidenceBundle(chunks=[_make_chunk()])
    deps = _make_deps(bundle=bundle)

    async def fake_runner_run(_agent, _input, *, error_handlers, **_kwargs):
        decision = error_handlers["max_turns"](object())
        return SimpleNamespace(final_output=decision)

    with patch("server.agents.qa_agent.Runner.run", side_effect=fake_runner_run):
        result, returned_bundle = await run_qa_agent(
            agent=object(),
            question="EN 1990 设计使用年限是什么？",
            deps=deps,
            max_turns=1,
        )

    assert result.action == "compose_rag"
    assert returned_bundle is bundle


@pytest.mark.asyncio
async def test_max_turns_without_evidence():
    deps = _make_deps()

    async def fake_runner_run(_agent, _input, *, error_handlers, **_kwargs):
        decision = error_handlers["max_turns"](object())
        return SimpleNamespace(final_output=decision)

    with patch("server.agents.qa_agent.Runner.run", side_effect=fake_runner_run):
        result, bundle = await run_qa_agent(
            agent=object(),
            question="EN 1990 设计使用年限是什么？",
            deps=deps,
            max_turns=1,
        )

    assert result.action == "chat"
    assert (
        result.direct_reply
        == "抱歉，暂时查不到相关规范内容，请尝试换个问法或补充规范号。"
    )
    assert bundle.is_empty


@pytest.mark.asyncio
async def test_compose_rag_without_retrieve_exposes_empty_bundle():
    """Regression: bug state — agent returns compose_rag without calling retrieve.

    This test asserts the *current* run_qa_agent behavior in the buggy case
    (no auto-recovery at agent layer). The fix lives in the dispatch layer
    (server/api/v1/query.py — see test_query_stream_recovers_*).
    """
    deps = _make_deps()
    decision = AgentDecision(action="compose_rag")

    with patch(
        "server.agents.qa_agent.Runner.run",
        return_value=await _fake_runner_result(decision),
    ):
        result, bundle = await run_qa_agent(
            agent=object(),
            question="混凝土分项系数是多少？",
            deps=deps,
        )

    assert result.action == "compose_rag"
    assert bundle.is_empty
    assert not any(entry.get("tool") == "retrieve" for entry in bundle.tool_trace)


def test_qa_agent_instructions_require_retrieve_before_compose():
    """Prompt-hardening guard: enforce the new mandatory-retrieve language."""
    assert "必须先调用 retrieve" in _QA_AGENT_INSTRUCTIONS
    assert "硬性" in _QA_AGENT_INSTRUCTIONS
