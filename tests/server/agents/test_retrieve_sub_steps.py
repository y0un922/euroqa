from __future__ import annotations

from agents import RunContextWrapper
import pytest

from server.agents.deps import QADeps
from server.agents.evidence import EvidenceBundle
from server.agents.tool_progress import ToolSubStep
from server.agents.tools.agentic_retrieve import _retrieve_agentic_impl
from server.agents.tools.retrieve import _retrieve_impl
from server.config import ServerConfig
from server.core.conversation import ConversationState
from server.core.evidence_planner import EvidencePlan, EvidenceSlot
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

    async def list_sources(self, filters=None):
        return [
            {
                "source": "EN 1990",
                "title": "Basis of structural design",
                "chunk_count": 10,
            },
            {
                "source": "EN 1992-1-1",
                "title": "Eurocode 2",
                "chunk_count": 20,
            },
        ]


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


@pytest.mark.asyncio
async def test_retrieve_agentic_runs_slot_plan_through_existing_retriever(monkeypatch):
    chunks = [_make_chunk(), _make_chunk().model_copy(update={"chunk_id": "chunk-2"})]
    retriever = _FakeRetriever(
        RetrievalResult(
            chunks=chunks,
            parent_chunks=[],
            scores=[0.8, 0.7],
            groundedness="partial",
        )
    )
    deps = QADeps(
        config=ServerConfig(agentic_search_enabled=True),
        retriever=retriever,
        glossary={},
        bundle=EvidenceBundle(),
        conversation_state=None,
        tool_progress=_ProgressCollector().on_tool_sub_step,
    )
    analysis = QueryAnalysis(
        original_question="请给出作用和材料的分项系数。",
        expanded_queries=["partial factors actions materials"],
        filters={},
        question_type=QuestionType.PARAMETER,
        intent_label="limit",
    )
    plan = EvidencePlan(
        strategy="slot",
        slots=[
            EvidenceSlot(
                id="actions",
                description="Action partial factors",
                query="partial factors for actions",
                search_queries=["EN 1990 partial factors actions"],
                source_hints=["EN 1990"],
            ),
            EvidenceSlot(
                id="materials",
                description="Material partial factors",
                query="partial factors for concrete and reinforcement",
                search_queries=["EN 1992 material partial factors"],
                source_hints=["EN 1992-1-1"],
                object_labels=["Table 2.1N"],
            ),
        ],
    )

    async def _fake_analyze_query(question, glossary, config, history):
        return analysis

    async def _fake_plan_evidence(question, query_analysis, inventory, config):
        assert len(inventory) == 2
        return plan

    monkeypatch.setattr(
        "server.agents.tools.agentic_retrieve.analyze_query",
        _fake_analyze_query,
    )
    monkeypatch.setattr(
        "server.agents.tools.agentic_retrieve.plan_evidence",
        _fake_plan_evidence,
    )

    summary = await _retrieve_agentic_impl(
        RunContextWrapper(deps),
        "请给出作用和材料的分项系数。",
    )

    assert "Evidence slots" in summary
    assert len(retriever.calls) == 2
    assert retriever.calls[0]["filters"] == {"source": "EN 1990"}
    assert retriever.calls[1]["filters"] == {"source": "EN 1992-1-1"}
    assert "Table 2.1N" in retriever.calls[1]["requested_objects"]
    assert deps.bundle.chunk_count == 2
    assert deps.bundle.tool_trace[-1]["tool"] == "retrieve_agentic"
