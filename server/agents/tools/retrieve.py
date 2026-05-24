from __future__ import annotations

from agents import RunContextWrapper, function_tool

from server.agents.deps import QADeps
from server.core.query_understanding import analyze_query


@function_tool
async def retrieve(ctx: RunContextWrapper[QADeps], query: str) -> str:
    """搜索欧洲规范知识库。传入中文或英文检索查询，返回匹配的规范片段摘要。"""
    return await _retrieve_impl(ctx, query)


async def _retrieve_impl(ctx: RunContextWrapper[QADeps], query: str) -> str:
    analysis = await analyze_query(query, ctx.context.glossary, ctx.context.config)
    filters = dict(analysis.filters)
    if ctx.context.domain_filter:
        filters["source"] = ctx.context.domain_filter
    result = await ctx.context.retriever.retrieve(
        analysis.expanded_queries,
        original_query=query,
        filters=filters,
        intent_label=analysis.intent_label,
        question_type=analysis.question_type,
        guide_hint=analysis.guide_hint,
        target_hint=analysis.target_hint,
        requested_objects=analysis.requested_objects,
        preferred_element_type=analysis.preferred_element_type,
    )
    ctx.context.bundle.add_retrieval(result)
    ctx.context.bundle.tool_trace.append(
        {
            "tool": "retrieve",
            "query": query,
            "expanded_queries": analysis.expanded_queries,
            "chunk_count": len(result.chunks),
            "groundedness": result.groundedness,
        }
    )
    return _format_retrieval_summary(result.groundedness, result.chunks)


def _format_retrieval_summary(groundedness: str, chunks: list) -> str:
    lines = [
        f"检索到 {len(chunks)} 个片段，groundedness={groundedness}。",
    ]
    if not chunks:
        return lines[0]

    lines.append("Top hits:")
    for index, chunk in enumerate(chunks[:3], start=1):
        metadata = chunk.metadata
        section = (
            " > ".join(metadata.section_path) if metadata.section_path else "unknown"
        )
        source = metadata.source or metadata.source_title or "unknown"
        lines.append(f"{index}. {source} | {section}")
    return "\n".join(lines)
