from __future__ import annotations

from agents import RunContextWrapper, function_tool

from server.agents.deps import QADeps


@function_tool
async def lookup_glossary(ctx: RunContextWrapper[QADeps], term: str) -> str:
    """查询欧洲规范术语表。传入中文或英文术语，返回对应的翻译和定义。"""
    normalized = term.strip()
    if not normalized:
        return "未提供术语。"

    matches = _find_matches(normalized, ctx.context.glossary)
    if not matches:
        ctx.context.bundle.tool_trace.append(
            {"tool": "lookup_glossary", "term": normalized, "hit_count": 0}
        )
        return f"术语表中未找到：{normalized}"

    for key, definition in matches:
        ctx.context.bundle.add_glossary_hit(key, definition)
    ctx.context.bundle.tool_trace.append(
        {
            "tool": "lookup_glossary",
            "term": normalized,
            "hit_count": len(matches),
        }
    )
    return "\n".join(f"{key}: {definition}" for key, definition in matches)


def _find_matches(term: str, glossary: dict[str, str]) -> list[tuple[str, str]]:
    if term in glossary:
        return [(term, glossary[term])]

    lowered = term.lower()
    matches: list[tuple[str, str]] = []
    for key, definition in glossary.items():
        key_lowered = key.lower()
        if lowered in key_lowered or key_lowered in lowered:
            matches.append((key, definition))
    return matches
