"""Failure-mode rules for retrieval trace triage."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from experiments.retrieval_eval.dataset.schema import ExpectedDoc
from experiments.retrieval_eval.metrics.recall import (
    chunk_matches_doc,
    chunk_matches_expected_section,
    chunk_matches_section,
    normalize_for_text_match,
)

FAILURE_MODES = {
    "a_candidate_pool_missing": "候选池就没",
    "b_rrf_dropped": "RRF 丢",
    "c_cap_dropped": "Cap 砍",
    "d_rerank_dropped": "Rerank 误杀",
    "e_granularity_issue": "粒度问题",
}


@dataclass
class TriageFinding:
    """One failure-mode finding for a question."""

    code: str
    label: str
    detail: str

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "label": self.label, "detail": self.detail}


@dataclass
class _Meta:
    source: str = ""
    section_path: list[str] = field(default_factory=list)
    clause_ids: list[str] = field(default_factory=list)
    source_title: str = ""
    display_title: str = ""
    object_label: str = ""
    object_aliases: list[str] = field(default_factory=list)


@dataclass
class _TraceChunk:
    chunk_id: str
    content: str = ""
    embedding_text: str = ""
    metadata: _Meta = field(default_factory=_Meta)


def classify_failure_modes(row: dict[str, Any]) -> list[TriageFinding]:
    """Classify one per-question result into zero or more failure modes."""
    expected = _expected_docs(row.get("expected_documents") or [])
    if not expected:
        return []

    trace = row.get("trace") or {}
    dense_hits = _flatten_stage(trace.get("dense_hits") or [])
    bm25_hits = _flatten_stage(trace.get("bm25_hits") or [])
    candidate_hits = [*dense_hits, *bm25_hits]
    rrf_hits = _stage_chunks(trace.get("rrf_fused") or [])
    cap_hits = _stage_chunks(trace.get("after_cap") or [])
    reranked_hits = _stage_chunks(trace.get("reranked") or [])
    top_hits = _stage_chunks(row.get("retrieved_chunks") or [])

    findings: list[TriageFinding] = []

    candidate_has = _stage_has_expected(candidate_hits, expected)
    rrf_has = _stage_has_expected(rrf_hits, expected)
    cap_has = _stage_has_expected(cap_hits, expected)
    rerank_has = _stage_has_expected(reranked_hits, expected)

    if not candidate_has:
        findings.append(_finding("a_candidate_pool_missing", "dense ∪ BM25 无任何金标 doc+section 命中"))
    if candidate_has and not rrf_has:
        findings.append(_finding("b_rrf_dropped", "候选池有金标命中，但 RRF 后无命中"))
    if rrf_has and not cap_has:
        findings.append(_finding("c_cap_dropped", "RRF 有金标命中，但 per-source cap 后无命中"))
    if cap_has and not rerank_has:
        findings.append(_finding("d_rerank_dropped", "cap 后有金标命中，但 rerank top_n 后无命中"))
    if _has_granularity_issue(top_hits or reranked_hits, expected):
        findings.append(_finding("e_granularity_issue", "section_path 命中金标，但 clause_ids 未命中"))

    return findings


def _finding(code: str, detail: str) -> TriageFinding:
    return TriageFinding(code=code, label=FAILURE_MODES[code], detail=detail)


def _stage_has_expected(chunks: list[_TraceChunk], expected: list[ExpectedDoc]) -> bool:
    return any(chunk_matches_expected_section(chunk, expected) for chunk in chunks)


def _has_granularity_issue(chunks: list[_TraceChunk], expected: list[ExpectedDoc]) -> bool:
    for chunk in chunks:
        for doc in expected:
            if not chunk_matches_doc(chunk, doc.doc):
                continue
            for section in doc.sections:
                section_path_chunk = _TraceChunk(
                    chunk_id=chunk.chunk_id,
                    metadata=_Meta(
                        source=chunk.metadata.source,
                        section_path=chunk.metadata.section_path,
                        clause_ids=[],
                    ),
                )
                if chunk_matches_section(section_path_chunk, section) and not _clause_exact_matches(
                    chunk.metadata.clause_ids,
                    section,
                ):
                    return True
    return False


def _clause_exact_matches(clause_ids: list[str], section: str) -> bool:
    expected = _numeric_or_text_section(section)
    return any(_numeric_or_text_section(value) == expected for value in clause_ids)


def _numeric_or_text_section(value: str) -> str:
    import re

    text = str(value or "")
    match = re.search(r"\d+(?:\.\d+)*", text)
    if match:
        return match.group(0)
    return normalize_for_text_match(text)


def _flatten_stage(groups: list[Any]) -> list[_TraceChunk]:
    chunks: list[_TraceChunk] = []
    for group in groups:
        if isinstance(group, list):
            chunks.extend(_stage_chunks(group))
        else:
            chunks.extend(_stage_chunks([group]))
    return chunks


def _stage_chunks(items: list[Any]) -> list[_TraceChunk]:
    return [_trace_chunk(item) for item in items if isinstance(item, dict)]


def _trace_chunk(item: dict[str, Any]) -> _TraceChunk:
    return _TraceChunk(
        chunk_id=str(item.get("chunk_id") or ""),
        metadata=_Meta(
            source=str(item.get("source") or ""),
            source_title=str(item.get("source_title") or item.get("source") or ""),
            display_title=str(item.get("display_title") or ""),
            section_path=[str(value) for value in item.get("section_path") or []],
            clause_ids=[str(value) for value in item.get("clause_ids") or []],
            object_label=str(item.get("object_label") or ""),
            object_aliases=[str(value) for value in item.get("object_aliases") or []],
        ),
    )


def _expected_docs(items: list[Any]) -> list[ExpectedDoc]:
    docs: list[ExpectedDoc] = []
    for item in items:
        if isinstance(item, ExpectedDoc):
            docs.append(item)
        elif isinstance(item, dict):
            docs.append(
                ExpectedDoc(
                    doc=str(item.get("doc") or ""),
                    sections=[str(value) for value in item.get("sections") or []],
                    objects=[str(value) for value in item.get("objects") or []],
                )
            )
    return docs
