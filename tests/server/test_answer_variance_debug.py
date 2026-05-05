"""Tests for repeated-answer variance debug helpers."""
from __future__ import annotations

import argparse
import json

import pytest

from server.core.query_understanding import QueryAnalysis
from server.core.retrieval import RetrievalResult
from server.debug import answer_variance
from server.models.schemas import AnswerMode, ElementType, QueryResponse, QuestionType, Source


def _run_snapshot(index: int, *, chunks: list[str], confidence: str = "high"):
    return answer_variance.AnswerVarianceRun(
        run_index=index,
        elapsed_ms=10,
        query_understanding={
            "rewritten_query": "design working life",
            "expanded_queries": ["design working life"],
            "answer_mode": "exact",
            "question_type": "rule",
            "intent_label": "definition",
        },
        retrieval={
            "groundedness": "grounded",
            "exact_probe_used": True,
            "chunks": [{"chunk_id": chunk_id, "score": 0.9} for chunk_id in chunks],
        },
        answer={
            "answer": f"answer {index}",
            "confidence": confidence,
            "degraded": False,
            "answer_mode": "exact",
            "groundedness": "grounded",
        },
    )


class TestAnswerVarianceSerialization:
    def test_serialize_retrieval_preserves_chunk_ids_scores_and_metadata(
        self,
        sample_text_chunk,
        sample_table_chunk,
    ):
        result = RetrievalResult(
            chunks=[sample_text_chunk, sample_table_chunk],
            parent_chunks=[],
            scores=[0.91, 0.82],
            ref_chunks=[sample_table_chunk],
            groundedness="grounded",
            anchor_chunk_ids=["chunk_023"],
            exact_probe_used=True,
            resolved_refs=["Table 2.1"],
        )

        payload = answer_variance.serialize_retrieval(result)

        assert payload["groundedness"] == "grounded"
        assert payload["exact_probe_used"] is True
        assert payload["chunks"][0]["chunk_id"] == "chunk_023"
        assert payload["chunks"][0]["score"] == 0.91
        assert payload["chunks"][1]["element_type"] == "table"
        assert payload["ref_chunks"][0]["chunk_id"] == "chunk_t_2_1"

    def test_summarize_variance_flags_retrieval_drift_before_generation(self):
        runs = [
            _run_snapshot(1, chunks=["chunk-a", "chunk-b"], confidence="high"),
            _run_snapshot(2, chunks=["chunk-b", "chunk-a"], confidence="low"),
        ]

        summary = answer_variance.summarize_variance(runs)

        assert summary["retrieval_changed"] is True
        assert summary["generation_changed"] is True
        assert summary["likely_variance_layer"] == "retrieval"
        assert summary["chunk_id_sequences"] == [
            ["chunk-a", "chunk-b"],
            ["chunk-b", "chunk-a"],
        ]

    def test_summarize_variance_ignores_tiny_score_noise(self):
        runs = [
            _run_snapshot(1, chunks=["chunk-a"], confidence="high"),
            _run_snapshot(2, chunks=["chunk-a"], confidence="high"),
        ]
        runs[0].answer["answer"] = "same answer"
        runs[1].answer["answer"] = "same answer"
        runs[0].retrieval["chunks"][0]["score"] = 0.9000000001
        runs[1].retrieval["chunks"][0]["score"] = 0.9000000002

        summary = answer_variance.summarize_variance(runs)

        assert summary["retrieval_changed"] is False
        assert summary["likely_variance_layer"] == "stable"

    def test_serialize_answer_payload_is_json_serializable(self):
        response = QueryResponse(
            answer="Use Table 2.1.",
            sources=[
                Source(
                    file="EN 1990:2002",
                    document_id="EN1990_2002",
                    element_type=ElementType.TABLE,
                    title="Eurocode - Basis of structural design",
                    section="2.3 Design working life",
                    page=28,
                    clause="Table 2.1",
                    original_text="Table 2.1 - Indicative design working life",
                    locator_text="Table 2.1 - Indicative design working life",
                    translation="",
                )
            ],
            related_refs=["Table 2.1"],
            confidence="high",
        )

        payload = answer_variance.serialize_answer(response)

        assert payload["sources"][0]["element_type"] == "table"
        json.dumps(payload, ensure_ascii=False)

    def test_markdown_report_includes_answer_previews(self):
        run = _run_snapshot(1, chunks=["chunk-a"], confidence="high")
        run.answer["answer_preview"] = "Line 1\nLine 2 | with pipe"
        report = {
            "question": "设计使用年限是什么？",
            "summary": answer_variance.summarize_variance([run]),
            "runs": [
                {
                    "run_index": run.run_index,
                    "elapsed_ms": run.elapsed_ms,
                    "query_understanding": run.query_understanding,
                    "retrieval": run.retrieval,
                    "answer": run.answer,
                }
            ],
        }

        rendered = answer_variance.render_markdown_report(report)

        assert "## Answer Preview" in rendered
        assert "Line 1 Line 2 \\| with pipe" in rendered

    def test_positive_int_rejects_non_positive_runs(self):
        with pytest.raises(argparse.ArgumentTypeError):
            answer_variance._positive_int("0")


class TestAnswerVarianceRunner:
    @pytest.mark.asyncio
    async def test_run_repeated_uses_mocked_pipeline_without_external_services(
        self,
        monkeypatch,
        sample_text_chunk,
        sample_table_chunk,
    ):
        analyses: list[QueryAnalysis] = [
            QueryAnalysis(
                original_question="设计使用年限是什么？",
                expanded_queries=["design working life"],
                filters={},
                question_type=QuestionType.RULE,
                answer_mode=AnswerMode.EXACT,
                intent_label="definition",
            ),
            QueryAnalysis(
                original_question="设计使用年限是什么？",
                expanded_queries=["design working lifetime"],
                filters={},
                question_type=QuestionType.RULE,
                answer_mode=AnswerMode.EXACT,
                intent_label="definition",
            ),
        ]

        async def fake_analyze_query(question, glossary, config):
            del question, glossary, config
            return analyses.pop(0)

        async def fake_generate_answer(**kwargs):
            return QueryResponse(
                answer=f"ok from {kwargs['chunks'][0].chunk_id}",
                sources=[],
                related_refs=[],
                confidence="high",
            )

        class FakeRetriever:
            def __init__(self):
                self.calls = 0

            async def retrieve(self, **kwargs):
                self.calls += 1
                chunk = sample_text_chunk if self.calls == 1 else sample_table_chunk
                return RetrievalResult(
                    chunks=[chunk],
                    parent_chunks=[],
                    scores=[0.9],
                    groundedness="grounded",
                )

        monkeypatch.setattr(answer_variance, "analyze_query", fake_analyze_query)
        monkeypatch.setattr(answer_variance, "generate_answer", fake_generate_answer)

        report = await answer_variance.run_repeated(
            question="设计使用年限是什么？",
            runs=2,
            retriever=FakeRetriever(),
            glossary={},
        )

        assert report["summary"]["likely_variance_layer"] == "query_understanding"
        assert report["runs"][0]["query_understanding"]["rewritten_query"] == (
            "design working life"
        )
        assert report["runs"][1]["retrieval"]["chunks"][0]["chunk_id"] == "chunk_t_2_1"
