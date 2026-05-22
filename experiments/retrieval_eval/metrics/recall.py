"""Recall metrics for retrieval-only evaluation."""

from __future__ import annotations

import re
import unicodedata
from typing import Any

from experiments.retrieval_eval.dataset.schema import ExpectedDoc

_DOC_ALIASES = {
    "EN1990": {"EN1990", "EN 1990"},
    "EN1992": {"EN1992", "EN 1992", "EN1992-1-1", "EN 1992-1-1"},
    "EN206": {"EN206", "EN 206", "EN206-1", "EN 206-1"},
    "DG_EN1992": {"DG_EN1992", "DG EN1992", "DESIGNERS GUIDE EN1992"},
}

_TEXT_ALIASES = {
    "分项系数": ["partial factor", "partial safety factor", "gamma"],
    "材料分项系数": ["partial factor for materials", "gamma c", "gamma s"],
    "承载能力极限状态": ["ultimate limit state", "uls"],
    "正常使用极限状态": ["serviceability limit state", "sls"],
    "混凝土保护层": ["concrete cover", "cover"],
    "保护层": ["concrete cover", "cover"],
    "裂缝宽度": ["crack width", "wmax"],
    "抗剪": ["shear", "vrd"],
    "抗压强度": ["compressive strength", "fck", "fcd"],
    "设计值": ["design value", "design strength"],
    "特征值": ["characteristic value"],
    "组合值": ["combination value"],
    "频遇值": ["frequent value"],
    "准永久值": ["quasi-permanent value", "quasi permanent value"],
}


def section_recall_at_k(
    retrieved_chunks: list[Any], expected: list[ExpectedDoc], k: int
) -> float:
    """Return fraction of expected sections found in top-k chunks."""
    expected_pairs = _expected_section_pairs(expected)
    if not expected_pairs:
        return 1.0

    hits: set[tuple[str, str]] = set()
    for chunk in _top_k(retrieved_chunks, k):
        for doc_key, section in expected_pairs:
            if _chunk_matches_doc(chunk, doc_key) and _chunk_matches_section(chunk, section):
                hits.add((doc_key, section))
    return len(hits) / len(expected_pairs)


def doc_recall_at_k(
    retrieved_chunks: list[Any], expected: list[ExpectedDoc], k: int
) -> float:
    """Return fraction of expected documents represented in top-k chunks."""
    expected_docs = {_normalize_doc(doc.doc) for doc in expected if doc.doc}
    if not expected_docs:
        return 1.0

    hit_docs: set[str] = set()
    for chunk in _top_k(retrieved_chunks, k):
        for doc_key in expected_docs:
            if _chunk_matches_doc(chunk, doc_key):
                hit_docs.add(doc_key)
    return len(hit_docs) / len(expected_docs)


def keyword_recall_at_k(
    retrieved_chunks: list[Any], expected_keywords: list[str], k: int
) -> float:
    """Return fraction of expected keyword strings found in top-k chunk text."""
    return _text_recall_at_k(retrieved_chunks, expected_keywords, k)


def concept_recall_at_k(
    retrieved_chunks: list[Any], expected_concepts: list[str], k: int
) -> float:
    """Return fraction of expected concept strings found in top-k chunk text."""
    return _text_recall_at_k(retrieved_chunks, expected_concepts, k)


def chunk_matches_expected_section(chunk: Any, expected: list[ExpectedDoc]) -> bool:
    """Return whether one chunk matches any expected document-section pair."""
    for doc_key, section in _expected_section_pairs(expected):
        if _chunk_matches_doc(chunk, doc_key) and _chunk_matches_section(chunk, section):
            return True
    return False


def chunk_matches_section(chunk: Any, section: str) -> bool:
    """Return whether one chunk matches a section regardless of document."""
    return _chunk_matches_section(chunk, section)


def chunk_matches_doc(chunk: Any, doc: str) -> bool:
    """Return whether one chunk source matches a gold document id."""
    return _chunk_matches_doc(chunk, _normalize_doc(doc))


def normalize_for_text_match(text: str) -> str:
    """Normalize text for conservative substring matching."""
    normalized = unicodedata.normalize("NFKC", str(text or "")).lower()
    normalized = normalized.replace("γ", "gamma")
    normalized = normalized.replace("_", " ")
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", " ", normalized).strip()


def normalize_doc_id(doc: str) -> str:
    """Public wrapper for document id normalization."""
    return _normalize_doc(doc)


def _expected_section_pairs(expected: list[ExpectedDoc]) -> set[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()
    for doc in expected:
        doc_key = _normalize_doc(doc.doc)
        for section in doc.sections:
            normalized = _normalize_section(section)
            if doc_key and normalized:
                pairs.add((doc_key, normalized))
    return pairs


def _text_recall_at_k(retrieved_chunks: list[Any], expected_terms: list[str], k: int) -> float:
    terms = [term for term in expected_terms if str(term or "").strip()]
    if not terms:
        return 1.0

    haystack = normalize_for_text_match(
        " ".join(_chunk_text(chunk) for chunk in _top_k(retrieved_chunks, k))
    )
    compact_haystack = haystack.replace(" ", "")

    hits = 0
    for term in terms:
        candidates = _term_candidates(term)
        if any(
            candidate in haystack or candidate.replace(" ", "") in compact_haystack
            for candidate in candidates
            if candidate
        ):
            hits += 1
    return hits / len(terms)


def _term_candidates(term: str) -> list[str]:
    normalized = normalize_for_text_match(term)
    candidates = [normalized]
    candidates.extend(normalize_for_text_match(alias) for alias in _TEXT_ALIASES.get(term, []))
    candidates.extend(_formula_variants(normalized))
    return list(dict.fromkeys(c for c in candidates if c))


def _formula_variants(term: str) -> list[str]:
    variants = {term}
    compact = term.replace(" ", "")
    if compact:
        variants.add(compact)
    if "gamma" in term:
        variants.add(term.replace("gamma", "γ"))
    return list(variants)


def _chunk_text(chunk: Any) -> str:
    content = getattr(chunk, "content", "") or ""
    embedding_text = getattr(chunk, "embedding_text", "") or ""
    meta = getattr(chunk, "metadata", None)
    object_label = getattr(meta, "object_label", "") if meta is not None else ""
    object_aliases = getattr(meta, "object_aliases", []) if meta is not None else []
    return " ".join([content, embedding_text, object_label, " ".join(object_aliases or [])])


def _chunk_matches_doc(chunk: Any, expected_doc_key: str) -> bool:
    meta = getattr(chunk, "metadata", None)
    source = getattr(meta, "source", "") if meta is not None else ""
    title = getattr(meta, "source_title", "") if meta is not None else ""
    display_title = getattr(meta, "display_title", "") if meta is not None else ""
    doc_keys = {_normalize_doc(value) for value in (source, title, display_title) if value}
    return expected_doc_key in doc_keys


def _chunk_matches_section(chunk: Any, expected_section: str) -> bool:
    expected = _normalize_section(expected_section)
    if not expected:
        return False

    meta = getattr(chunk, "metadata", None)
    clause_ids = getattr(meta, "clause_ids", []) if meta is not None else []
    section_path = getattr(meta, "section_path", []) if meta is not None else []
    object_label = getattr(meta, "object_label", "") if meta is not None else ""
    object_aliases = getattr(meta, "object_aliases", []) if meta is not None else []

    for value in list(clause_ids or []) + list(section_path or []):
        if _section_value_matches(value, expected):
            return True

    if expected.startswith(("table ", "annex ", "figure ", "eq ", "equation ")):
        object_values = [object_label, *list(object_aliases or [])]
        return any(normalize_for_text_match(expected) in normalize_for_text_match(v) for v in object_values)

    return False


def _section_value_matches(value: str, expected: str) -> bool:
    normalized_value = _normalize_section(value)
    if not normalized_value:
        return False
    if expected == normalized_value:
        return True
    if normalized_value.startswith(f"{expected}.") or normalized_value.startswith(f"{expected} "):
        return True
    return expected in normalized_value


def _normalize_doc(doc: str) -> str:
    text = _compact_doc(doc)
    text = re.sub(r"[:：]\s*\d{4}.*$", "", text)
    if text.startswith("DGEN1992"):
        return "DG_EN1992"
    if text.startswith("DESIGNERSGUIDEEN1992"):
        return "DG_EN1992"
    if text.startswith("EN1992"):
        return "EN1992"
    if text.startswith("EN1990"):
        return "EN1990"
    if text.startswith("EN206"):
        return "EN206"
    for canonical, aliases in _DOC_ALIASES.items():
        if text in {_compact_doc(alias) for alias in aliases}:
            return canonical
    return text


def _compact_doc(doc: str) -> str:
    text = unicodedata.normalize("NFKC", str(doc or "")).upper()
    text = re.sub(r"[:：]\s*\d{4}.*$", "", text)
    text = re.sub(r"\bEUROCODE\b", "EN", text)
    return re.sub(r"[^A-Z0-9]+", "", text)


def _normalize_section(section: str) -> str:
    text = unicodedata.normalize("NFKC", str(section or "")).strip()
    text = text.replace("§", "").replace("clause", "").replace("Clause", "")
    text = re.sub(r"\((?:\d+|[A-Z])\)P?$", "", text).strip()
    text = re.sub(r"\s+", " ", text)
    lower = text.lower()
    if lower.startswith(("table ", "annex ", "figure ", "eq ", "equation ")):
        return normalize_for_text_match(text)
    match = re.search(r"\d+(?:\.\d+)*", text)
    return match.group(0) if match else normalize_for_text_match(text)


def _top_k(items: list[Any], k: int) -> list[Any]:
    if k <= 0:
        return []
    return items[:k]
