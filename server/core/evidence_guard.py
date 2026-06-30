"""Evidence requirement matching for retrieval quality checks."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from server.models.schemas import Chunk


@dataclass
class EvidenceMatcher:
    """Structured predicate for one acceptable evidence shape.

    The matcher is intentionally generic: it only checks chunk metadata/content
    fields and does not know Eurocode business semantics.
    """

    source_contains: list[str] = field(default_factory=list)
    document_id_contains: list[str] = field(default_factory=list)
    source_title_contains: list[str] = field(default_factory=list)
    display_title_contains: list[str] = field(default_factory=list)
    section_path_contains: list[str] = field(default_factory=list)
    object_label_contains: list[str] = field(default_factory=list)
    object_id_contains: list[str] = field(default_factory=list)
    clause_ids_overlap: list[str] = field(default_factory=list)
    object_aliases_overlap: list[str] = field(default_factory=list)
    ref_labels_overlap: list[str] = field(default_factory=list)
    element_type_in: list[str] = field(default_factory=list)
    object_type_in: list[str] = field(default_factory=list)
    content_contains: list[str] = field(default_factory=list)


@dataclass
class EvidenceRequirement:
    """A named evidence requirement with OR semantics across matchers."""

    id: str
    label: str
    any_of: list[EvidenceMatcher] = field(default_factory=list)
    required: bool = True


@dataclass
class EvidenceGuardResult:
    """Result of matching evidence chunks against declared requirements."""

    passed: bool
    missing_required: list[EvidenceRequirement]
    matched_chunk_ids_by_requirement: dict[str, list[str]]
    retry_note: str | None = None

    def to_trace(self) -> dict[str, object]:
        """Return a JSON-native diagnostic payload."""
        return {
            "passed": self.passed,
            "missing_required": [
                _requirement_summary(requirement)
                for requirement in self.missing_required
            ],
            "matched_chunk_ids_by_requirement": (
                self.matched_chunk_ids_by_requirement
            ),
            "retry_note": self.retry_note,
        }


def evaluate_evidence_requirements(
    chunks: list[Chunk],
    requirements: list[EvidenceRequirement],
) -> EvidenceGuardResult:
    """Match chunks against requirements without blocking generation."""
    matched_by_requirement: dict[str, list[str]] = {}
    missing_required: list[EvidenceRequirement] = []

    unique_chunks = _dedupe_chunks(chunks)
    for requirement in requirements:
        matched_ids = [
            chunk.chunk_id
            for chunk in unique_chunks
            if _matches_requirement(requirement, chunk)
        ]
        matched_by_requirement[requirement.id] = matched_ids
        if requirement.required and not matched_ids:
            missing_required.append(requirement)

    retry_note = _build_retry_note(missing_required)
    return EvidenceGuardResult(
        passed=not missing_required,
        missing_required=missing_required,
        matched_chunk_ids_by_requirement=matched_by_requirement,
        retry_note=retry_note,
    )


def requirements_to_trace(
    requirements: list[EvidenceRequirement],
) -> list[dict[str, object]]:
    """Return JSON-native requirement diagnostics."""
    return [_requirement_to_trace(requirement) for requirement in requirements]


def chunk_matches_requirement(chunk: Chunk, requirement: EvidenceRequirement) -> bool:
    """Return whether a chunk satisfies one structured requirement."""
    return _matches_requirement(requirement, chunk)


def _matches_requirement(requirement: EvidenceRequirement, chunk: Chunk) -> bool:
    if not requirement.any_of:
        return False
    return any(_matches_matcher(matcher, chunk) for matcher in requirement.any_of)


def _matches_matcher(matcher: EvidenceMatcher, chunk: Chunk) -> bool:
    meta = chunk.metadata
    if matcher.source_contains and not _any_contains(
        _join_values(
            meta.source,
            meta.document_id,
            meta.source_title,
            meta.display_title,
        ),
        matcher.source_contains,
    ):
        return False
    if matcher.document_id_contains and not _any_contains(
        meta.document_id or "",
        matcher.document_id_contains,
    ):
        return False
    if matcher.source_title_contains and not _any_contains(
        meta.source_title,
        matcher.source_title_contains,
    ):
        return False
    if matcher.display_title_contains and not _any_contains(
        meta.display_title,
        matcher.display_title_contains,
    ):
        return False
    if matcher.section_path_contains and not _any_contains(
        _join_values(*meta.section_path),
        matcher.section_path_contains,
    ):
        return False
    if matcher.object_label_contains and not _any_contains(
        meta.object_label,
        matcher.object_label_contains,
    ):
        return False
    if matcher.object_id_contains and not _any_contains(
        meta.object_id,
        matcher.object_id_contains,
    ):
        return False
    if matcher.clause_ids_overlap and not _has_clause_overlap(
        meta.clause_ids,
        matcher.clause_ids_overlap,
    ):
        return False
    if matcher.object_aliases_overlap and not _has_overlap(
        meta.object_aliases,
        matcher.object_aliases_overlap,
    ):
        return False
    if matcher.ref_labels_overlap and not _has_overlap(
        meta.ref_labels,
        matcher.ref_labels_overlap,
    ):
        return False
    if matcher.element_type_in and meta.element_type.value.lower() not in {
        value.lower() for value in matcher.element_type_in
    }:
        return False
    if matcher.object_type_in and (meta.object_type or "").lower() not in {
        value.lower() for value in matcher.object_type_in
    }:
        return False
    if matcher.content_contains and not _all_contains(
        chunk.content,
        matcher.content_contains,
    ):
        return False
    return True


def _build_retry_note(
    missing_required: list[EvidenceRequirement],
) -> str | None:
    if not missing_required:
        return None
    labels = "、".join(requirement.label for requirement in missing_required)
    return (
        f"当前检索证据缺少必要依据：{labels}。回答时请优先检查现有片段是否已经"
        "支撑这些内容；如果没有，必须明确说明缺口，不要编造数值、公式或条款。"
    )


def _requirement_to_trace(requirement: EvidenceRequirement) -> dict[str, object]:
    return {
        **_requirement_summary(requirement),
        "any_of": [_matcher_to_trace(matcher) for matcher in requirement.any_of],
    }


def _requirement_summary(requirement: EvidenceRequirement) -> dict[str, object]:
    return {
        "id": requirement.id,
        "label": requirement.label,
        "required": requirement.required,
    }


def _matcher_to_trace(matcher: EvidenceMatcher) -> dict[str, object]:
    payload: dict[str, object] = {}
    for key, value in matcher.__dict__.items():
        if value:
            payload[key] = list(value)
    return payload


def _dedupe_chunks(chunks: list[Chunk]) -> list[Chunk]:
    seen: set[str] = set()
    unique: list[Chunk] = []
    for chunk in chunks:
        if chunk.chunk_id in seen:
            continue
        unique.append(chunk)
        seen.add(chunk.chunk_id)
    return unique


def _join_values(*values: object) -> str:
    return "\n".join(str(value) for value in values if value)


def _any_contains(haystack: str, needles: list[str]) -> bool:
    return any(_contains(haystack, needle) for needle in needles)


def _all_contains(haystack: str, needles: list[str]) -> bool:
    return all(_contains(haystack, needle) for needle in needles)


def _contains(haystack: str, needle: str) -> bool:
    if not needle:
        return True
    haystacks = _contains_variants(haystack)
    needles = _contains_variants(needle)
    return any(
        needle_item in haystack_item
        or _compact(needle_item) in _compact(haystack_item)
        for haystack_item in haystacks
        for needle_item in needles
    )


def _has_overlap(values: list[str], expected: list[str]) -> bool:
    return any(_contains(value, item) for value in values for item in expected)


def _has_clause_overlap(values: list[str], expected: list[str]) -> bool:
    normalized_values = [_normalize_clause(value) for value in values if value]
    normalized_expected = [_normalize_clause(value) for value in expected if value]
    for actual in normalized_values:
        for wanted in normalized_expected:
            if actual == wanted:
                return True
            if actual.startswith(f"{wanted}.") or wanted.startswith(f"{actual}."):
                return True
    return False


def _normalize_clause(value: str) -> str:
    return value.strip().lower().replace(" ", "")


def _compact(value: str) -> str:
    return re.sub(r"[\s_\-:/]+", "", value)


def _contains_variants(value: str) -> set[str]:
    lowered = value.lower()
    return {lowered, re.sub(r"(?<=\d),(?=\d)", ".", lowered)}
