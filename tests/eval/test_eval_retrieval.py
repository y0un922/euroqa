"""Unit tests for retrieval evaluation helpers."""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from server.core.retrieval import RetrievalResult
from server.models.schemas import Chunk, ChunkMetadata, ElementType
from tests.eval import eval_retrieval


def _make_chunk(
    chunk_id: str,
    content: str,
    *,
    object_label: str = "",
    clause_ids: list[str] | None = None,
) -> Chunk:
    return Chunk(
        chunk_id=chunk_id,
        content=content,
        embedding_text=content,
        metadata=ChunkMetadata(
            source="EN 1992-1-1:2004",
            source_title="Concrete structures",
            section_path=["3.1.7"],
            page_numbers=[31],
            page_file_index=[30],
            clause_ids=clause_ids or [],
            element_type=ElementType.TABLE if object_label.startswith("Table ") else ElementType.TEXT,
            object_label=object_label,
        ),
    )


class TestEvalMetricsHelpers:
    def test_direct_ref_hits_match_resolved_refs_and_ref_chunks(self):
        result = RetrievalResult(
            chunks=[],
            parent_chunks=[],
            scores=[],
            ref_chunks=[
                _make_chunk("table-3-1", "table content", object_label="Table 3.1"),
            ],
            resolved_refs=["Table 3.1"],
            unresolved_refs=[],
        )

        hits = eval_retrieval._direct_ref_hits(result, ["Table 3.1", "Figure 3.3"])

        assert hits == ["Table 3.1"]

    def test_reference_closure_satisfied_requires_grounded_and_no_missing_refs(self):
        result = RetrievalResult(
            chunks=[],
            parent_chunks=[],
            scores=[],
            groundedness="grounded",
            resolved_refs=["Table 3.1"],
            unresolved_refs=[],
        )

        assert eval_retrieval._reference_closure_satisfied(result, ["Table 3.1"]) is True
        degraded_result = RetrievalResult(
            chunks=[],
            parent_chunks=[],
            scores=[],
            groundedness="exact_not_grounded",
            resolved_refs=["Table 3.1"],
            unresolved_refs=[],
        )
        assert (
            eval_retrieval._reference_closure_satisfied(
                degraded_result,
                ["Table 3.1"],
            )
            is False
        )

    def test_noise_intrusion_rate_scales_with_forbidden_hits(self):
        rate = eval_retrieval._noise_intrusion_rate(["noise-a"], ["noise-a", "noise-b"])

        assert rate == pytest.approx(0.5)


@pytest.mark.asyncio
async def test_evaluate_passes_requested_objects_and_reports_cross_ref_metrics(
    tmp_path,
    monkeypatch,
):
    questions_path = tmp_path / "test_questions.json"
    questions_path.write_text(
        json.dumps(
            [
                {
                    "id": "cross-ref-1",
                    "question": "3.1.7 里面混凝土受压应变限值怎么取？",
                    "category": "exact_cross_ref",
                    "expected_sections": [],
                    "expected_keywords": [],
                    "expected_mode": "exact",
                    "expected_document": "EN 1992-1-1:2004",
                    "expected_direct_refs": ["Table 3.1"],
                    "expected_reference_closure": True,
                    "must_not_include": [],
                }
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(eval_retrieval, "QUESTIONS_PATH", questions_path)

    seen_retrieve_calls: list[dict[str, object]] = []

    async def _fake_analyze_query(question, glossary, config):
        return SimpleNamespace(
            expanded_queries=[question],
            rewritten_query=question,
            original_question=question,
            filters={},
            answer_mode=SimpleNamespace(value="exact"),
            intent_label="limit",
            target_hint=SimpleNamespace(
                document="EN 1992-1-1:2004",
                clause="3.1.7",
                object="Table 3.1",
            ),
            requested_objects=["Table 3.1"],
        )

    class _FakeRetriever:
        def __init__(self, config):
            self.config = config

        async def retrieve(self, **kwargs):
            seen_retrieve_calls.append(kwargs)
            return RetrievalResult(
                chunks=[],
                parent_chunks=[],
                scores=[],
                groundedness="grounded",
                ref_chunks=[
                    _make_chunk(
                        "table-3-1",
                        "Table 3.1 Strength and deformation characteristics for concrete.",
                        object_label="Table 3.1",
                        clause_ids=["Table 3.1"],
                    )
                ],
                resolved_refs=["Table 3.1"],
                unresolved_refs=[],
            )

        async def close(self):
            return None

    monkeypatch.setattr(eval_retrieval, "analyze_query", _fake_analyze_query)
    monkeypatch.setattr(eval_retrieval, "HybridRetriever", _FakeRetriever)

    summary = await eval_retrieval.evaluate(top_k=1)

    assert seen_retrieve_calls[0]["requested_objects"] == ["Table 3.1"]
    assert summary["metrics"]["direct_ref_resolution_rate"] == 1.0
    assert summary["metrics"]["reference_closure_rate"] == 1.0
