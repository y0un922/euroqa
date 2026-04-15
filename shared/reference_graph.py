"""Helpers for deterministic internal reference extraction and object IDs."""
from __future__ import annotations

import re

_EN_REF_RE = re.compile(r"\bEN\s+\d{4}(?:-\d+(?:-\d+)?)?\b", re.IGNORECASE)
_ANNEX_REF_RE = re.compile(r"\bAnnex\s+[A-Z]\d*\b", re.IGNORECASE)
_TABLE_REF_RE = re.compile(r"\bTable\s+[A-Z]?\d+(?:\.\d+)*\b", re.IGNORECASE)
_FIGURE_REF_RE = re.compile(r"\bFigure\s+[A-Z]?\d+(?:\.\d+)*\b", re.IGNORECASE)
_EXPR_REF_RE = re.compile(r"\bExpression\s*\(\s*\d+(?:\.\d+)*\s*\)", re.IGNORECASE)
_CLAUSE_SIGNAL_RE = re.compile(
    r"\b(?:see|according\s+to|defined\s+in|given\s+in|follows\s+from|"
    r"described\s+in|specified\s+in|provided\s+in|relation\s+in)\s+"
    r"((?:[A-Z]?\d+(?:\.\d+)+)(?:\s*\(\d+\)\s*P?)?)",
    re.IGNORECASE,
)
_CLAUSE_KEY_RE = re.compile(r"[A-Z]?\d+(?:\.\d+)+", re.IGNORECASE)
_OBJECT_KEY_RE = re.compile(r"[A-Z]?\d+(?:\.\d+)*", re.IGNORECASE)


def extract_reference_labels(text: str) -> list[str]:
    """Extract normalized internal and external reference labels from text."""
    refs: list[str] = []
    seen: set[str] = set()

    def add(ref: str) -> None:
        normalized = normalize_reference_label(ref)
        if normalized and normalized not in seen:
            seen.add(normalized)
            refs.append(normalized)

    for pattern in (
        _EN_REF_RE,
        _ANNEX_REF_RE,
        _TABLE_REF_RE,
        _FIGURE_REF_RE,
        _EXPR_REF_RE,
    ):
        for match in pattern.finditer(text):
            add(match.group(0))

    for match in _CLAUSE_SIGNAL_RE.finditer(text):
        add(match.group(1))

    return refs


def normalize_reference_label(ref: str) -> str:
    """Normalize extracted reference labels to canonical display strings."""
    candidate = re.sub(r"\s+", " ", ref).strip()
    if not candidate:
        return ""

    lowered = candidate.lower()
    if lowered.startswith("table "):
        key = extract_object_key(candidate)
        return f"Table {key}" if key else candidate
    if lowered.startswith("figure "):
        key = extract_object_key(candidate)
        return f"Figure {key}" if key else candidate
    if lowered.startswith("expression"):
        key = extract_object_key(candidate)
        return f"Expression ({key})" if key else candidate
    if lowered.startswith("annex "):
        suffix = candidate.split(" ", 1)[1].strip()
        return f"Annex {suffix}"
    if _CLAUSE_KEY_RE.fullmatch(candidate):
        return candidate

    key = extract_clause_key(candidate)
    return key or candidate


def classify_reference_label(ref: str) -> str | None:
    """Classify a normalized reference label into an object type."""
    lowered = ref.lower()
    if lowered.startswith("table "):
        return "table"
    if lowered.startswith("figure "):
        return "figure"
    if lowered.startswith("expression"):
        return "expression"
    if lowered.startswith("annex "):
        return "annex"
    if _CLAUSE_KEY_RE.fullmatch(ref):
        return "clause"
    return None


def extract_clause_key(value: str) -> str:
    """Extract the stable clause key from a section title or reference label."""
    match = _CLAUSE_KEY_RE.search(value)
    return match.group(0) if match else ""


def extract_object_key(value: str) -> str:
    """Extract the stable numeric key used inside object IDs."""
    match = _OBJECT_KEY_RE.search(value)
    return match.group(0) if match else ""


def build_object_id(source: str, object_type: str, object_label: str) -> str:
    """Build a deterministic object identifier for one document-local object."""
    source_token = _slugify(source)
    object_key = ""

    if object_type == "clause":
        object_key = extract_clause_key(object_label)
    elif object_type in {"table", "figure", "expression"}:
        object_key = extract_object_key(object_label)
    elif object_type == "annex":
        suffix = object_label.split(" ", 1)[1].strip() if " " in object_label else object_label
        object_key = _slugify(suffix)

    object_key = object_key or _slugify(object_label)
    return f"{source_token}#{object_type}:{object_key}"


def _slugify(value: str) -> str:
    return re.sub(r"-{2,}", "-", re.sub(r"[^a-z0-9]+", "-", value.lower())).strip("-")
