from __future__ import annotations

import asyncio

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
    def __init__(
        self,
        result: RetrievalResult | list[RetrievalResult],
        object_chunks: dict[str, list[Chunk]] | None = None,
    ) -> None:
        self.results = result if isinstance(result, list) else [result]
        self.object_chunks = object_chunks or {}
        self.calls: list[dict] = []
        self.lookup_calls: list[dict] = []

    async def retrieve(self, queries: list[str], **kwargs) -> RetrievalResult:
        self.calls.append({"queries": queries, **kwargs})
        index = min(len(self.calls) - 1, len(self.results) - 1)
        return self.results[index]

    async def lookup_object(self, label: str, filters=None, top_k: int = 3):
        self.lookup_calls.append(
            {"label": label, "filters": filters or {}, "top_k": top_k}
        )
        return self.object_chunks.get(label, [])[:top_k]

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


class _DelayedFakeRetriever(_FakeRetriever):
    def __init__(
        self,
        result: RetrievalResult | list[RetrievalResult],
        delay_seconds: float = 0.02,
    ) -> None:
        super().__init__(result)
        self.delay_seconds = delay_seconds
        self.active_calls = 0
        self.max_active_calls = 0

    async def retrieve(self, queries: list[str], **kwargs) -> RetrievalResult:
        self.active_calls += 1
        self.max_active_calls = max(self.max_active_calls, self.active_calls)
        await asyncio.sleep(self.delay_seconds)
        try:
            return await super().retrieve(queries, **kwargs)
        finally:
            self.active_calls -= 1


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


def _make_table_chunk(label: str = "Table 2.1N") -> Chunk:
    return Chunk(
        chunk_id="table-2-1n",
        content="Table 2.1N Partial factors: concrete gamma_C = 1.5; steel gamma_S = 1.15.",
        embedding_text="Table 2.1N partial factors concrete steel",
        metadata=ChunkMetadata(
            source="EN 1992-1-1",
            source_title="Eurocode 2",
            section_path=[label],
            page_numbers=[35],
            page_file_index=[34],
            clause_ids=[label],
            element_type=ElementType.TABLE,
            object_type="table",
            object_label=label,
            object_id="en-1992-1-1#table:2.1N",
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

    async def _fake_analyze_query(question, glossary, config, history, **kwargs):
        assert question == "它跟耐久性等级有什么关系？"
        assert history is None
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

    async def _fake_analyze_query(question, glossary, config, history, **kwargs):
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
    assert retriever.calls[0]["top_k"] == 6
    assert retriever.calls[1]["top_k"] == 6
    assert "Table 2.1N" in retriever.calls[1]["requested_objects"]
    assert deps.bundle.chunk_count == 2
    assert deps.bundle.tool_trace[-1]["tool"] == "retrieve_agentic"


@pytest.mark.asyncio
async def test_retrieve_agentic_does_not_skip_on_existing_global_groundedness(
    monkeypatch,
):
    retriever = _FakeRetriever(
        RetrievalResult(
            chunks=[_make_chunk()],
            parent_chunks=[],
            scores=[0.8],
            groundedness="partial",
        )
    )
    deps = QADeps(
        config=ServerConfig(agentic_search_enabled=True),
        retriever=retriever,
        glossary={},
        bundle=EvidenceBundle(groundedness="grounded"),
        conversation_state=None,
        tool_progress=_ProgressCollector().on_tool_sub_step,
    )
    analysis = QueryAnalysis(
        original_question="钢筋的主要特性有哪些？",
        expanded_queries=["reinforcing steel properties"],
        filters={},
        question_type=QuestionType.PARAMETER,
        intent_label="definition",
    )
    plan = EvidencePlan(
        strategy="single",
        slots=[
            EvidenceSlot(
                id="steel",
                description="Reinforcing steel properties",
                query="reinforcing steel properties",
                search_queries=["reinforcing steel properties"],
            )
        ],
    )

    async def _fake_analyze_query(question, glossary, config, history, **kwargs):
        return analysis

    async def _fake_plan_evidence(question, query_analysis, inventory, config):
        return plan

    monkeypatch.setattr(
        "server.agents.tools.agentic_retrieve.analyze_query",
        _fake_analyze_query,
    )
    monkeypatch.setattr(
        "server.agents.tools.agentic_retrieve.plan_evidence",
        _fake_plan_evidence,
    )

    summary = await _retrieve_agentic_impl(RunContextWrapper(deps), "钢筋的主要特性有哪些？")

    assert len(retriever.calls) == 1
    assert "跳过检索" not in summary
    assert deps.bundle.groundedness == "partial"


@pytest.mark.asyncio
async def test_retrieve_agentic_groundedness_requires_all_required_slots(
    monkeypatch,
):
    retriever = _DelayedFakeRetriever(
        [
            RetrievalResult(
                chunks=[
                    _make_chunk().model_copy(
                        update={
                            "content": (
                                "For persistent design situations, "
                                "gamma_G = 1.35 and gamma_Q = 1.5."
                            )
                        }
                    )
                ],
                parent_chunks=[],
                scores=[0.92],
                groundedness="grounded",
            ),
            RetrievalResult(
                chunks=[],
                parent_chunks=[],
                scores=[],
                groundedness="not_grounded",
            ),
        ],
        delay_seconds=0.01,
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
            ),
            EvidenceSlot(
                id="materials",
                description="Material partial factors",
                query="partial factors for materials",
                search_queries=["EN 1992 material partial factors"],
            ),
        ],
    )

    async def _fake_analyze_query(question, glossary, config, history, **kwargs):
        return analysis

    async def _fake_plan_evidence(question, query_analysis, inventory, config):
        return plan

    monkeypatch.setattr(
        "server.agents.tools.agentic_retrieve.analyze_query",
        _fake_analyze_query,
    )
    monkeypatch.setattr(
        "server.agents.tools.agentic_retrieve.plan_evidence",
        _fake_plan_evidence,
    )

    await _retrieve_agentic_impl(RunContextWrapper(deps), "请给出作用和材料的分项系数。")

    assert len(retriever.calls) == 2
    assert retriever.max_active_calls == 2
    assert deps.bundle.groundedness == "partial"
    assert deps.bundle.tool_trace[-1]["groundedness"] == "partial"
    assert deps.bundle.tool_trace[-1]["slots"] == [
        {
            "id": "actions",
            "description": "Action partial factors",
            "status": "satisfied",
            "chunk_count": 1,
            "object_labels": [],
        },
        {
            "id": "materials",
            "description": "Material partial factors",
            "status": "missing",
            "chunk_count": 0,
            "object_labels": [],
        },
    ]


@pytest.mark.asyncio
async def test_retrieve_agentic_fetches_required_table_for_value_slot(monkeypatch):
    text_chunk = _make_chunk().model_copy(
        update={
            "content": "Material partial factors are given in Table 2.1N.",
            "metadata": _make_chunk().metadata.model_copy(
                update={"ref_labels": ["Table 2.1N"], "source": "EN 1992-1-1"}
            ),
        }
    )
    table_chunk = _make_table_chunk()
    retriever = _FakeRetriever(
        RetrievalResult(
            chunks=[text_chunk],
            parent_chunks=[],
            scores=[0.8],
            groundedness="partial",
        ),
        object_chunks={"Table 2.1N": [table_chunk]},
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
        original_question="请给出材料分项系数的取值。",
        expanded_queries=["material partial factor values"],
        filters={},
        question_type=QuestionType.PARAMETER,
        intent_label="limit",
    )
    plan = EvidencePlan(
        strategy="single",
        slots=[
            EvidenceSlot(
                id="materials",
                description="Material partial factor values",
                query="material partial factor values",
                search_queries=["EN 1992 material partial factors values"],
                source_hints=["EN 1992-1-1"],
            ),
        ],
    )

    async def _fake_analyze_query(question, glossary, config, history, **kwargs):
        return analysis

    async def _fake_plan_evidence(question, query_analysis, inventory, config):
        return plan

    monkeypatch.setattr(
        "server.agents.tools.agentic_retrieve.analyze_query",
        _fake_analyze_query,
    )
    monkeypatch.setattr(
        "server.agents.tools.agentic_retrieve.plan_evidence",
        _fake_plan_evidence,
    )

    await _retrieve_agentic_impl(RunContextWrapper(deps), "请给出材料分项系数的取值。")

    assert retriever.lookup_calls == [
        {
            "label": "Table 2.1N",
            "filters": {"source": "EN 1992-1-1"},
            "top_k": 1,
        }
    ]
    assert [chunk.chunk_id for chunk in deps.bundle.ref_chunks] == ["table-2-1n"]


@pytest.mark.asyncio
async def test_retrieve_agentic_retries_value_slot_without_numeric_evidence(
    monkeypatch,
):
    empty_value_chunk = _make_chunk().model_copy(
        update={
            "chunk_id": "actions-empty",
            "content": (
                "ULS action factors should be obtained from Table A1.2(B) "
                "of EN 1990 and the National Annex."
            ),
            "metadata": _make_chunk().metadata.model_copy(
                update={"source": "EN 1990", "ref_labels": []}
            ),
        }
    )
    table_chunk = _make_table_chunk("Table A1.2(B)").model_copy(
        update={
            "chunk_id": "table-a1-2b",
            "content": "Table A1.2(B): gamma_G,sup = 1.35 and gamma_Q = 1.5 for STR/GEO persistent and transient situations.",
            "metadata": _make_table_chunk("Table A1.2(B)").metadata.model_copy(
                update={"source": "EN 1990", "object_label": "Table A1.2(B)"}
            ),
        }
    )
    retriever = _FakeRetriever(
        [
            RetrievalResult(
                chunks=[empty_value_chunk],
                parent_chunks=[],
                scores=[0.8],
                groundedness="partial",
            ),
            RetrievalResult(
                chunks=[table_chunk],
                parent_chunks=[],
                scores=[0.9],
                groundedness="grounded",
            ),
        ]
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
        original_question="请给出作用荷载分项系数的取值。",
        expanded_queries=["action load partial factor values"],
        filters={},
        question_type=QuestionType.PARAMETER,
        intent_label="limit",
    )
    plan = EvidencePlan(
        strategy="single",
        slots=[
            EvidenceSlot(
                id="actions",
                description="Action partial factor values",
                query="action partial factors",
                search_queries=["EN 1990 action partial factors"],
                source_hints=["EN 1990"],
                retry_query="EN 1990 Annex A1 Table A1.2 gamma_G gamma_Q values",
            ),
        ],
    )

    async def _fake_analyze_query(question, glossary, config, history, **kwargs):
        return analysis

    async def _fake_plan_evidence(question, query_analysis, inventory, config):
        return plan

    monkeypatch.setattr(
        "server.agents.tools.agentic_retrieve.analyze_query",
        _fake_analyze_query,
    )
    monkeypatch.setattr(
        "server.agents.tools.agentic_retrieve.plan_evidence",
        _fake_plan_evidence,
    )

    await _retrieve_agentic_impl(RunContextWrapper(deps), "请给出作用荷载分项系数的取值。")

    assert len(retriever.calls) == 2
    assert retriever.calls[1]["queries"] == [
        "EN 1990 Annex A1 Table A1.2 gamma_G gamma_Q values"
    ]
    assert deps.bundle.chunks[-1].chunk_id == "table-a1-2b"
