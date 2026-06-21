from __future__ import annotations

from agents import RunContextWrapper, function_tool

from server.agents.deps import QADeps


@function_tool
async def lookup_clause(
    ctx: RunContextWrapper[QADeps],
    clause_ref: str,
) -> str:
    """按条款号精确查找规范条文，用于追踪已知交叉引用。"""
    return await _lookup_clause_impl(ctx, clause_ref)


async def _lookup_clause_impl(
    ctx: RunContextWrapper[QADeps],
    clause_ref: str,
) -> str:
    normalized = clause_ref.strip()
    if not normalized:
        return "未提供条款引用。"

    chunks = await ctx.context.retriever.lookup_clause(normalized)
    ctx.context.bundle.ref_chunks = _merge_chunks(ctx.context.bundle.ref_chunks, chunks)
    ctx.context.bundle.tool_trace.append(
        {
            "tool": "lookup_clause",
            "clause_ref": normalized,
            "chunk_count": len(chunks),
        }
    )
    if not chunks:
        return f"未精确找到条款引用：{normalized}"

    lines = [f"精确找到 {len(chunks)} 个条款片段："]
    for index, chunk in enumerate(chunks[:3], start=1):
        metadata = chunk.metadata
        source = metadata.source or metadata.source_title or "unknown"
        section = " > ".join(metadata.section_path) if metadata.section_path else "unknown"
        preview = chunk.content[:80].replace("\n", " ").strip()
        lines.append(f"{index}. {source} | {section}")
        if preview:
            lines.append(f"   摘要: {preview}...")
    return "\n".join(lines)


def _merge_chunks(existing, incoming):
    seen = {chunk.chunk_id for chunk in existing}
    merged = list(existing)
    for chunk in incoming:
        if chunk.chunk_id in seen:
            continue
        merged.append(chunk)
        seen.add(chunk.chunk_id)
    return merged
