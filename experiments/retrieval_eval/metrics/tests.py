"""Plain-assert smoke tests for retrieval evaluation metrics."""

from __future__ import annotations

from dataclasses import dataclass, field

from experiments.retrieval_eval.dataset.schema import ExpectedDoc
from experiments.retrieval_eval.metrics.bucketize import bucket_summary
from experiments.retrieval_eval.metrics.noise import (
    direct_ref_resolution_rate,
    noise_intrusion_rate,
)
from experiments.retrieval_eval.metrics.ranking import mrr_section, ndcg_at_k
from experiments.retrieval_eval.metrics.recall import (
    concept_recall_at_k,
    doc_recall_at_k,
    keyword_recall_at_k,
    section_recall_at_k,
)


@dataclass
class FakeMetadata:
    source: str
    section_path: list[str]
    clause_ids: list[str]
    source_title: str = ""
    display_title: str = ""
    object_label: str = ""
    object_id: str = ""
    object_aliases: list[str] = field(default_factory=list)
    ref_labels: list[str] = field(default_factory=list)


@dataclass
class FakeChunk:
    chunk_id: str
    content: str
    embedding_text: str
    metadata: FakeMetadata


@dataclass
class FakeResult:
    chunks: list[FakeChunk]
    ref_chunks: list[FakeChunk] = field(default_factory=list)
    resolved_refs: list[str] = field(default_factory=list)


def test_section_recall_at_k() -> None:
    chunks = [
        _chunk("c1", "EN 1992-1-1:2004", ["2.4.2.4"], ["2 Materials"]),
        _chunk("c2", "EN 1990:2002", ["6.4"], ["6.4 Ultimate limit states"]),
    ]
    expected = [
        ExpectedDoc("EN1992", ["2.4.2.4"]),
        ExpectedDoc("EN1990", ["6.4"]),
    ]
    assert section_recall_at_k(chunks, expected, 1) == 0.5
    assert section_recall_at_k(chunks, expected, 2) == 1.0


def test_doc_recall_at_k() -> None:
    chunks = [_chunk("c1", "EN 1992-1-1:2004", ["2.4"], ["2.4"])]
    expected = [ExpectedDoc("EN1992", ["2.4"]), ExpectedDoc("EN1990", ["6.4"])]
    assert doc_recall_at_k(chunks, expected, 10) == 0.5


def test_keyword_recall_at_k() -> None:
    chunks = [_chunk("c1", "EN1992", ["3.1.6"], ["3.1.6"], "design compressive strength fcd")]
    assert keyword_recall_at_k(chunks, ["fcd", "design compressive"], 1) == 1.0


def test_concept_recall_at_k_with_alias() -> None:
    chunks = [_chunk("c1", "EN1992", ["4.4.1"], ["4.4.1"], "minimum concrete cover cmin")]
    assert concept_recall_at_k(chunks, ["保护层"], 1) == 1.0


def test_mrr_section() -> None:
    chunks = [
        _chunk("c1", "EN1992", ["5.1"], ["5.1"]),
        _chunk("c2", "EN1992", ["6.2.2"], ["6.2 Shear"]),
    ]
    assert mrr_section(chunks, ["6.2.2"]) == 0.5


def test_ndcg_at_k() -> None:
    chunks = [
        _chunk("c1", "EN1992", ["5.1"], ["5.1"]),
        _chunk("c2", "EN1992", ["6.2.2"], ["6.2.2"]),
        _chunk("c3", "EN1992", ["6.2.3"], ["6.2.3"]),
    ]
    value = ndcg_at_k(chunks, ["6.2.2", "6.2.3"], 3)
    assert 0.0 < value < 1.0


def test_noise_intrusion_rate() -> None:
    chunks = [
        _chunk("c1", "EN1992", ["6.1"], ["6.1"], "plane sections remain plane"),
        _chunk("c2", "EN1992", ["5.8.9"], ["5.8.9"], "biaxial bending"),
    ]
    assert noise_intrusion_rate(chunks, ["biaxial bending"]) == 0.5


def test_direct_ref_resolution_rate() -> None:
    ref_chunk = _chunk(
        "t1",
        "EN1992",
        ["3.1"],
        ["3.1"],
        "table content",
        object_label="Table 3.1",
    )
    result = FakeResult(chunks=[], ref_chunks=[ref_chunk], resolved_refs=["Table 3.1"])
    assert direct_ref_resolution_rate(result, ["Table 3.1", "Figure 1.1"]) == 0.5


def test_bucket_summary() -> None:
    rows = [
        {
            "category": "broad",
            "review_bucket": "通过",
            "expected_documents": [{"doc": "EN1992"}],
            "metrics": {"section_recall@10": 1.0},
        },
        {
            "category": "broad",
            "review_bucket": "重大修改",
            "expected_documents": [{"doc": "EN1992"}, {"doc": "EN1990"}],
            "metrics": {"section_recall@10": 0.0},
        },
    ]
    summary = bucket_summary(rows)
    assert summary["category"]["broad"]["count"] == 2
    assert summary["doc_span"]["multi_doc"]["count"] == 1
    assert "重大修改" not in summary["included_review_bucket"]


def _chunk(
    chunk_id: str,
    source: str,
    clause_ids: list[str],
    section_path: list[str],
    text: str = "",
    *,
    object_label: str = "",
) -> FakeChunk:
    return FakeChunk(
        chunk_id=chunk_id,
        content=text,
        embedding_text=text,
        metadata=FakeMetadata(
            source=source,
            source_title=source,
            section_path=section_path,
            clause_ids=clause_ids,
            object_label=object_label,
            object_aliases=[object_label] if object_label else [],
        ),
    )


def run_all() -> None:
    tests = [
        test_section_recall_at_k,
        test_doc_recall_at_k,
        test_keyword_recall_at_k,
        test_concept_recall_at_k_with_alias,
        test_mrr_section,
        test_ndcg_at_k,
        test_noise_intrusion_rate,
        test_direct_ref_resolution_rate,
        test_bucket_summary,
    ]
    for test in tests:
        test()
    print(f"OK: {len(tests)} metric smoke tests passed.")


if __name__ == "__main__":
    run_all()
