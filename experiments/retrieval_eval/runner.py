"""Run retrieval-only evaluation against v2 golden questions."""

from __future__ import annotations

import statistics
from typing import Any

from server.config import ServerConfig
from server.core.query_understanding import analyze_query

from experiments.retrieval_eval.dataset.schema import QuestionV2, to_jsonable
from experiments.retrieval_eval.metrics import (
    bucket_summary,
    concept_recall_at_k,
    direct_ref_resolution_rate,
    doc_recall_at_k,
    keyword_recall_at_k,
    mrr_section,
    ndcg_at_k,
    noise_intrusion_rate,
    section_recall_at_k,
)
from experiments.retrieval_eval.trace.wrapper import TracingHybridRetriever


async def run_evaluation(
    questions: list[QuestionV2],
    retriever: TracingHybridRetriever,
    glossary: dict[str, str],
    config: ServerConfig,
    top_k: int = 10,
    exp: str = "baseline",
) -> dict:
    """Run analyze_query → retrieve_with_trace → metric calculation for each question."""
    per_question: list[dict[str, Any]] = []

    for question in questions:
        try:
            analysis = await analyze_query(question.question, glossary, config)
            if exp in ("rerank-english", "rerank-en-fill"):
                retriever._force_rerank_query = _first_query(analysis.expanded_queries)
            try:
                result, trace = await retriever.retrieve_with_trace(
                    queries=analysis.expanded_queries,
                    original_query=analysis.original_question,
                    filters=analysis.filters,
                    intent_label=analysis.intent_label,
                    target_hint=analysis.target_hint,
                    requested_objects=getattr(analysis, "requested_objects", []),
                )
            finally:
                retriever._force_rerank_query = None
            chunks = result.chunks[:top_k]
            metrics = _question_metrics(question, result, chunks, top_k)
            per_question.append(
                {
                    **to_jsonable(question),
                    "analysis": {
                        "expanded_queries": list(analysis.expanded_queries),
                        "intent_label": analysis.intent_label,
                        "filters": dict(analysis.filters),
                        "target_hint": _jsonable(analysis.target_hint),
                        "requested_objects": list(getattr(analysis, "requested_objects", []) or []),
                    },
                    "metrics": metrics,
                    "trace": trace.to_dict(),
                    "retrieved_chunks": [
                        _chunk_summary(chunk, score)
                        for chunk, score in zip(chunks, result.scores, strict=False)
                    ],
                    "groundedness": result.groundedness,
                    "resolved_refs": list(result.resolved_refs),
                    "unresolved_refs": list(result.unresolved_refs),
                }
            )
        except Exception as exc:
            per_question.append(
                {
                    **to_jsonable(question),
                    "error": f"{type(exc).__name__}: {exc}",
                    "metrics": {},
                    "trace": {},
                }
            )

    return {
        "config": _config_summary(config, top_k),
        "metrics": _aggregate_metrics(per_question),
        "per_question": per_question,
        "buckets": bucket_summary(per_question),
    }


def _question_metrics(
    question: QuestionV2,
    result: Any,
    chunks: list[Any],
    top_k: int,
) -> dict[str, float]:
    metrics: dict[str, float] = {
        "doc_recall@10": doc_recall_at_k(chunks, question.expected_documents, top_k),
        "section_recall@1": section_recall_at_k(chunks, question.expected_documents, 1),
        "section_recall@3": section_recall_at_k(chunks, question.expected_documents, 3),
        "section_recall@5": section_recall_at_k(chunks, question.expected_documents, 5),
        "section_recall@10": section_recall_at_k(chunks, question.expected_documents, top_k),
        "mrr_section": mrr_section(chunks, question.expected_sections),
        "ndcg@10": ndcg_at_k(chunks, question.expected_sections, top_k),
        "keyword_recall@10": keyword_recall_at_k(chunks, question.expected_keywords, top_k),
        "concept_recall@10": concept_recall_at_k(chunks, question.expected_concepts, top_k),
        "direct_ref_resolution_rate": direct_ref_resolution_rate(
            result,
            _expected_direct_refs(question),
        ),
        "noise_intrusion_rate": noise_intrusion_rate(chunks, question.must_not_include),
    }
    return metrics


def _aggregate_metrics(per_question: list[dict[str, Any]]) -> dict[str, float | int]:
    metric_names = sorted(
        {
            name
            for row in per_question
            for name in (row.get("metrics") or {})
        }
    )
    summary: dict[str, float | int] = {
        "total": len(per_question),
        "successful": sum(1 for row in per_question if not row.get("error")),
    }
    for name in metric_names:
        values = [
            value
            for row in per_question
            for value in [(row.get("metrics") or {}).get(name)]
            if isinstance(value, int | float)
        ]
        if values:
            summary[name] = round(statistics.fmean(values), 4)
    return summary


def _expected_direct_refs(question: QuestionV2) -> list[str]:
    refs: list[str] = []
    for doc in question.expected_documents:
        refs.extend(doc.objects)
    return refs


def _first_query(queries: list[str]) -> str | None:
    for query in queries:
        normalized = (query or "").strip()
        if normalized:
            return normalized
    return None


def _chunk_summary(chunk: Any, score: float | None = None) -> dict[str, Any]:
    meta = chunk.metadata
    payload: dict[str, Any] = {
        "chunk_id": chunk.chunk_id,
        "source": meta.source,
        "section_path": list(meta.section_path),
        "clause_ids": list(meta.clause_ids),
        "element_type": getattr(meta.element_type, "value", meta.element_type),
        "object_label": meta.object_label,
    }
    if score is not None:
        payload["score"] = float(score)
    return payload


def _config_summary(config: ServerConfig, top_k: int) -> dict[str, Any]:
    return {
        "top_k": top_k,
        "vector_top_k": config.vector_top_k,
        "bm25_top_k": config.bm25_top_k,
        "rerank_top_n": config.rerank_top_n,
        "milvus_collection": config.milvus_collection,
        "es_index": config.es_index,
        "embedding_provider": config.embedding_provider,
        "rerank_provider": config.rerank_provider,
    }


def _jsonable(value: Any) -> Any:
    if isinstance(value, int | float | str | bool) or value is None:
        return value
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    return str(value)
