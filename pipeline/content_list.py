"""Helpers for consuming MinerU content_list output."""
from __future__ import annotations

import re
from dataclasses import dataclass, field


_NORMALIZE_TEXT_RE = re.compile(r"[^a-z0-9]+")
_PAGE_ONLY_TYPES = {"header", "footer", "page_number", "aside_text", "page_footnote"}


@dataclass(frozen=True)
class ContentListEntry:
    """Flattened MinerU content_list entry used for section-page matching."""

    index: int
    page_idx: int
    text: str
    text_level: int
    bbox: list[float] = field(default_factory=list)
    element_type: str = ""


def _validate_bbox(raw_bbox: object) -> list[float]:
    """Validate and return bbox, or empty list if invalid.

    Accepts a list of exactly 4 numeric values in the 0-1000 range
    (MinerU normalises coordinates to this range).
    """
    if not isinstance(raw_bbox, list) or len(raw_bbox) != 4:
        return []
    values: list[float] = []
    for v in raw_bbox:
        if not isinstance(v, (int, float)):
            return []
        if v < 0 or v > 1000:
            return []
        values.append(float(v))
    return values


def content_list_output_name(stem: str) -> str:
    """Return the normalized content_list filename stored beside parsed markdown."""

    return f"{stem}_content_list.json"


def resolve_section_page_metadata(
    segments: list[tuple[int, str, str]],
    content_list: object,
) -> list[tuple[list[int], list[int], list[float], int]]:
    """Resolve page metadata for markdown sections from MinerU content_list.

    Returns a list of 4-tuples:
        (page_numbers, page_file_indexes, bbox, bbox_page_idx)

    page_numbers:      1-based page numbers covered by the section
    page_file_indexes: 0-based page indexes covered by the section
    bbox:              bounding box of the matched heading entry (may be [])
    bbox_page_idx:     page_idx of the matched heading entry (-1 if unmatched)
    """

    normalized_list = _normalize_content_list(content_list)
    if not segments:
        return []
    if not normalized_list:
        return [([], [], [], -1) for _ in segments]

    heading_indexes = _match_heading_indexes(segments, normalized_list)
    resolved: list[tuple[list[int], list[int], list[float], int]] = []
    for index, (level, _, _) in enumerate(segments):
        start = heading_indexes[index]
        if start is None:
            resolved.append(([], [], [], -1))
            continue

        end = len(normalized_list)
        for next_index in range(index + 1, len(segments)):
            next_start = heading_indexes[next_index]
            next_level = segments[next_index][0]
            if next_start is not None and next_level <= level:
                end = next_start
                break

        page_file_indexes = _collect_page_indexes(normalized_list[start:end])

        # 优先使用第一个 body text entry 的 bbox（实际内容位置），
        # 而非 heading entry 的 bbox（仅标题位置）。
        heading_entry = normalized_list[start]
        body_entry = _find_first_body_entry(normalized_list[start + 1 : end])
        target_entry = body_entry if body_entry else heading_entry

        resolved.append((
            [page + 1 for page in page_file_indexes],
            page_file_indexes,
            list(target_entry.bbox),
            target_entry.page_idx,
        ))
    return resolved


def _normalize_content_list(content_list: object) -> list[ContentListEntry]:
    """Flatten content_list JSON into a text-bearing sequence."""

    if isinstance(content_list, dict):
        content_list = content_list.get("items", [])
    if not isinstance(content_list, list):
        return []

    entries: list[ContentListEntry] = []
    for index, item in enumerate(content_list):
        if not isinstance(item, dict):
            continue
        page_idx = item.get("page_idx")
        if not isinstance(page_idx, int):
            continue
        text = _extract_entry_text(item)
        if not text:
            continue
        text_level = item.get("text_level", 0)
        if not isinstance(text_level, int):
            text_level = 0
        entries.append(
            ContentListEntry(
                index=index,
                page_idx=page_idx,
                text=text,
                text_level=text_level,
                bbox=_validate_bbox(item.get("bbox")),
                element_type=str(item.get("type", "")),
            )
        )
    return entries


def _extract_entry_text(item: dict) -> str:
    """Extract readable text from one content_list item."""

    item_type = item.get("type")
    if not isinstance(item_type, str) or item_type in _PAGE_ONLY_TYPES:
        return ""

    text_parts: list[str] = []
    direct_text = item.get("text")
    if isinstance(direct_text, str) and direct_text.strip():
        text_parts.append(direct_text.strip())

    for key in (
        "image_caption",
        "image_footnote",
        "table_caption",
        "table_footnote",
        "code_caption",
        "list_items",
    ):
        value = item.get(key)
        if isinstance(value, list):
            text_parts.extend(
                part.strip() for part in value if isinstance(part, str) and part.strip()
            )

    code_body = item.get("code_body")
    if isinstance(code_body, str) and code_body.strip():
        text_parts.append(code_body.strip())

    return "\n".join(text_parts).strip()


def _match_heading_indexes(
    segments: list[tuple[int, str, str]],
    entries: list[ContentListEntry],
) -> list[int | None]:
    """Match markdown headings to content_list heading entries in order."""

    matches: list[int | None] = []
    cursor = 0
    for level, title, _ in segments:
        match_index: int | None = None
        for entry_index in range(cursor, len(entries)):
            entry = entries[entry_index]
            if entry.text_level <= 0:
                continue
            if entry.text_level != level:
                continue
            if _texts_match(title, entry.text):
                match_index = entry_index
                cursor = entry_index + 1
                break
        matches.append(match_index)
    return matches


def _texts_match(left: str, right: str) -> bool:
    """Return whether two content blocks likely describe the same heading."""

    normalized_left = _normalize_text(left)
    normalized_right = _normalize_text(right)
    if not normalized_left or not normalized_right:
        return False
    return (
        normalized_left == normalized_right
        or normalized_left in normalized_right
        or normalized_right in normalized_left
    )


def _normalize_text(value: str) -> str:
    """Normalize heading text for resilient matching."""

    return _NORMALIZE_TEXT_RE.sub("", value.casefold())


def _find_first_body_entry(
    entries: list[ContentListEntry],
) -> ContentListEntry | None:
    """Return the first body text entry with a valid bbox, or None."""
    for entry in entries:
        if entry.text_level == 0 and entry.bbox:
            return entry
    return None


def _collect_page_indexes(entries: list[ContentListEntry]) -> list[int]:
    """Collect unique page indexes while preserving order."""

    seen: set[int] = set()
    page_indexes: list[int] = []
    for entry in entries:
        if entry.page_idx in seen:
            continue
        seen.add(entry.page_idx)
        page_indexes.append(entry.page_idx)
    return page_indexes
