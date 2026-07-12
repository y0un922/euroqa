"""Deterministic query text helpers for Agentic RAG retrieval."""

from __future__ import annotations

import re

from shared.reference_graph import classify_reference_label, normalize_reference_label
from server.models.schemas import RoutingTargetHint

_INJECTION_PATTERNS = [
    re.compile(r"忽略.{0,10}(之前|以上|前面).{0,10}(指令|规则|提示)", re.IGNORECASE),
    re.compile(
        r"ignore.{0,20}(previous|above|prior).{0,20}(instructions?|rules?|prompts?)",
        re.IGNORECASE,
    ),
    re.compile(r"disregard.{0,20}(previous|above|prior)", re.IGNORECASE),
    re.compile(r"你(现在)?是.{0,10}(一个|一名)", re.IGNORECASE),
    re.compile(r"pretend.{0,10}(you are|to be)", re.IGNORECASE),
]
_DG_SOURCE_RE = re.compile(r"DG\s*EN\s*(\d{4}(?:-\d+-\d+|-\d+)?)", re.IGNORECASE)
_SOURCE_RE = re.compile(r"EN\s*(\d{4}(?:-\d+-\d+|-\d+)?)", re.IGNORECASE)
_TABLE_RE = re.compile(r"表格?|table", re.IGNORECASE)
_FORMULA_RE = re.compile(r"公式|formula|eq", re.IGNORECASE)
_REQUESTED_TABLE_RE = re.compile(
    r"(?:\btable\b|表格?|表)\s*([A-Z]?\d+(?:\.\d+)*(?:[A-Z])?(?:\([A-Z0-9]+\))?)",
    re.IGNORECASE,
)
_REQUESTED_FIGURE_RE = re.compile(
    r"(?:\bfigure\b|图)\s*([A-Z]?\d+(?:\.\d+)*(?:[A-Z])?(?:\([A-Z0-9]+\))?)",
    re.IGNORECASE,
)
_REQUESTED_EXPR_RE = re.compile(
    r"(?:\bexpression\b|公式|式)\s*[\(\[]?\s*(\d+(?:\.\d+)*)\s*[\)\]]?",
    re.IGNORECASE,
)
_REQUESTED_ANNEX_RE = re.compile(r"(?:\bannex\b|附录)\s*([A-Z]\d*)", re.IGNORECASE)
_REQUESTED_CLAUSE_RE = re.compile(
    r"(?<![A-Za-z0-9/])([A-Z]?\d+(?:\.\d+)+[A-Z]?)(?![A-Za-z0-9/])",
    re.IGNORECASE,
)


def sanitize_input(question: str) -> str:
    """Filter common prompt-injection phrases while preserving the question."""
    cleaned = question
    for pattern in _INJECTION_PATTERNS:
        cleaned = pattern.sub("", cleaned).strip()
    return cleaned


def extract_filters(question: str) -> dict[str, str]:
    """Extract query-local source filters from explicit EN/DG mentions."""
    filters: dict[str, str] = {}
    dg_source_match = _DG_SOURCE_RE.search(question)
    if dg_source_match:
        filters["source"] = f"DG EN{dg_source_match.group(1)}"
        return filters
    source_match = _SOURCE_RE.search(question)
    if source_match:
        filters["source"] = f"EN {source_match.group(1)}"
    return filters


def extract_preferred_element_type(question: str) -> str | None:
    """Extract a soft element preference for callers that still need it."""
    if _TABLE_RE.search(question):
        return "table"
    if _FORMULA_RE.search(question):
        return "formula"
    return None


def extract_requested_objects(
    question: str,
    target_hint: RoutingTargetHint | dict[str, str] | None = None,
) -> list[str]:
    """Extract explicit Table/Figure/Expression/Annex/Clause references."""
    requested: list[str] = []
    seen: set[str] = set()
    candidates: list[tuple[int, str]] = []
    occupied_spans: list[tuple[int, int]] = []

    def add_candidate(value: str) -> None:
        normalized = normalize_reference_label(value)
        if not normalized:
            return
        category = classify_reference_label(normalized)
        if category != "clause" and category is None:
            return
        if normalized not in seen:
            seen.add(normalized)
            requested.append(normalized)

    def add_pattern(pattern: re.Pattern[str], builder) -> None:
        for match in pattern.finditer(question):
            occupied_spans.append(match.span())
            candidates.append((match.start(), builder(match.group(1))))

    add_pattern(_REQUESTED_TABLE_RE, lambda key: f"Table {key}")
    add_pattern(_REQUESTED_FIGURE_RE, lambda key: f"Figure {key}")
    add_pattern(_REQUESTED_EXPR_RE, lambda key: f"Expression ({key})")
    add_pattern(_REQUESTED_ANNEX_RE, lambda key: f"Annex {key}")

    for match in _REQUESTED_CLAUSE_RE.finditer(question):
        if _overlaps(match.span(), occupied_spans):
            continue
        candidates.append((match.start(), match.group(1)))

    for _, value in sorted(candidates, key=lambda item: item[0]):
        add_candidate(value)

    target_object = _target_hint_object(target_hint)
    if target_object:
        for label in re.split(r"[,;，；、]|\band\b", target_object):
            add_candidate(label.strip())

    return requested


def _target_hint_object(
    target_hint: RoutingTargetHint | dict[str, str] | None,
) -> str:
    if target_hint is None:
        return ""
    if isinstance(target_hint, dict):
        return str(target_hint.get("object") or "")
    return str(target_hint.object or "")


def _overlaps(span: tuple[int, int], occupied: list[tuple[int, int]]) -> bool:
    return any(not (span[1] <= left or span[0] >= right) for left, right in occupied)
