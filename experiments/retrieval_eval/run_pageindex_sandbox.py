"""Run retrieval eval against a PageIndex vectorless sandbox retriever."""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from server.config import ServerConfig  # noqa: E402
from server.core.query_understanding import analyze_query  # noqa: E402
from server.deps import get_glossary  # noqa: E402

from experiments.retrieval_eval.dataset.schema import load_questions, to_jsonable  # noqa: E402
from experiments.retrieval_eval.metrics import (  # noqa: E402
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
from experiments.retrieval_eval.pageindex_sandbox import PageIndexSandboxRetriever  # noqa: E402
from experiments.retrieval_eval.runner import _chunk_summary, _jsonable  # noqa: E402


async def _main() -> None:
    args = _parse_args()
    questions = load_questions(args.questions)
    if args.limit:
        questions = questions[: args.limit]
    config = ServerConfig()
    if args.mode == "agent":
        from experiments.retrieval_eval.pageindex_agent_sandbox import (  # noqa: PLC0415
            PageIndexAgentSandboxRetriever,
        )

        retriever = PageIndexAgentSandboxRetriever(
            str(args.workspace),
            config=config,
            max_docs=args.max_docs,
            max_turns=args.max_turns,
        )
    else:
        retriever = PageIndexSandboxRetriever(
            args.workspace,
            max_docs=args.max_docs,
            top_k=args.top_k,
        )
    try:
        result = await run_pageindex_evaluation(
            questions=questions,
            retriever=retriever,
            glossary=get_glossary(),
            config=config,
            top_k=args.top_k,
            workspace=args.workspace,
            mode=args.mode,
        )
    finally:
        await retriever.close()

    if args.compare_to:
        result["comparison"] = _compare_to_baseline(result, args.compare_to)

    output = args.output or _default_output_path()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {output}")
    print(json.dumps(result["metrics"], ensure_ascii=False, indent=2))
    if "comparison" in result:
        print(json.dumps(result["comparison"], ensure_ascii=False, indent=2))


async def run_pageindex_evaluation(
    *,
    questions: list[Any],
    retriever: Any,
    glossary: dict[str, str],
    config: ServerConfig,
    top_k: int,
    workspace: Path,
    mode: str,
) -> dict[str, Any]:
    """Run analyze_query -> vectorless PageIndex sandbox -> existing metrics."""
    per_question: list[dict[str, Any]] = []
    for question in questions:
        try:
            analysis = await analyze_query(question.question, glossary, config)
            result, trace = await retriever.retrieve_with_trace(
                queries=analysis.expanded_queries,
                original_query=analysis.original_question,
                filters=analysis.filters,
                intent_label=analysis.intent_label,
                target_hint=analysis.target_hint,
                requested_objects=getattr(analysis, "requested_objects", []),
            )
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
        "config": {
            "top_k": top_k,
            "retriever": f"pageindex-vectorless-sandbox-{mode}",
            "workspace": str(workspace),
            "max_docs": retriever.max_docs,
            "indexed_documents": _indexed_document_summary(retriever),
        },
        "metrics": _aggregate_metrics(per_question),
        "per_question": per_question,
        "buckets": bucket_summary(per_question),
    }


def _question_metrics(question: Any, result: Any, chunks: list[Any], top_k: int) -> dict[str, float]:
    return {
        "doc_recall@10": doc_recall_at_k(chunks, question.expected_documents, min(10, top_k)),
        "section_recall@1": section_recall_at_k(chunks, question.expected_documents, 1),
        "section_recall@3": section_recall_at_k(chunks, question.expected_documents, 3),
        "section_recall@5": section_recall_at_k(chunks, question.expected_documents, 5),
        "section_recall@10": section_recall_at_k(chunks, question.expected_documents, min(10, top_k)),
        "mrr_section": mrr_section(chunks, question.expected_sections),
        "ndcg@10": ndcg_at_k(chunks, question.expected_sections, min(10, top_k)),
        "keyword_recall@10": keyword_recall_at_k(chunks, question.expected_keywords, min(10, top_k)),
        "concept_recall@10": concept_recall_at_k(chunks, question.expected_concepts, min(10, top_k)),
        "direct_ref_resolution_rate": direct_ref_resolution_rate(
            result,
            [ref for doc in question.expected_documents for ref in doc.objects],
        ),
        "noise_intrusion_rate": noise_intrusion_rate(chunks, question.must_not_include),
    }


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


def _compare_to_baseline(result: dict[str, Any], baseline_path: Path) -> dict[str, Any]:
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    baseline_metrics = baseline.get("metrics") or {}
    current_metrics = result.get("metrics") or {}
    comparison: dict[str, Any] = {"baseline": str(baseline_path), "delta": {}}
    for key, value in current_metrics.items():
        if not isinstance(value, int | float):
            continue
        baseline_value = baseline_metrics.get(key)
        if isinstance(baseline_value, int | float):
            comparison["delta"][key] = round(value - baseline_value, 4)
    return comparison


def _indexed_document_summary(retriever: PageIndexSandboxRetriever) -> list[dict[str, Any]]:
    return [
        {
            "doc_id": doc_id,
            "doc_name": doc.get("doc_name"),
            "type": doc.get("type"),
            "line_count": doc.get("line_count"),
            "page_count": doc.get("page_count"),
        }
        for doc_id, doc in retriever.workspace.documents.items()
    ]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--workspace",
        type=Path,
        default=Path("/Users/youngz/webdav/Euro_QA_pageindex/data/pageindex_workspace_md"),
    )
    parser.add_argument(
        "--questions",
        type=Path,
        default=Path("experiments/retrieval_eval/dataset/test_questions_v2.json"),
    )
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--compare-to", type=Path, default=None)
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--max-docs", type=int, default=3)
    parser.add_argument("--max-turns", type=int, default=8)
    parser.add_argument("--mode", choices=["deterministic", "agent"], default="deterministic")
    parser.add_argument("--limit", type=int, default=0)
    return parser.parse_args()


def _default_output_path() -> Path:
    return Path("experiments/retrieval_eval/results/pageindex-vectorless-sandbox.json")


if __name__ == "__main__":
    asyncio.run(_main())
