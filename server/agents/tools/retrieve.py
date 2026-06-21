from __future__ import annotations

from agents import RunContextWrapper, function_tool

from server.agents.deps import QADeps
from server.agents.tool_progress import RETRIEVE_STEPS, ToolProgressEmitter
from server.core.query_understanding import (
    FilterValue,
    analyze_query,
    build_filters_from_intent,
)
from server.core.retrieval import RetrievalResult

_DEFAULT_TOP_K = 8
_MIN_TOP_K = 3
_MAX_TOP_K = 12


@function_tool
async def retrieve(
    ctx: RunContextWrapper[QADeps],
    query: str,
    top_k: int = _DEFAULT_TOP_K,
    standard_family: str | None = None,
    doc_type: str | None = None,
    doc_version: str | list[str] | None = None,
) -> str:
    """搜索欧洲规范知识库，可用 top_k 控制返回给回答生成的证据数量。

    通常只传 query/top_k；当需要显式切换规范族、文档类型或版本时，
    再传 standard_family/doc_type/doc_version 覆盖自动路由。
    """
    return await _retrieve_impl(
        ctx,
        query,
        top_k=top_k,
        standard_family=standard_family,
        doc_type=doc_type,
        doc_version=doc_version,
    )


async def _retrieve_impl(
    ctx: RunContextWrapper[QADeps],
    query: str,
    top_k: int = _DEFAULT_TOP_K,
    standard_family: str | None = None,
    doc_type: str | None = None,
    doc_version: str | list[str] | None = None,
) -> str:
    if ctx.context.bundle.groundedness == "grounded":
        ctx.context.bundle.tool_trace.append(
            {
                "tool": "retrieve",
                "query": query,
                "skipped": True,
                "reason": "already_grounded",
            }
        )
        return (
            "跳过检索：当前证据已充足 "
            f"(groundedness=grounded, {ctx.context.bundle.chunk_count} 个片段)。"
            " 请直接基于已有证据回复。"
        )

    effective_top_k = _clamp_top_k(top_k)
    progress = ToolProgressEmitter("retrieve", ctx.context.tool_progress)
    history = (
        ctx.context.conversation_state.history
        if ctx.context.conversation_state
        else None
    )

    await progress.start(
        "query_understanding",
        RETRIEVE_STEPS["query_understanding"]["title"],
        "正在理解问题并扩展检索查询",
    )
    analysis = await analyze_query(
        query,
        ctx.context.glossary,
        ctx.context.config,
        history,
    )
    effective_original = analysis.rewritten_question or query
    was_rewritten = bool(
        analysis.rewritten_question and analysis.rewritten_question != query
    )
    await progress.complete(
        "query_understanding",
        RETRIEVE_STEPS["query_understanding"]["title"],
        _format_understanding_summary(analysis, was_rewritten),
        metadata={
            "original_query": query,
            "rewritten_question": analysis.rewritten_question,
            "was_rewritten": was_rewritten,
            "question_type": (
                analysis.question_type.value if analysis.question_type else None
            ),
            "expanded_queries": analysis.expanded_queries,
            "target_hint": _serialize_target_hint(analysis),
        },
    )

    agent_overrides = _agent_override_filters(
        standard_family=standard_family,
        doc_type=doc_type,
        doc_version=doc_version,
    )
    filters, soft_boosts = build_filters_from_intent(
        getattr(analysis, "retrieval_intent", None),
        base_filters=analysis.filters,
        agent_overrides=agent_overrides,
    )
    if ctx.context.domain_filter:
        filters["source"] = ctx.context.domain_filter
        _relax_automatic_metadata_filters(
            filters,
            soft_boosts,
            protected_keys={
                key
                for key, value in agent_overrides.items()
                if value is not None
            },
        )
    if ctx.context.sources_filter is not None:
        filters["sources"] = ctx.context.sources_filter
        _relax_automatic_metadata_filters(
            filters,
            soft_boosts,
            protected_keys={
                key
                for key, value in agent_overrides.items()
                if value is not None
            },
        )
    await progress.start(
        "hybrid_search",
        RETRIEVE_STEPS["hybrid_search"]["title"],
        "正在执行向量检索、关键词检索与重排序",
    )
    result = await ctx.context.retriever.retrieve(
        analysis.expanded_queries,
        original_query=effective_original,
        filters=filters,
        intent_label=analysis.intent_label,
        question_type=analysis.question_type,
        guide_hint=analysis.guide_hint,
        target_hint=analysis.target_hint,
        requested_objects=analysis.requested_objects,
        preferred_element_type=analysis.preferred_element_type,
        soft_boosts=soft_boosts,
        top_k=effective_top_k,
        progress=progress,
    )
    await progress.complete(
        "hybrid_search",
        RETRIEVE_STEPS["hybrid_search"]["title"],
        f"找到 {len(result.chunks)} 个候选片段，groundedness={result.groundedness}",
        metadata={
            "chunk_count": len(result.chunks),
            "groundedness": result.groundedness,
            "ref_count": len(result.ref_chunks),
            "guide_count": len(result.guide_chunks) + len(result.guide_example_chunks),
        },
    )
    result = _limit_retrieval_result(result, effective_top_k)
    ctx.context.bundle.add_retrieval(result)
    ctx.context.bundle.tool_trace.append(
        {
            "tool": "retrieve",
            "query": query,
            "top_k": effective_top_k,
            "requested_top_k": top_k,
            "expanded_queries": analysis.expanded_queries,
            "rewritten_question": analysis.rewritten_question,
            "filters": filters,
            "soft_boosts": soft_boosts,
            "chunk_count": len(result.chunks),
            "groundedness": result.groundedness,
        }
    )
    return _format_retrieval_summary(result.groundedness, result.chunks)


def _agent_override_filters(
    *,
    standard_family: str | None,
    doc_type: str | None,
    doc_version: str | list[str] | None,
) -> dict[str, FilterValue | None]:
    return {
        "standard_family": standard_family,
        "doc_type": doc_type,
        "doc_version": doc_version,
    }


def _relax_automatic_metadata_filters(
    filters: dict[str, FilterValue],
    soft_boosts: dict[str, FilterValue],
    *,
    protected_keys: set[str],
) -> None:
    for key in ("standard_family", "doc_type", "doc_version"):
        if key in protected_keys:
            continue
        value = filters.pop(key, None)
        if value is not None:
            soft_boosts.setdefault(key, value)


def _clamp_top_k(top_k: int) -> int:
    try:
        value = int(top_k)
    except (TypeError, ValueError):
        value = _DEFAULT_TOP_K
    return min(max(value, _MIN_TOP_K), _MAX_TOP_K)


def _limit_retrieval_result(result: RetrievalResult, top_k: int) -> RetrievalResult:
    """Trim evidence attached to generation while preserving key supplements."""
    return RetrievalResult(
        chunks=result.chunks[:top_k],
        parent_chunks=result.parent_chunks[:top_k],
        scores=result.scores[:top_k],
        guide_chunks=result.guide_chunks[: max(1, top_k // 2)],
        guide_example_chunks=result.guide_example_chunks[: max(1, top_k // 3)],
        ref_chunks=result.ref_chunks[: max(2, top_k // 2)],
        groundedness=result.groundedness,
        resolved_refs=result.resolved_refs,
        unresolved_refs=result.unresolved_refs,
    )


def _format_retrieval_summary(groundedness: str, chunks: list) -> str:
    lines = [
        f"检索到 {len(chunks)} 个片段，groundedness={groundedness}。",
    ]
    if groundedness == "grounded":
        lines.append("证据已充足，请直接基于以上证据回复，无需再次检索。")
    if not chunks:
        return "\n".join(lines)

    lines.append("Top hits:")
    for index, chunk in enumerate(chunks[:3], start=1):
        metadata = chunk.metadata
        section = (
            " > ".join(metadata.section_path) if metadata.section_path else "unknown"
        )
        source = metadata.source or metadata.source_title or "unknown"
        content_preview = chunk.content[:80].replace("\n", " ").strip()
        lines.append(f"{index}. {source} | {section}")
        if content_preview:
            lines.append(f"   摘要: {content_preview}...")
    return "\n".join(lines)


def _format_understanding_summary(analysis, was_rewritten: bool) -> str:
    question_type = (
        analysis.question_type.value if analysis.question_type else "unknown"
    )
    summary = f"识别为{question_type}问题，扩展 {len(analysis.expanded_queries)} 条查询"
    if was_rewritten and analysis.rewritten_question:
        return f"改写为：{analysis.rewritten_question}；{summary}"
    return summary


def _serialize_target_hint(analysis) -> dict | None:
    target_hint = analysis.target_hint
    if target_hint is None:
        return None
    return {
        "document": target_hint.document,
        "clause": target_hint.clause,
        "object": target_hint.object,
    }
