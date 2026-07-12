from __future__ import annotations

from agents import RunContextWrapper, function_tool

from server.agents.deps import QADeps
from server.agents.tools._utils import (
    base_filters,
    clamp_top_k,
    limit_retrieval_result,
)
from server.core.retrieval import RetrievalResult
from server.models.schemas import Chunk


@function_tool
async def search(
    ctx: RunContextWrapper[QADeps],
    query: str,
    top_k: int = 8,
) -> str:
    """搜索 Eurocode 语料库。返回带编号的证据片段。"""
    effective_top_k = clamp_top_k(top_k)
    result = await ctx.context.retriever.retrieve(
        [query],
        original_query=query,
        filters=base_filters(ctx),
        top_k=effective_top_k,
    )
    limited = limit_retrieval_result(result, effective_top_k)
    ctx.context.bundle.add_retrieval(limited, query=query)
    ctx.context.bundle.tool_trace.append(
        {
            "tool": "search",
            "query": query,
            "top_k": effective_top_k,
            "chunk_count": len(limited.chunks),
            "groundedness": limited.groundedness,
        }
    )
    return _format_evidence_list("补充检索结果", ctx.context.bundle, limited.chunks)


@function_tool
async def lookup_object(
    ctx: RunContextWrapper[QADeps],
    label: str,
    top_k: int = 3,
) -> str:
    """按 Table/Figure/Expression/Annex/Clause 标签精确查找规范对象。"""
    lookup = getattr(ctx.context.retriever, "lookup_object", None)
    if lookup is None:
        return "当前检索器不支持 lookup_object。"
    effective_top_k = clamp_top_k(top_k, default=3)
    chunks = await lookup(label, filters=base_filters(ctx), top_k=effective_top_k)
    if chunks:
        result = RetrievalResult(
            chunks=chunks,
            parent_chunks=[],
            scores=[1.0] * len(chunks),
            groundedness="partial",
            resolved_refs=[label],
        )
        ctx.context.bundle.add_retrieval(result, query=label)
    ctx.context.bundle.tool_trace.append(
        {
            "tool": "lookup_object",
            "label": label,
            "top_k": effective_top_k,
            "chunk_count": len(chunks),
        }
    )
    return _format_evidence_list("对象查找结果", ctx.context.bundle, chunks)


def _format_evidence_list(title: str, bundle, chunks: list[Chunk]) -> str:
    if not chunks:
        return f"{title}: 未找到匹配片段。"
    lines = [f"{title}: {len(chunks)} 个片段"]
    for chunk in chunks[:8]:
        ref = bundle.ref_label_for(chunk)
        meta = chunk.metadata
        section = " > ".join(meta.section_path) if meta.section_path else "unknown"
        page = ", ".join(map(str, meta.page_numbers)) if meta.page_numbers else "unknown"
        label = f" | {meta.object_label}" if meta.object_label else ""
        preview = chunk.content[:360].replace("\n", " ").strip()
        lines.append(f"[{ref}] {meta.source} | {section} | p.{page}{label}")
        if preview:
            lines.append(preview)
    return "\n".join(lines)
