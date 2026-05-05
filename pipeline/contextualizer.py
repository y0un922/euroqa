"""Contextual retrieval helper objects."""
from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Literal

import structlog
from openai import AsyncOpenAI

from pipeline.config import PipelineConfig
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


class Contextualizer:
    """Single OpenAI-compatible LLM contextualizer."""

    def __init__(self, config: PipelineConfig) -> None:
        self._client = AsyncOpenAI(
            base_url=config.contextualize_llm_base_url or config.llm_base_url,
            api_key=config.contextualize_llm_api_key or config.llm_api_key,
        )
        self._model = config.contextualize_llm_model or config.llm_model
        self._retry_attempts = max(1, config.contextualize_retry_attempts)

    async def generate_doc_summary(self, source_title: str, doc_outline_text: str) -> str:
        prompt = (
            f"Below is the outline and excerpts of a regulatory/standards document titled '{source_title}'.\n"
            "In 200-400 words, summarize its scope, structure, and key technical topics.\n"
            "This summary will be used as context to improve search retrieval of individual chunks.\n\n"
            f"Outline:\n{doc_outline_text}"
        )
        return await self._call_llm(prompt, max_tokens=800)

    async def contextualize_chunk(self, request: ContextualizeRequest) -> ContextualizeResult:
        if request.chunk_kind == "text":
            return await self._contextualize_text_chunk(request)
        if request.chunk_kind in {"table", "formula", "image"}:
            return await self._contextualize_special_chunk(request)
        raise ValueError(f"Unsupported chunk kind: {request.chunk_kind}")

    async def _contextualize_text_chunk(
        self, request: ContextualizeRequest
    ) -> ContextualizeResult:
        prompt = (
            f"Document summary: {request.doc_summary}\n\n"
            f"Section path: {' > '.join(request.section_path)}\n\n"
            f"Section containing the chunk:\n{request.parent_section_text}\n\n"
            f"Chunk to situate:\n{request.chunk_content}\n\n"
            "In 1-3 sentences, give a short context that situates this chunk within the document "
            "for retrieval purposes. Output only the context, no preamble."
        )
        context = await self._call_llm(prompt, max_tokens=300)
        return ContextualizeResult(context_blurb=context.strip(), semantic_description="")

    async def _contextualize_special_chunk(
        self, request: ContextualizeRequest
    ) -> ContextualizeResult:
        image_alt = ""
        if request.chunk_kind == "image" and request.chunk_alt:
            image_alt = f"\nImage alt text: {request.chunk_alt}"

        prompt = (
            f"Document summary: {request.doc_summary}\n"
            f"Section path: {' > '.join(request.section_path)}\n"
            f"Section containing the element:\n{request.parent_section_text}\n\n"
            f"The element ({request.chunk_kind}) to situate:\n{request.chunk_content}"
            f"{image_alt}\n\n"
            "Respond with a JSON object exactly matching this schema:\n"
            "{\n"
            '  "context": "1-2 sentence context situating this element within the document",\n'
            f'  "description": "natural-language description of what this {request.chunk_kind} expresses '
            '(factors, formula meaning, figure subject, etc.)"\n'
            "}\n"
            "Output only the JSON, no preamble."
        )
        raw = await self._call_llm(prompt, max_tokens=500)
        try:
            payload = json.loads(raw)
            return ContextualizeResult(
                context_blurb=str(payload.get("context", "")).strip(),
                semantic_description=str(payload.get("description", "")).strip(),
            )
        except json.JSONDecodeError:
            logger.warning(
                "contextualize_json_parse_failed",
                chunk_id="unknown",
                raw=raw[:200],
            )
            return ContextualizeResult(context_blurb=raw.strip(), semantic_description="")

    async def _call_llm(self, prompt: str, *, max_tokens: int) -> str:
        last_error: Exception | None = None
        for attempt in range(1, self._retry_attempts + 1):
            try:
                response = await self._client.chat.completions.create(
                    model=self._model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.1,
                    max_tokens=max_tokens,
                )
                content = response.choices[0].message.content
                return content.strip() if content else ""
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "contextualize_llm_attempt_failed",
                    attempt=attempt,
                    max_attempts=self._retry_attempts,
                    error=str(exc),
                )
                if attempt < self._retry_attempts:
                    # Exponential backoff per spec Section 5: 0.5s, 1s, 2s, …
                    await asyncio.sleep(0.5 * (2 ** (attempt - 1)))
        assert last_error is not None
        raise last_error
