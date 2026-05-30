"""Pure retrieval helper functions for targets, objects, and source filters."""

from __future__ import annotations

import re
from typing import Any

from server.models.schemas import Chunk
from shared.reference_graph import build_object_id, classify_reference_label

_SOURCE_DOC_RE = re.compile(
    r"(?<![A-Za-z0-9])en\s*([0-9]{4}(?:-[0-9]+(?:-[0-9]+)?)?)"
    r"(?:[\s:_-]*([0-9]{4}))?(?![A-Za-z0-9])",
    re.IGNORECASE,
)


def _normalize_target_hint(target_hint: Any) -> dict[str, str]:
    """将 target_hint 归一化为纯字符串字典。"""
    if target_hint is None:
        return {}

    if isinstance(target_hint, dict):
        raw_items = target_hint.items()
    else:
        raw_items = (
            (key, getattr(target_hint, key, None))
            for key in ("document", "clause", "object")
        )

    normalized: dict[str, str] = {}
    for key, value in raw_items:
        if isinstance(value, str):
            stripped = value.strip()
            if stripped:
                normalized[key] = stripped
    return normalized


def _object_reference_key(object_id: str) -> str:
    return object_id.split("#", 1)[-1].strip().lower() if object_id else ""


def _collect_object_ids(chunks: list[Chunk]) -> set[str]:
    return {
        chunk.metadata.object_id
        for chunk in chunks
        if chunk.metadata.object_id
    }


def _collect_ref_object_ids(chunks: list[Chunk]) -> set[str]:
    object_ids: set[str] = set()
    for chunk in chunks:
        object_ids.update(
            object_id
            for object_id in chunk.metadata.ref_object_ids
            if object_id
        )
    return object_ids


def _collect_object_keys(chunks: list[Chunk]) -> set[str]:
    return {
        _object_reference_key(chunk.metadata.object_id)
        for chunk in chunks
        if chunk.metadata.object_id
    }


def _build_object_id_label_map(
    chunks: list[Chunk],
    requested_objects: list[str],
    lookup_source: str,
) -> dict[str, str]:
    labels_by_id: dict[str, str] = {}

    for chunk in chunks:
        if chunk.metadata.object_id and chunk.metadata.object_label:
            labels_by_id.setdefault(chunk.metadata.object_id, chunk.metadata.object_label)

    for chunk in chunks:
        for label, object_id in zip(
            chunk.metadata.ref_labels,
            chunk.metadata.ref_object_ids,
            strict=False,
        ):
            if object_id and label and object_id not in labels_by_id:
                labels_by_id[object_id] = label

    for label in requested_objects:
        ref_type = classify_reference_label(label)
        if ref_type is None or not lookup_source:
            continue
        object_id = build_object_id(lookup_source, ref_type, label)
        labels_by_id.setdefault(object_id, label)

    return labels_by_id


def _should_require_reference_closure(object_key: str, requested_object_keys: set[str]) -> bool:
    if object_key in requested_object_keys:
        return True
    return object_key.startswith(("table:", "expression:", "annex:"))


def _should_promote_exact_ref_chunk(
    chunk: Chunk,
    required_object_keys: set[str],
    requested_object_keys: set[str],
) -> bool:
    object_key = _object_reference_key(chunk.metadata.object_id)
    if not object_key or object_key not in required_object_keys:
        return False
    if object_key in requested_object_keys:
        return True
    return (chunk.metadata.object_type or "").lower() in {"table", "expression", "annex"}


def _promote_exact_ref_chunks(
    chunks: list[Chunk],
    scores: list[float],
    ref_chunks: list[Chunk],
    required_object_keys: set[str],
    requested_object_keys: set[str],
) -> tuple[list[Chunk], list[float], list[Chunk]]:
    if not chunks or not ref_chunks:
        return chunks, scores, ref_chunks

    seen_ids = {chunk.chunk_id for chunk in chunks}
    promoted: list[Chunk] = []
    remaining: list[Chunk] = []
    for chunk in ref_chunks:
        if chunk.chunk_id in seen_ids:
            continue
        if _should_promote_exact_ref_chunk(
            chunk,
            required_object_keys,
            requested_object_keys,
        ):
            seen_ids.add(chunk.chunk_id)
            promoted.append(chunk)
        else:
            remaining.append(chunk)

    if not promoted:
        return chunks, scores, ref_chunks

    insert_at = 1 if (chunks[0].metadata.object_type or "").lower() == "clause" else 0
    base_score = scores[0] if scores else 0.0
    promoted_scores = [max(base_score - (index + 1) * 0.001, 0.0) for index, _ in enumerate(promoted)]
    merged_chunks = chunks[:insert_at] + promoted + chunks[insert_at:]
    merged_scores = scores[:insert_at] + promoted_scores + scores[insert_at:]
    return merged_chunks, merged_scores, remaining


def _prune_shadowed_requested_object_ids(object_ids: set[str]) -> set[str]:
    explicit_object_keys = {
        object_key.split(":", 1)[1]
        for object_id in object_ids
        if (object_key := _object_reference_key(object_id))
        and not object_key.startswith("clause:")
        and ":" in object_key
    }
    return {
        object_id
        for object_id in object_ids
        if not (
            (object_key := _object_reference_key(object_id)).startswith("clause:")
            and object_key.split(":", 1)[1] in explicit_object_keys
        )
    }


def _display_label_for_object_id(object_id: str) -> str:
    suffix = object_id.split("#", 1)[-1]
    if ":" not in suffix:
        return object_id
    object_type, key = suffix.split(":", 1)
    if object_type == "table":
        return f"Table {key}"
    if object_type == "figure":
        return f"Figure {key}"
    if object_type == "expression":
        return f"Expression ({key})"
    if object_type == "annex":
        return f"Annex {key.upper()}"
    if object_type == "clause":
        return key
    return object_id


def _parse_source_reference(value: str) -> tuple[str, str]:
    match = _SOURCE_DOC_RE.search(value or "")
    if not match:
        return "", ""
    return match.group(1), match.group(2) or ""


def _source_aliases(value: str) -> list[str]:
    candidate = (value or "").strip()
    if not candidate:
        return []

    aliases: list[str] = [candidate]
    code, year = _parse_source_reference(candidate)
    if not code:
        return aliases

    base_forms = [f"EN {code}", f"EN{code}"]
    if year:
        for base in base_forms:
            aliases.extend(
                [
                    f"{base}:{year}",
                    f"{base} {year}",
                    f"{base}_{year}",
                ]
            )
    else:
        aliases.extend(base_forms)

    deduped: list[str] = []
    seen: set[str] = set()
    for alias in aliases:
        normalized = alias.strip()
        if normalized and normalized not in seen:
            seen.add(normalized)
            deduped.append(normalized)
    return deduped


def _build_source_filter_clauses(filters: dict | None) -> list[dict]:
    filters = filters or {}
    filter_clauses: list[dict] = []

    if "source" in filters:
        aliases = _source_aliases(filters["source"])
        code, year = _parse_source_reference(filters["source"])
        should_clauses = [{"term": {"source": alias}} for alias in aliases]
        if code and not year:
            should_clauses.append({"wildcard": {"source": f"*{code}*"}})
        filter_clauses.append(
            {
                "bool": {
                    "should": should_clauses,
                    "minimum_should_match": 1,
                }
            }
        )

    if "sources" in filters:
        filter_clauses.append({"terms": {"source": filters["sources"]}})

    return filter_clauses


def _build_milvus_source_expr(source: str) -> str | None:
    aliases = _source_aliases(source)
    code, year = _parse_source_reference(source)
    if not aliases:
        return None
    if not code:
        return f'source == "{source}"'
    if not year:
        return None
    if len(aliases) == 1:
        return f'source == "{aliases[0]}"'
    quoted = ", ".join(f'"{alias}"' for alias in aliases)
    return f"source in [{quoted}]"


def _source_matches_filter(source: str, expected: str) -> bool:
    """Return whether an indexed source satisfies a user-facing source filter."""

    normalized_source = source.strip()
    aliases = _source_aliases(expected)
    code, year = _parse_source_reference(expected)
    if normalized_source in aliases:
        return True
    if code and not year:
        source_code, _ = _parse_source_reference(normalized_source)
        return source_code == code or source_code.startswith(f"{code}-")
    return False


def _filter_results_by_source(
    results: list[dict],
    filters: dict | None,
) -> list[dict]:
    """Apply source filters to result rows that were not filtered by backend expr."""

    filters = filters or {}
    if "source" in filters:
        return [
            result
            for result in results
            if _source_matches_filter(str(result.get("source") or ""), filters["source"])
        ]
    if "sources" in filters:
        allowed = set(filters["sources"])
        return [
            result
            for result in results
            if result.get("source") in allowed
        ]
    return results


def _lookup_aliases_for_object_id(object_id: str) -> tuple[str, list[str]]:
    suffix = object_id.split("#", 1)[-1]
    if ":" not in suffix:
        return "", []
    object_type, key = suffix.split(":", 1)
    if object_type == "table":
        return object_type, [f"Table {key}"]
    if object_type == "figure":
        return object_type, [f"Figure {key}"]
    if object_type == "expression":
        return object_type, [f"Expression ({key})"]
    if object_type == "annex":
        return object_type, [f"Annex {key.upper()}"]
    if object_type == "clause":
        return object_type, [key, f"Clause {key}", f"Section {key}"]
    return object_type, []
