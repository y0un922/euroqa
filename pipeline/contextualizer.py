"""Contextual retrieval helper objects."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


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
