from __future__ import annotations

from agents import RunContextWrapper

from server.agents.deps import QADeps
from server.core.retrieval import RetrievalResult

DEFAULT_TOP_K = 8
MIN_TOP_K = 3
MAX_TOP_K = 16


def base_filters(ctx: RunContextWrapper[QADeps] | QADeps) -> dict[str, object]:
    """Return request-scoped retrieval filters that must never be relaxed."""
    deps = ctx.context if isinstance(ctx, RunContextWrapper) else ctx
    filters: dict[str, object] = {}
    if deps.domain_filter:
        filters["source"] = deps.domain_filter
    if deps.sources_filter:
        filters["sources"] = deps.sources_filter
    return filters


def merge_retrieval_filters(
    required_filters: dict[str, object],
    query_filters: dict[str, str] | None = None,
) -> dict[str, object]:
    """Merge query-derived filters under request-scoped permission filters."""
    merged: dict[str, object] = {}
    for key, value in (query_filters or {}).items():
        if value:
            merged[key] = value
    for key, value in required_filters.items():
        if value:
            merged[key] = value
    return merged


def clamp_top_k(top_k: int, *, default: int = DEFAULT_TOP_K) -> int:
    """Clamp user/model supplied top_k into the supported retrieval range."""
    try:
        value = int(top_k)
    except (TypeError, ValueError):
        value = default
    return min(max(value, MIN_TOP_K), MAX_TOP_K)


def limit_retrieval_result(result: RetrievalResult, top_k: int) -> RetrievalResult:
    """Trim evidence attached to generation while preserving supplements."""
    effective_top_k = clamp_top_k(top_k)
    return RetrievalResult(
        chunks=result.chunks[:effective_top_k],
        parent_chunks=result.parent_chunks[:effective_top_k],
        scores=result.scores[:effective_top_k],
        guide_chunks=result.guide_chunks[: max(1, effective_top_k // 2)],
        guide_example_chunks=result.guide_example_chunks[
            : max(1, effective_top_k // 3)
        ],
        ref_chunks=result.ref_chunks[: max(2, effective_top_k // 2)],
        groundedness=result.groundedness,
        resolved_refs=result.resolved_refs,
        unresolved_refs=result.unresolved_refs,
        per_query_candidate_counts=result.per_query_candidate_counts,
    )
