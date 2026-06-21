from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from agents import RunContextWrapper

from server.agents.deps import QADeps
from server.agents.evidence import EvidenceBundle
from server.agents.qa_agent import (
    AgentStreamEvent,
    _QA_AGENT_INSTRUCTIONS,
    _build_input_items,
    _compress_answer_for_agent,
    build_qa_agent,
    run_qa_agent,
    run_qa_agent_streamed,
)
from server.agents.tools.retrieve import (
    _clamp_top_k,
    _format_retrieval_summary,
    _retrieve_impl,
)
from server.agents.tools.lookup_clause import _lookup_clause_impl
from server.config import ServerConfig
from server.core.conversation import ConversationState
from server.core.query_understanding import QueryAnalysis, RetrievalIntent
from server.core.retrieval import RetrievalResult
from server.models.schemas import Chunk, ChunkMetadata, ElementType, QuestionType


class FakeRetriever:
    def __init__(self, result: RetrievalResult | None = None) -> None:
        self.result = result or RetrievalResult(chunks=[], parent_chunks=[], scores=[])
        self.calls: list[dict] = []

    async def retrieve(self, queries: list[str], **kwargs) -> RetrievalResult:
        self.calls.append({"queries": queries, **kwargs})
        return self.result

    async def lookup_clause(self, clause_ref: str):
        self.calls.append({"clause_ref": clause_ref})
        return list(self.result.ref_chunks or self.result.chunks)


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


def _make_chunks(count: int, prefix: str = "chunk") -> list[Chunk]:
    return [_make_chunk(f"{prefix}-{index}") for index in range(count)]


async def _fake_runner_result(reply: str):
    return SimpleNamespace(final_output=reply)


@pytest.mark.asyncio
async def test_chat_greeting():
    deps = _make_deps()
    reply = "你好，有什么欧标问题可以帮你？"

    with patch(
        "server.agents.qa_agent.Runner.run",
        return_value=await _fake_runner_result(reply),
    ):
        result, bundle = await run_qa_agent(
            agent=object(),
            question="hi",
            deps=deps,
        )

    assert result == reply
    assert bundle.is_empty


def test_qa_agent_instructions_forbid_json_actions():
    assert "不要输出 JSON" in _QA_AGENT_INSTRUCTIONS
    assert '{"action": "retrieve"}' in _QA_AGENT_INSTRUCTIONS


def test_build_qa_agent_does_not_configure_trace_processors():
    with patch("agents.set_trace_processors") as set_trace_processors:
        agent = build_qa_agent(ServerConfig())

    set_trace_processors.assert_not_called()
    tool_names = {getattr(tool, "name", "") for tool in agent.tools}
    assert {"retrieve", "lookup_clause", "lookup_glossary"} <= tool_names


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
        return SimpleNamespace(final_output="已检索到 EN 1990 的设计使用年限条文。")

    with (
        patch("server.agents.qa_agent.Runner.run", side_effect=fake_runner_run),
        patch("server.agents.tools.retrieve.analyze_query", return_value=analysis),
    ):
        result, bundle = await run_qa_agent(
            agent=object(),
            question="设计使用年限是什么？",
            deps=deps,
        )

    assert "EN 1990" in result
    assert not bundle.is_empty
    assert bundle.has_rag_evidence
    assert bundle.chunk_count == 1
    assert bundle.groundedness == "grounded"
    assert retriever.calls[0]["queries"] == ["design working life"]
    assert retriever.calls[0]["filters"] == {"source": "EN 1990"}
    assert retriever.calls[0]["top_k"] == 8


@pytest.mark.asyncio
async def test_retrieve_tool_relaxes_auto_family_filter_when_domain_filter_exists():
    retriever = FakeRetriever(
        RetrievalResult(
            chunks=[_make_chunk()],
            parent_chunks=[],
            scores=[0.8],
            groundedness="partial",
        )
    )
    deps = _make_deps(retriever=retriever)
    deps.domain_filter = "EN 1990"
    analysis = QueryAnalysis(
        original_question="EN 1992 新版最小配筋怎么取？",
        expanded_queries=["minimum reinforcement"],
        filters={"standard_family": "EN 1992-1-1"},
        question_type=QuestionType.PARAMETER,
        intent_label="limit",
        retrieval_intent=RetrievalIntent(
            standard_family="EN 1992-1-1",
            standard_family_confidence="high",
            version_pref="new",
        ),
    )

    with patch("server.agents.tools.retrieve.analyze_query", return_value=analysis):
        await _retrieve_impl(
            RunContextWrapper(deps),
            "EN 1992 新版最小配筋怎么取？",
        )

    call = retriever.calls[0]
    assert call["filters"] == {"source": "EN 1990"}
    assert call["soft_boosts"]["standard_family"] == "EN 1992-1-1"
    assert call["soft_boosts"]["doc_version"] == ["2022", "2023", "2024", "2025"]


@pytest.mark.asyncio
async def test_retrieve_tool_accepts_top_k_and_trims_evidence():
    chunks = _make_chunks(12)
    parent_chunks = _make_chunks(8, prefix="parent")
    guide_chunks = _make_chunks(6, prefix="guide")
    guide_example_chunks = _make_chunks(5, prefix="example")
    ref_chunks = _make_chunks(7, prefix="ref")
    retriever = FakeRetriever(
        RetrievalResult(
            chunks=chunks,
            parent_chunks=parent_chunks,
            scores=[0.9 - index * 0.01 for index in range(len(chunks))],
            guide_chunks=guide_chunks,
            guide_example_chunks=guide_example_chunks,
            ref_chunks=ref_chunks,
            groundedness="grounded",
        )
    )
    deps = _make_deps(retriever=retriever)
    analysis = QueryAnalysis(
        original_question="钢筋的主要特性有哪些？",
        expanded_queries=["reinforcing steel properties"],
        filters={},
        question_type=QuestionType.RULE,
        intent_label="summary",
    )

    with patch("server.agents.tools.retrieve.analyze_query", return_value=analysis):
        summary = await _retrieve_impl(
            RunContextWrapper(deps),
            "钢筋的主要特性有哪些？",
            top_k=5,
        )

    assert retriever.calls[0]["top_k"] == 5
    assert deps.bundle.chunks == chunks[:5]
    assert deps.bundle.parent_chunks == parent_chunks[:5]
    assert deps.bundle.scores == [0.9 - index * 0.01 for index in range(5)]
    assert deps.bundle.guide_chunks == guide_chunks[:2]
    assert deps.bundle.guide_example_chunks == guide_example_chunks[:1]
    assert deps.bundle.ref_chunks == ref_chunks[:2]
    assert deps.bundle.tool_trace[-1]["top_k"] == 5
    assert "检索到 5 个片段" in summary


@pytest.mark.asyncio
async def test_lookup_clause_tool_adds_ref_chunks_to_bundle():
    ref_chunk = _make_chunk("clause-6-10")
    retriever = FakeRetriever(
        RetrievalResult(
            chunks=[],
            parent_chunks=[],
            scores=[],
            ref_chunks=[ref_chunk],
        )
    )
    deps = _make_deps(retriever=retriever)

    summary = await _lookup_clause_impl(
        RunContextWrapper(deps),
        "EN 1990, Expression (6.10)",
    )

    assert "精确找到 1 个条款片段" in summary
    assert deps.bundle.ref_chunks == [ref_chunk]
    assert deps.bundle.tool_trace[-1] == {
        "tool": "lookup_clause",
        "clause_ref": "EN 1990, Expression (6.10)",
        "chunk_count": 1,
    }


@pytest.mark.asyncio
async def test_retrieve_tool_skips_when_bundle_is_already_grounded():
    bundle = EvidenceBundle(chunks=[_make_chunk()])
    bundle.groundedness = "grounded"
    retriever = FakeRetriever()
    deps = _make_deps(retriever=retriever, bundle=bundle)

    with patch("server.agents.tools.retrieve.analyze_query") as analyze_query:
        summary = await _retrieve_impl(
            RunContextWrapper(deps),
            "EN 1990 设计使用年限是什么？",
            top_k=99,
        )

    analyze_query.assert_not_called()
    assert retriever.calls == []
    assert "跳过检索" in summary
    assert "groundedness=grounded" in summary
    assert "1 个片段" in summary
    assert "个片段)。 请直接" in summary
    assert deps.bundle.tool_trace[-1] == {
        "tool": "retrieve",
        "query": "EN 1990 设计使用年限是什么？",
        "skipped": True,
        "reason": "already_grounded",
    }


def test_format_retrieval_summary_includes_stop_instruction_and_previews():
    chunk = _make_chunk()
    chunk.content = "First line\nSecond line explains the design working life requirement."

    summary = _format_retrieval_summary("grounded", [chunk])

    assert "证据已充足" in summary
    assert "无需再次检索" in summary
    assert "摘要: First line Second line explains" in summary


@pytest.mark.parametrize(
    ("requested", "expected"),
    [
        (1, 3),
        (4, 4),
        (99, 12),
        ("bad", 8),
    ],
)
def test_retrieve_tool_clamps_top_k(requested, expected):
    assert _clamp_top_k(requested) == expected


def test_compress_answer_for_agent_strips_citations_and_truncates():
    answer = "[Ref-1] " + "设计使用年限" * 30 + " [Ref-22]"

    compressed = _compress_answer_for_agent(answer, limit=20)

    assert "[Ref-" not in compressed
    assert compressed == ("设计使用年限" * 3 + "设计") + "..."


def test_build_input_items_compresses_previous_answers_only():
    deps = _make_deps()
    deps.conversation_state = ConversationState(
        conversation_id="conv-1",
        history=[
            {
                "question": "上一轮问题",
                "answer": "[Ref-1] " + "A" * 250,
            }
        ]
    )

    input_items = _build_input_items("当前问题 [Ref-2]", deps)

    assert input_items == [
        {"role": "user", "content": "上一轮问题"},
        {"role": "assistant", "content": "A" * 200 + "..."},
        {"role": "user", "content": "当前问题 [Ref-2]"},
    ]


@pytest.mark.asyncio
async def test_clarify_vague_question():
    deps = _make_deps()
    reply = "请补充规范号或构件类型。"

    with patch(
        "server.agents.qa_agent.Runner.run",
        return_value=await _fake_runner_result(reply),
    ):
        result, bundle = await run_qa_agent(
            agent=object(),
            question="这个参数是多少",
            deps=deps,
        )

    assert "补充" in result or "哪" in result
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

    assert result == "已检索到相关规范证据，正在整理回答。"
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

    assert result == "抱歉，暂时查不到相关规范内容，请尝试换个问法或补充规范号。"
    assert bundle.is_empty


@pytest.mark.asyncio
async def test_direct_reply_without_retrieve_exposes_empty_bundle():
    """The agent can answer directly without creating RAG evidence."""
    deps = _make_deps()
    reply = "这个问题需要补充规范号或构件类型。"

    with patch(
        "server.agents.qa_agent.Runner.run",
        return_value=await _fake_runner_result(reply),
    ):
        result, bundle = await run_qa_agent(
            agent=object(),
            question="混凝土分项系数是多少？",
            deps=deps,
        )

    assert result == reply
    assert bundle.is_empty
    assert not any(entry.get("tool") == "retrieve" for entry in bundle.tool_trace)


@pytest.mark.asyncio
async def test_run_qa_agent_streamed_yields_tool_progress():
    deps = _make_deps()

    class _FakeStreamedRun:
        final_output = "已检索到相关规范证据。"

        async def stream_events(self):
            from agents.stream_events import RunItemStreamEvent

            yield RunItemStreamEvent(
                name="tool_called",
                item=SimpleNamespace(
                    type="tool_call_item",
                    tool_name="retrieve",
                    call_id="call-1",
                    raw_item={"arguments": '{"query": "design working life"}'},
                ),
            )
            yield RunItemStreamEvent(
                name="tool_output",
                item=SimpleNamespace(
                    type="tool_call_output_item",
                    call_id="call-1",
                    output="检索到 1 个片段。",
                ),
            )

    with patch(
        "server.agents.qa_agent.Runner.run_streamed",
        return_value=_FakeStreamedRun(),
    ):
        events = [
            item
            async for item in run_qa_agent_streamed(
                agent=object(),
                question="设计使用年限是什么？",
                deps=deps,
            )
        ]

    assert isinstance(events[0], AgentStreamEvent)
    assert events[0].kind == "tool_calling"
    assert events[0].tool_name == "retrieve"
    assert events[0].tool_args == {
        "call_id": "call-1",
        "arguments": '{"query": "design working life"}',
    }
    assert "design working life" in events[0].summary
    assert isinstance(events[1], AgentStreamEvent)
    assert events[1].kind == "tool_result"
    assert events[1].tool_result == "检索到 1 个片段。"
    assert events[-1] == ("已检索到相关规范证据。", deps.bundle)


def test_qa_agent_instructions_require_retrieve_for_eurocode_questions():
    """Prompt-hardening: Eurocode questions should use retrieve."""
    assert "必须调用 retrieve" in _QA_AGENT_INSTRUCTIONS
    assert "retrieve 已返回 groundedness=grounded 的结果时，不要再次调用 retrieve" in (
        _QA_AGENT_INSTRUCTIONS
    )
    assert "lookup_clause(clause_ref)" in _QA_AGENT_INSTRUCTIONS
    assert "错误 filter 比没有 filter 更糟" in _QA_AGENT_INSTRUCTIONS
    assert "最多调用 retrieve 2 次" not in _QA_AGENT_INSTRUCTIONS
    assert "top_k 允许范围 3-12" in _QA_AGENT_INSTRUCTIONS
    assert "简单定义或单个参数问题用 4-6" in _QA_AGENT_INSTRUCTIONS
    assert "不要输出 JSON" in _QA_AGENT_INSTRUCTIONS
