"""Stage 3.5 contextual retrieval enrichment."""
from __future__ import annotations

import asyncio
import re
from collections import defaultdict
from collections.abc import Awaitable, Callable

import structlog

from pipeline.config import PipelineConfig
from pipeline.contextualizer import (
    ContextualizeRequest,
    ContextualizeResult,
    Contextualizer,
    build_outline_from_tree,
)
from pipeline.structure import DocumentNode
from server.models.schemas import Chunk, ElementType

logger = structlog.get_logger()


async def enrich_chunks(
    chunks: list[Chunk],
    config: PipelineConfig | None = None,
    *,
    tree: DocumentNode | None = None,
    progress_callback: Callable[[dict], Awaitable[None] | None] | None = None,
) -> list[Chunk]:
    """Contextualize all chunks and write into embedding_text."""
    if not chunks:
        return chunks

    cfg = config or PipelineConfig()
    contextualizer = Contextualizer(cfg)
    chunks_by_source: dict[str, list[Chunk]] = defaultdict(list)
    for chunk in chunks:
        chunks_by_source[chunk.metadata.source].append(chunk)

    for source, source_chunks in chunks_by_source.items():
        source_title = source_chunks[0].metadata.source_title or source
        outline_text = build_outline_from_tree(tree) if tree is not None else _build_outline_from_chunks(source_chunks)
        doc_summary = await contextualizer.generate_doc_summary(
            source_title=source_title,
            doc_outline_text=outline_text,
        )
        await _contextualize_source_chunks(
            source_chunks,
            contextualizer,
            cfg,
            doc_summary,
            progress_callback,
        )

    return chunks


async def _contextualize_source_chunks(
    chunks: list[Chunk],
    contextualizer: Contextualizer,
    config: PipelineConfig,
    doc_summary: str,
    progress_callback: Callable[[dict], Awaitable[None] | None] | None,
) -> None:
    semaphore = asyncio.Semaphore(max(1, config.contextualize_concurrency))
    chunk_lookup = {chunk.chunk_id: chunk for chunk in chunks}
    total = len(chunks)
    completed = 0

    async def _one(chunk: Chunk) -> ContextualizeResult:
        async with semaphore:
            request = _build_request(chunk, chunk_lookup, doc_summary)
            return await contextualizer.contextualize_chunk(request)

    results = await asyncio.gather(*(_one(chunk) for chunk in chunks), return_exceptions=True)

    for chunk, result in zip(chunks, results):
        completed += 1
        if isinstance(result, Exception):
            logger.warning(
                "contextualize_failed",
                chunk_id=chunk.chunk_id,
                element_type=chunk.metadata.element_type.value,
                section_path=chunk.metadata.section_path,
                exc=str(result),
            )
        else:
            chunk.embedding_text = build_embedding_text(chunk, result)

        if progress_callback is not None:
            payload = {
                "completed": completed,
                "total": total,
                "chunk_id": chunk.chunk_id,
                "element_type": chunk.metadata.element_type.value,
                "section_path": chunk.metadata.section_path,
            }
            callback_result = progress_callback(payload)
            if isinstance(callback_result, Awaitable):
                await callback_result


def build_embedding_text(chunk: Chunk, result: ContextualizeResult) -> str:
    """Build the final embedding_text string."""
    if chunk.metadata.element_type == ElementType.TEXT:
        return f"[CTX] {result.context_blurb}\n\n{chunk.content}"
    return f"[CTX] {result.context_blurb}\n\n[DESC] {result.semantic_description}"


def _build_request(
    chunk: Chunk,
    chunk_lookup: dict[str, Chunk],
    doc_summary: str,
) -> ContextualizeRequest:
    return ContextualizeRequest(
        doc_summary=doc_summary,
        parent_section_text=_resolve_parent_section_text(chunk, chunk_lookup),
        chunk_content=chunk.content,
        chunk_kind=chunk.metadata.element_type.value,
        section_path=chunk.metadata.section_path,
        chunk_alt=_extract_alt_if_image(chunk),
    )


def _resolve_parent_section_text(chunk: Chunk, chunk_lookup: dict[str, Chunk]) -> str:
    if chunk.metadata.element_type == ElementType.TEXT:
        parent_id = chunk.metadata.parent_chunk_id
        if parent_id and parent_id in chunk_lookup:
            return chunk_lookup[parent_id].content
        return chunk.content

    parent_text_chunk_id = chunk.metadata.parent_text_chunk_id
    if parent_text_chunk_id and parent_text_chunk_id in chunk_lookup:
        return chunk_lookup[parent_text_chunk_id].content
    return chunk.content


def _extract_alt_if_image(chunk: Chunk) -> str:
    if chunk.metadata.element_type != ElementType.IMAGE:
        return ""
    match = re.search(r"!\[([^\]]*)\]\([^)]+\)", chunk.content)
    if match:
        return match.group(1).strip()
    return chunk.metadata.object_label


def _build_outline_from_chunks(chunks: list[Chunk]) -> str:
    seen: set[tuple[str, ...]] = set()
    lines: list[str] = []
    for chunk in chunks:
        path = tuple(chunk.metadata.section_path)
        if not path or path in seen:
            continue
        seen.add(path)
        depth = max(0, len(path) - 1)
        lines.append(f"{'  ' * depth}{path[-1]}")
    return "\n".join(lines)
