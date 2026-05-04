"""Contextual retrieval helper objects."""
from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Literal

import structlog

from pipeline.structure import DocumentNode
from pipeline.structure import ElementType as StructElementType


logger = structlog.get_logger()


@dataclass(frozen=True)
class ContextualizeRequest:
    """Inputs required to contextualize one chunk."""

    doc_summary: str
    parent_section_text: str
    chunk_content: str
    chunk_kind: Literal["text", "table", "formula", "image"]
    section_path: list[str]
    chunk_alt: str = ""


@dataclass(frozen=True)
class ContextualizeResult:
    """LLM output for one contextualized chunk."""

    context_blurb: str
    semantic_description: str = ""


def build_outline_from_tree(tree: DocumentNode, *, first_para_max_chars: int = 200) -> str:
    """Build a deterministic outline from the document tree."""
    lines: list[str] = []
    token_estimate_chars = 0

    for node, depth in _walk_with_depth(tree):
        if node.element_type != StructElementType.SECTION:
            continue
        if node.title == "root":
            continue

        indent = "  " * depth
        lines.append(f"{indent}{node.title}")
        token_estimate_chars += len(indent) + len(node.title)

        first_para = _first_nonempty_paragraph(node.content)
        if first_para:
            truncated = first_para[:first_para_max_chars]
            suffix = "…" if len(first_para) >= first_para_max_chars else ""
            lines.append(f"{indent}  {truncated}{suffix}")
            token_estimate_chars += len(indent) + 2 + len(first_para)

    text = "\n".join(lines)
    if _estimate_tokens_from_chars(token_estimate_chars) > 50000:
        logger.warning("outline_fallback_titles_only", source=tree.source)
        return _build_titles_only_outline(tree)
    return text


def _walk_with_depth(tree: DocumentNode) -> Iterator[tuple[DocumentNode, int]]:
    stack: list[tuple[DocumentNode, int]] = [(tree, -1)]
    while stack:
        node, depth = stack.pop()
        if node.title != "root":
            yield node, max(depth, 0)
        for child in reversed(node.children):
            stack.append((child, depth + 1))


def _first_nonempty_paragraph(text: str) -> str:
    for paragraph in re.split(r"\n\s*\n", text):
        collapsed = " ".join(paragraph.split())
        if collapsed:
            return collapsed
    return ""


def _build_titles_only_outline(tree: DocumentNode) -> str:
    lines: list[str] = []
    for node, depth in _walk_with_depth(tree):
        if node.element_type != StructElementType.SECTION:
            continue
        if node.title == "root":
            continue
        lines.append(f"{'  ' * depth}{node.title}")
    return "\n".join(lines)


def _estimate_tokens_from_chars(char_count: int) -> int:
    """Rough token estimate: ~4 chars per token."""
    return char_count // 4 if char_count > 0 else 0
