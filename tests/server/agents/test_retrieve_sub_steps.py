from __future__ import annotations

from agents import RunContextWrapper
import pytest

from server.agents.deps import QADeps
from server.agents.evidence import EvidenceBundle
from server.agents.tool_progress import ToolSubStep
from server.agents.tools.retrieve import _retrieve_impl
from server.config import ServerConfig
from server.core.conversation import ConversationState
from server.core.query_understanding import QueryAnalysis
from server.core.retrieval import RetrievalResult
from server.models.schemas import Chunk, ChunkMetadata, ElementType, QuestionType


class _ProgressCollector:
    def __init__(self) -> None:
        self.steps: list[ToolSubStep] = []

    async def on_tool_sub_step(self, step: ToolSubStep) -> None:
        self.steps.append(step)


class _FakeRetriever:
    def __init__(self, result: RetrievalResult) -> None:
        self.result = result
        self.calls: list[dict] = []

    async def retrieve(self, queries: list[str], **kwargs) -> RetrievalResult:
        self.calls.append({"queries": queries, **kwargs})
        return self.result


def _make_chunk() -> Chunk:
    return Chunk(
        chunk_id="chunk-1",
        content="Concrete cover depends on exposure class.",
        embedding_text="Concrete cover exposure class",
        metadata=ChunkMetadata(
            source="EN 1992-1-1",
            source_title="Eurocode 2",
            section_path=["4.4", "Durability"],
            page_numbers=[40],
            page_file_index=[39],
            clause_ids=["4.4"],
            element_type=ElementType.TEXT,
        ),
    )


@pytest.mark.asyncio
async def test_retrieve_impl_emits_sub_steps_and_rewrite_metadata(monkeypatch):
    chunk = _make_chunk()
    result = RetrievalResult(
        chunks=[chunk],
        parent_chunks=[],
        scores=[0.9],
        groundedness="grounded",
    )
    retriever = _FakeRetriever(result)
    progress = _ProgressCollector()
    deps = QADeps(
        config=ServerConfig(),
        retriever=retriever,
        glossary={},
        bundle=EvidenceBundle(),
        conversation_state=ConversationState(
            conversation_id="conv-1",
            history=[
                {"question": "保护层厚度怎么确定？", "answer": "按耐久性要求确定。"}
            ],
        ),
        tool_progress=progress,
    )
    analysis = QueryAnalysis(
        original_question="它跟耐久性等级有什么关系？",
        rewritten_question="混凝土保护层厚度跟耐久性等级有什么关系？",
        expanded_queries=["concrete cover durability exposure class"],
        filters={},
        question_type=QuestionType.MECHANISM,
        intent_label="mechanism",
    )

    async def _fake_analyze_query(question, glossary, config, history):
        assert question == "它跟耐久性等级有什么关系？"
        assert history == deps.conversation_state.history
        return analysis

    monkeypatch.setattr(
        "server.agents.tools.retrieve.analyze_query",
        _fake_analyze_query,
    )

    await _retrieve_impl(
        RunContextWrapper(deps),
        "它跟耐久性等级有什么关系？",
    )

    completed = {
        step.step_id: step for step in progress.steps if step.status == "completed"
    }
    assert "query_understanding" in completed
    assert "hybrid_search" in completed
    assert completed["query_understanding"].metadata["was_rewritten"] is True
    assert completed["query_understanding"].metadata["rewritten_question"] == (
        "混凝土保护层厚度跟耐久性等级有什么关系？"
    )
    assert retriever.calls[0]["original_query"] == (
        "混凝土保护层厚度跟耐久性等级有什么关系？"
    )
    assert retriever.calls[0]["progress"] is not None
    assert deps.bundle.tool_trace[-1]["rewritten_question"] == (
        "混凝土保护层厚度跟耐久性等级有什么关系？"
    )
