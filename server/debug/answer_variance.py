"""CLI for comparing repeated Euro_QA answers to the same question."""
from __future__ import annotations

import argparse
import asyncio
import json
import time
from dataclasses import dataclass
from typing import Any, Protocol

from server.config import ServerConfig
from server.core.generation import generate_answer
from server.core.query_understanding import QueryAnalysis, analyze_query
from server.core.retrieval import HybridRetriever, RetrievalResult
from server.deps import get_glossary
from server.models.schemas import Chunk, QueryResponse


class RetrieverLike(Protocol):
    async def retrieve(self, **kwargs: Any) -> RetrievalResult:
        """Run retrieval for one analyzed query."""


@dataclass
class AnswerVarianceRun:
    """Structured snapshot for one repeated answer run."""

    run_index: int
    elapsed_ms: int
    query_understanding: dict[str, Any]
    retrieval: dict[str, Any]
    answer: dict[str, Any]


def _enum_value(value: Any) -> str | None:
    """Return a stable string for enums and enum-like namespaces."""
    if value is None:
        return None
    raw = getattr(value, "value", value)
    return str(raw) if raw is not None else None


def _model_dump(value: Any) -> dict[str, Any] | None:
    """Dump Pydantic-like objects and dicts without tying tests to model classes."""
    if value is None:
        return None
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        return value.model_dump()
    return {
        key: getattr(value, key)
        for key in dir(value)
        if not key.startswith("_") and not callable(getattr(value, key))
    }


def serialize_query_understanding(analysis: QueryAnalysis) -> dict[str, Any]:
    """Serialize query-understanding output for variance comparison."""
    return {
        "original_question": analysis.original_question,
        "rewritten_query": analysis.rewritten_query,
        "expanded_queries": list(analysis.expanded_queries),
        "filters": dict(analysis.filters),
        "matched_terms": dict(analysis.matched_terms),
        "requested_objects": list(analysis.requested_objects),
        "question_type": _enum_value(analysis.question_type),
        "answer_mode": _enum_value(analysis.answer_mode),
        "intent_label": analysis.intent_label,
        "intent_confidence": analysis.intent_confidence,
        "target_hint": _model_dump(analysis.target_hint),
        "reason_short": analysis.reason_short,
        "preferred_element_type": analysis.preferred_element_type,
        "guide_hint": _model_dump(analysis.guide_hint),
        "engineering_context": _model_dump(analysis.engineering_context),
    }


def _chunk_entry(chunk: Chunk, score: float | None = None) -> dict[str, Any]:
    """Serialize one evidence chunk with enough metadata to diagnose drift."""
    meta = chunk.metadata
    entry: dict[str, Any] = {
        "chunk_id": chunk.chunk_id,
        "source": meta.source,
        "title": meta.source_title,
        "section_path": list(meta.section_path),
        "page_numbers": list(meta.page_numbers),
        "clause_ids": list(meta.clause_ids),
        "element_type": _enum_value(meta.element_type),
        "object_id": meta.object_id,
        "object_label": meta.object_label,
    }
    if score is not None:
        entry["score"] = score
    return entry


def serialize_retrieval(
    result: RetrievalResult,
    *,
    effective_filters: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Serialize retrieval output, preserving evidence ordering and scores."""
    return {
        "effective_filters": dict(effective_filters or {}),
        "groundedness": result.groundedness,
        "exact_probe_used": result.exact_probe_used,
        "anchor_chunk_ids": list(result.anchor_chunk_ids),
        "resolved_refs": list(result.resolved_refs),
        "unresolved_refs": list(result.unresolved_refs),
        "chunks": [
            _chunk_entry(chunk, result.scores[index] if index < len(result.scores) else None)
            for index, chunk in enumerate(result.chunks)
        ],
        "parent_chunks": [_chunk_entry(chunk) for chunk in result.parent_chunks],
        "ref_chunks": [_chunk_entry(chunk) for chunk in result.ref_chunks],
        "guide_chunks": [_chunk_entry(chunk) for chunk in result.guide_chunks],
        "guide_example_chunks": [
            _chunk_entry(chunk) for chunk in result.guide_example_chunks
        ],
    }


def serialize_answer(response: QueryResponse) -> dict[str, Any]:
    """Serialize answer-level fields that help separate generation drift."""
    retrieval_context = (
        response.retrieval_context.model_dump()
        if response.retrieval_context is not None
        else None
    )
    return {
        "answer": response.answer,
        "answer_preview": response.answer[:500],
        "answer_length": len(response.answer),
        "confidence": _enum_value(response.confidence),
        "degraded": response.degraded,
        "conversation_id": response.conversation_id,
        "question_type": response.question_type,
        "answer_mode": response.answer_mode,
        "groundedness": response.groundedness,
        "source_count": len(response.sources),
        "sources": [source.model_dump() for source in response.sources],
        "related_refs": list(response.related_refs),
        "retrieval_context": retrieval_context,
    }


def _sequence(values: list[dict[str, Any]], key: str) -> list[Any]:
    return [item.get(key) for item in values]


def _unique_sequences(sequences: list[list[Any]]) -> list[list[Any]]:
    seen: set[str] = set()
    unique: list[list[Any]] = []
    for sequence in sequences:
        signature = json.dumps(sequence, ensure_ascii=False, sort_keys=True)
        if signature not in seen:
            seen.add(signature)
            unique.append(sequence)
    return unique


def _score_signature(scores: list[Any]) -> list[Any]:
    """Normalize score sequences enough to avoid noise-only drift flags."""
    signature: list[Any] = []
    for score in scores:
        if isinstance(score, float):
            signature.append(round(score, 6))
        else:
            signature.append(score)
    return signature


def summarize_variance(runs: list[AnswerVarianceRun]) -> dict[str, Any]:
    """Summarize cross-run differences by pipeline layer."""
    query_payloads = [run.query_understanding for run in runs]
    retrieval_payloads = [run.retrieval for run in runs]
    answer_payloads = [run.answer for run in runs]

    expanded_query_sequences = [
        list(payload.get("expanded_queries", [])) for payload in query_payloads
    ]
    chunk_id_sequences = [
        [item.get("chunk_id") for item in payload.get("chunks", [])]
        for payload in retrieval_payloads
    ]
    chunk_score_sequences = [
        [item.get("score") for item in payload.get("chunks", [])]
        for payload in retrieval_payloads
    ]
    chunk_score_signatures = [
        _score_signature(sequence) for sequence in chunk_score_sequences
    ]
    answer_texts = [str(payload.get("answer", "")) for payload in answer_payloads]

    query_changed = (
        len(set(_sequence(query_payloads, "rewritten_query"))) > 1
        or len(_unique_sequences(expanded_query_sequences)) > 1
        or len(set(_sequence(query_payloads, "answer_mode"))) > 1
        or len(set(_sequence(query_payloads, "question_type"))) > 1
        or len(set(_sequence(query_payloads, "intent_label"))) > 1
    )
    retrieval_changed = (
        len(_unique_sequences(chunk_id_sequences)) > 1
        or len(_unique_sequences(chunk_score_signatures)) > 1
        or len(set(_sequence(retrieval_payloads, "groundedness"))) > 1
        or len(set(_sequence(retrieval_payloads, "exact_probe_used"))) > 1
    )
    answer_changed = (
        len(set(_sequence(answer_payloads, "confidence"))) > 1
        or len(set(_sequence(answer_payloads, "degraded"))) > 1
        or len(set(answer_texts)) > 1
        or len(set(_sequence(answer_payloads, "answer_mode"))) > 1
        or len(set(_sequence(answer_payloads, "groundedness"))) > 1
    )

    likely_layer = "stable"
    if query_changed:
        likely_layer = "query_understanding"
    elif retrieval_changed:
        likely_layer = "retrieval"
    elif answer_changed:
        likely_layer = "generation"

    return {
        "run_count": len(runs),
        "likely_variance_layer": likely_layer,
        "query_understanding_changed": query_changed,
        "retrieval_changed": retrieval_changed,
        "generation_changed": answer_changed,
        "rewritten_queries": _sequence(query_payloads, "rewritten_query"),
        "answer_modes": _sequence(query_payloads, "answer_mode"),
        "question_types": _sequence(query_payloads, "question_type"),
        "intent_labels": _sequence(query_payloads, "intent_label"),
        "groundedness": _sequence(retrieval_payloads, "groundedness"),
        "confidences": _sequence(answer_payloads, "confidence"),
        "degraded": _sequence(answer_payloads, "degraded"),
        "chunk_id_sequences": chunk_id_sequences,
        "chunk_score_sequences": chunk_score_sequences,
        "answer_lengths": [len(text) for text in answer_texts],
    }


async def run_once(
    *,
    question: str,
    run_index: int,
    config: ServerConfig,
    retriever: RetrieverLike,
    glossary: dict[str, str],
    domain: str | None = None,
) -> AnswerVarianceRun:
    """Run one non-streaming Euro_QA answer pipeline and capture debug fields."""
    started_at = time.perf_counter()
    analysis = await analyze_query(question, glossary, config)
    filters = dict(analysis.filters)
    if domain:
        filters["source"] = domain

    result = await retriever.retrieve(
        queries=analysis.expanded_queries,
        original_query=analysis.original_question,
        filters=filters,
        answer_mode=analysis.answer_mode.value if analysis.answer_mode else None,
        intent_label=analysis.intent_label,
        question_type=analysis.question_type.value if analysis.question_type else None,
        guide_hint=analysis.guide_hint,
        target_hint=analysis.target_hint,
        requested_objects=analysis.requested_objects,
        preferred_element_type=analysis.preferred_element_type,
    )
    response = await generate_answer(
        question=question,
        chunks=result.chunks,
        parent_chunks=result.parent_chunks,
        scores=result.scores,
        glossary_terms=analysis.matched_terms,
        conversation_history=[],
        config=config,
        ref_chunks=result.ref_chunks,
        guide_chunks=result.guide_chunks,
        guide_example_chunks=result.guide_example_chunks,
        question_type=analysis.question_type,
        engineering_context=analysis.engineering_context,
        answer_mode=analysis.answer_mode.value if analysis.answer_mode else None,
        groundedness=result.groundedness,
        resolved_refs=result.resolved_refs,
        unresolved_refs=result.unresolved_refs,
        intent_label=analysis.intent_label,
    )
    response = response.model_copy(
        update={
            "question_type": analysis.question_type.value
            if analysis.question_type
            else None,
            "engineering_context": analysis.engineering_context.model_dump()
            if analysis.engineering_context
            else None,
            "answer_mode": analysis.answer_mode.value if analysis.answer_mode else None,
            "groundedness": result.groundedness,
        }
    )

    return AnswerVarianceRun(
        run_index=run_index,
        elapsed_ms=int((time.perf_counter() - started_at) * 1000),
        query_understanding=serialize_query_understanding(analysis),
        retrieval=serialize_retrieval(result, effective_filters=filters),
        answer=serialize_answer(response),
    )


async def run_repeated(
    *,
    question: str,
    runs: int,
    config: ServerConfig | None = None,
    retriever: RetrieverLike | None = None,
    glossary: dict[str, str] | None = None,
    domain: str | None = None,
) -> dict[str, Any]:
    """Run the same question multiple times and return structured comparison."""
    if runs < 1:
        raise ValueError("runs must be >= 1")

    cfg = config or ServerConfig()
    own_retriever = retriever is None
    active_retriever: RetrieverLike = retriever or HybridRetriever(cfg)
    active_glossary = get_glossary() if glossary is None else glossary
    snapshots: list[AnswerVarianceRun] = []
    try:
        for index in range(1, runs + 1):
            snapshots.append(
                await run_once(
                    question=question,
                    run_index=index,
                    config=cfg,
                    retriever=active_retriever,
                    glossary=active_glossary,
                    domain=domain,
                )
            )
    finally:
        if own_retriever and hasattr(active_retriever, "close"):
            await active_retriever.close()  # type: ignore[attr-defined]

    return {
        "question": question,
        "domain": domain,
        "summary": summarize_variance(snapshots),
        "runs": [
            {
                "run_index": item.run_index,
                "elapsed_ms": item.elapsed_ms,
                "query_understanding": item.query_understanding,
                "retrieval": item.retrieval,
                "answer": item.answer,
            }
            for item in snapshots
        ],
    }


def render_markdown_report(report: dict[str, Any]) -> str:
    """Render a compact human-readable comparison report."""
    summary = report["summary"]
    lines = [
        f"# Answer Variance Debug: {report['question']}",
        "",
        f"- runs: {summary['run_count']}",
        f"- likely variance layer: {summary['likely_variance_layer']}",
        f"- query_understanding_changed: {summary['query_understanding_changed']}",
        f"- retrieval_changed: {summary['retrieval_changed']}",
        f"- generation_changed: {summary['generation_changed']}",
        "",
        "## Per-run Summary",
        "",
        "| run | mode | groundedness | confidence | chunks | answer_chars | elapsed_ms |",
        "| --- | --- | --- | --- | --- | ---: | ---: |",
    ]
    for run in report["runs"]:
        chunk_ids = [
            chunk["chunk_id"] for chunk in run["retrieval"].get("chunks", [])
        ]
        lines.append(
            "| {run} | {mode} | {groundedness} | {confidence} | {chunks} | {chars} | {elapsed} |".format(
                run=run["run_index"],
                mode=run["query_understanding"].get("answer_mode") or "",
                groundedness=run["retrieval"].get("groundedness") or "",
                confidence=run["answer"].get("confidence") or "",
                chunks=", ".join(chunk_ids) or "-",
                chars=run["answer"].get("answer_length", 0),
                elapsed=run["elapsed_ms"],
            )
            )

    lines.extend(["", "## Answer Preview"])
    for run in report["runs"]:
        answer = run["answer"]
        preview = _markdown_inline(answer.get("answer_preview") or "")
        lines.extend(
            [
                "",
                f"### Run {run['run_index']}",
                f"- confidence: {answer.get('confidence')}",
                f"- degraded: {answer.get('degraded')}",
                f"- preview: {preview or '-'}",
            ]
        )

    lines.extend(["", "## Query Understanding"])
    for run in report["runs"]:
        understanding = run["query_understanding"]
        lines.extend(
            [
                "",
                f"### Run {run['run_index']}",
                f"- rewritten_query: {understanding.get('rewritten_query')}",
                f"- expanded_queries: {json.dumps(understanding.get('expanded_queries', []), ensure_ascii=False)}",
                f"- filters: {json.dumps(understanding.get('filters', {}), ensure_ascii=False, sort_keys=True)}",
                f"- target_hint: {json.dumps(understanding.get('target_hint'), ensure_ascii=False, sort_keys=True)}",
            ]
        )

    lines.extend(["", "## Retrieval Evidence"])
    for run in report["runs"]:
        lines.append(f"\n### Run {run['run_index']}")
        for chunk in run["retrieval"].get("chunks", []):
            lines.append(
                "- {chunk_id} score={score} source={source} clause={clause}".format(
                    chunk_id=chunk.get("chunk_id"),
                    score=chunk.get("score"),
                    source=chunk.get("source"),
                    clause=", ".join(chunk.get("clause_ids", [])),
                )
            )

    return "\n".join(lines) + "\n"


def _markdown_inline(value: str) -> str:
    """Escape a value for compact Markdown list/table cells."""
    return value.replace("\n", " ").replace("|", "\\|").strip()


def _positive_int(value: str) -> int:
    """Parse a positive integer for user-facing CLI options."""
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a positive integer") from exc
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the Euro_QA answer pipeline repeatedly and compare drift."
    )
    parser.add_argument("question", help="Question to run repeatedly.")
    parser.add_argument("-n", "--runs", type=_positive_int, default=3, help="Repeat count.")
    parser.add_argument("--domain", help="Optional source/domain filter.")
    parser.add_argument(
        "--output",
        choices=("json", "markdown"),
        default="markdown",
        help="Output format.",
    )
    return parser.parse_args()


async def _amain() -> None:
    args = _parse_args()
    report = await run_repeated(
        question=args.question,
        runs=args.runs,
        domain=args.domain,
    )
    if args.output == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render_markdown_report(report))


def main() -> None:
    """CLI entry point."""
    asyncio.run(_amain())


if __name__ == "__main__":
    main()
