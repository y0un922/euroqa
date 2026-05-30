from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import structlog

from server.config import ServerConfig
from server.models.schemas import Chunk, ElementType, Source

logger = structlog.get_logger()


def _build_sources_from_chunks(
    chunks: list[Chunk],
    config: ServerConfig | None = None,
    prioritized_chunks: list[Chunk] | None = None,
) -> list[Source]:
    """从检索结果的 metadata 直接构建 Source，不依赖 LLM JSON 解析。"""
    sources: list[Source] = []
    cfg = config or ServerConfig()
    ordered_chunks: list[Chunk] = []
    seen_ids: set[str] = set()
    for chunk in prioritized_chunks or []:
        if chunk.chunk_id not in seen_ids:
            seen_ids.add(chunk.chunk_id)
            ordered_chunks.append(chunk)
    for chunk in chunks:
        if chunk.chunk_id not in seen_ids:
            seen_ids.add(chunk.chunk_id)
            ordered_chunks.append(chunk)

    for chunk in ordered_chunks:
        meta = chunk.metadata
        document_id = _resolve_document_id(chunk)
        display_title = _resolve_chunk_display_title(chunk, cfg, document_id)
        # Primary: use bbox from pipeline metadata
        bbox = list(meta.bbox) if meta.bbox else []
        resolved_page = str(meta.bbox_page_idx + 1) if meta.bbox_page_idx >= 0 else ""

        # Fallback for table: runtime content_list traversal (legacy data without pipeline bbox)
        if not bbox and meta.element_type == ElementType.TABLE:
            bbox, resolved_page = _resolve_table_source_geometry(
                chunk,
                document_id,
                cfg,
            )

        sources.append(
            Source(
                file=meta.source,
                document_id=document_id,
                display_title=display_title,
                element_type=meta.element_type,
                bbox=bbox,
                title=display_title,
                section=" > ".join(meta.section_path),
                page=resolved_page
                or (
                    str(meta.page_file_index[0] + 1)
                    if meta.page_file_index
                    else str(meta.page_numbers[0])
                    if meta.page_numbers
                    else ""
                ),
                clause=", ".join(meta.clause_ids[:2]) if meta.clause_ids else "",
                original_text=chunk.content,
                locator_text=_build_locator_text(chunk.content),
                highlight_text=_build_highlight_text(
                    chunk.content,
                    meta.page_numbers,
                ),
                translation="",
            )
        )
    return sources


def _build_prioritized_source_chunks(
    chunks: list[Chunk],
    parent_chunks: list[Chunk],
    ref_chunks: list[Chunk] | None = None,
    guide_chunks: list[Chunk] | None = None,
    guide_example_chunks: list[Chunk] | None = None,
    generation_mode: str | None = None,
    question: str = "",
    intent_label: str | None = None,
) -> list[Chunk]:
    """Build source ordering for prompt and source metadata."""
    del generation_mode, question, intent_label
    seen_ids: set[str] = set()
    ordered: list[Chunk] = []
    for chunk in (
        list(chunks)
        + list(parent_chunks)
        + list(ref_chunks or [])
        + list(guide_chunks or [])
        + list(guide_example_chunks or [])
    ):
        if chunk.chunk_id not in seen_ids:
            seen_ids.add(chunk.chunk_id)
            ordered.append(chunk)
    return ordered


def _normalize_sources(sources: list[Source]) -> list[Source]:
    """Backfill source fields using backend normalization rules."""
    normalized_sources: list[Source] = []
    for source in sources:
        document_id = _resolve_document_id(source)
        display_title = (
            source.display_title.strip()
            or source.title.strip()
            or source.file.strip()
            or document_id
        )
        highlight_text = source.highlight_text.strip() or _build_highlight_text(
            source.original_text,
            [int(source.page)] if str(source.page).strip().isdigit() else [],
        )
        locator_text = source.locator_text.strip() or _build_locator_text(
            highlight_text or source.original_text
        )
        normalized_sources.append(
            source.model_copy(
                update={
                    "document_id": document_id,
                    "display_title": display_title,
                    "highlight_text": highlight_text,
                    "locator_text": locator_text,
                    "translation": "",
                    "title": display_title,
                }
            )
        )
    return normalized_sources


def _parse_source_payload(payload: object) -> Source | None:
    """Parse a single source payload leniently and keep partial data when possible."""
    if not isinstance(payload, dict):
        return None

    return Source(
        file=str(payload.get("file", "")),
        document_id=str(payload.get("document_id", "")),
        display_title=str(payload.get("display_title", "")),
        element_type=payload.get("element_type", ElementType.TEXT),
        bbox=payload.get("bbox", []),
        title=str(payload.get("title", "")),
        section=str(payload.get("section", "")),
        page=payload.get("page", ""),
        clause=str(payload.get("clause", "")),
        original_text=str(payload.get("original_text", "")),
        locator_text=str(payload.get("locator_text", "")),
        highlight_text=str(payload.get("highlight_text", "")),
        translation=str(payload.get("translation", "")),
    )


def _collect_pending_source_indexes(sources: list[Source]) -> list[int]:
    """收集仍需补齐翻译的 source 下标。"""
    return [
        index
        for index, source in enumerate(sources)
        if not source.translation.strip() and source.original_text.strip()
    ]


def _build_document_id(source: str) -> str:
    """Build a stable document identifier from source metadata."""
    normalized = re.sub(r"(?<=[A-Za-z])\s+(?=\d)", "", source.strip())
    normalized = re.sub(r"[^A-Za-z0-9_\-]+", "_", normalized)
    return normalized.strip("_")


def _resolve_document_id(chunk: Chunk | Source) -> str:
    """Resolve the backend document id used by document file endpoints."""
    if isinstance(chunk, Source):
        document_id = chunk.document_id.strip()
        file_name = chunk.file.strip()
        if document_id:
            return document_id
        if file_name.lower().endswith(".pdf"):
            return file_name
        return _build_document_id(file_name)

    meta = chunk.metadata
    document_id = (meta.document_id or "").strip()
    if document_id:
        return document_id
    source = meta.source.strip()
    if source.lower().endswith(".pdf"):
        return source
    return _build_document_id(meta.source)


def _load_parse_option_file_name(parsed_dir: str, document_id: str) -> str:
    """Load the client-provided filename from per-document parse options."""
    base_dir = Path(parsed_dir)
    for options_name in ("parse_options.json", "option.json"):
        options_path = base_dir / document_id / options_name
        if not options_path.is_file():
            continue
        try:
            payload = json.loads(options_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            logger.warning(
                "parse_options_display_title_load_failed",
                path=str(options_path),
            )
            continue
        if not isinstance(payload, dict):
            continue
        for key in ("file_name", "filename", "fileName"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return ""


def _resolve_chunk_display_title(
    chunk: Chunk,
    config: ServerConfig | None = None,
    document_id: str | None = None,
) -> str:
    """Resolve the readable document title while preserving source identity."""
    meta = chunk.metadata
    resolved_document_id = document_id or _resolve_document_id(chunk)
    if config is not None:
        parse_file_name = _load_parse_option_file_name(
            str(Path(config.parsed_dir)),
            resolved_document_id,
        )
        if parse_file_name:
            return parse_file_name
    source_title = meta.source_title.strip()
    source_title_suffix = Path(source_title).suffix.lower()
    return (
        meta.display_title.strip()
        or (source_title if source_title_suffix == ".pdf" else "")
        or meta.source.strip()
        or resolved_document_id
    )


def _build_locator_text(content: str, max_length: int = 240) -> str:
    """Build a shorter normalized text snippet suitable for PDF search."""
    normalized = re.sub(r"\[\->\s*[^\]]*\]", " ", content)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    if not normalized:
        normalized = re.sub(r"\s+", " ", content).strip()
    if len(normalized) <= max_length:
        return normalized

    truncated = normalized[:max_length].rsplit(" ", 1)[0].strip()
    return truncated or normalized[:max_length].strip()


def _build_highlight_text(content: str, page_numbers: list[int]) -> str:
    """Build the full text used for PDF paragraph highlighting.

    Keep the full chunk semantics intact and let the frontend derive the best
    page-local overlap against the rendered PDF text layer. Only retrieval
    markers and simple HTML table wrappers are stripped out here.
    """
    del page_numbers

    normalized = re.sub(r"\[\->\s*[^\]]*\]", "", content)
    normalized = re.sub(
        r"</?(?:table|thead|tbody|tr|td|th|br)\b[^>]*>", " ", normalized
    )
    # 剥离 LaTeX 公式（$...$, $$...$$）
    normalized = re.sub(r"\$\$.*?\$\$", " ", normalized, flags=re.DOTALL)
    normalized = re.sub(r"\$[^$\n]+?\$", " ", normalized)
    # 剥离 Markdown 强调标记（**...**、*...*、__...__、_..._）
    normalized = re.sub(r"\*{1,2}([^*\n]+?)\*{1,2}", r"\1", normalized)
    normalized = re.sub(r"_{1,2}([^_\n]+?)_{1,2}", r"\1", normalized)
    if normalized == content:
        return content.strip()
    normalized = re.sub(r"[ \t]+", " ", normalized)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized).strip()
    if normalized:
        return normalized
    return content.strip()


def _normalize_table_html(content: str) -> str:
    """Normalize HTML table strings for robust matching."""
    return re.sub(r"\s+", "", content).casefold()


def _extract_table_caption(content: str) -> str:
    """Extract the caption line when a table chunk starts with one."""
    for line in content.splitlines():
        candidate = line.strip()
        if re.match(r"^Table\s+[A-Z]?\d+(?:\.\d+)*\b", candidate):
            return candidate
        if candidate:
            break
    return ""


def _extract_table_html(content: str) -> str:
    """Extract the HTML table fragment from a chunk when present."""
    match = re.search(r"<table\b[^>]*>.*?</table>", content, re.DOTALL)
    return match.group(0).strip() if match else ""


def _load_content_list_payload(content_list_path: str) -> list[dict[str, Any]]:
    """Load a parsed MinerU content_list file from disk."""
    path = Path(content_list_path)
    if not path.is_file():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.warning(
            "content_list_load_failed", path=content_list_path, exc_info=True
        )
        return []
    return payload if isinstance(payload, list) else []


def _resolve_content_list_path(config: ServerConfig, document_id: str) -> Path:
    """Resolve the MinerU content_list path for a document."""
    return Path(config.parsed_dir) / document_id / f"{document_id}_content_list.json"


def _extract_content_list_caption(entry: dict[str, Any]) -> str:
    """Normalize content_list table captions into a single string."""
    caption = entry.get("table_caption", [])
    if isinstance(caption, list):
        return " ".join(
            str(part).strip() for part in caption if str(part).strip()
        ).strip()
    if isinstance(caption, str):
        return caption.strip()
    return ""


def _resolve_table_source_geometry(
    chunk: Chunk,
    document_id: str,
    config: ServerConfig,
) -> tuple[list[float], str]:
    """Resolve bbox and page for a table chunk from MinerU content_list."""
    content_list_path = _resolve_content_list_path(config, document_id)
    entries = _load_content_list_payload(str(content_list_path))
    if not entries:
        return [], ""

    chunk_caption = _extract_table_caption(chunk.content)
    chunk_table_html = _extract_table_html(chunk.content)
    normalized_chunk_html = (
        _normalize_table_html(chunk_table_html) if chunk_table_html else ""
    )
    candidate_page_indexes = set(chunk.metadata.page_file_index)

    best_bbox: list[float] = []
    best_page = ""
    best_score = -1

    for entry in entries:
        if entry.get("type") != "table":
            continue
        bbox = entry.get("bbox")
        if (
            not isinstance(bbox, list)
            or len(bbox) != 4
            or not all(isinstance(value, (int, float)) for value in bbox)
        ):
            continue

        score = 0
        page_idx = entry.get("page_idx")
        if isinstance(page_idx, int) and page_idx in candidate_page_indexes:
            score += 4

        entry_caption = _extract_content_list_caption(entry)
        if chunk_caption and entry_caption and entry_caption == chunk_caption:
            score += 8
        elif chunk_caption and entry_caption and entry_caption in chunk.content:
            score += 4

        entry_table_html = str(entry.get("table_body", "")).strip()
        if normalized_chunk_html and entry_table_html:
            normalized_entry_html = _normalize_table_html(entry_table_html)
            if normalized_entry_html == normalized_chunk_html:
                score += 10
            elif (
                normalized_entry_html
                and normalized_entry_html in _normalize_table_html(chunk.content)
            ):
                score += 5

        if score <= best_score:
            continue

        best_score = score
        best_bbox = [float(value) for value in bbox]
        best_page = str(page_idx + 1) if isinstance(page_idx, int) else ""

    if best_score < 5:
        return [], ""
    return best_bbox, best_page
