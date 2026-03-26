"""Test hybrid retrieval layer (mock external services)."""
import pytest

from server.core.retrieval import HybridRetriever
from server.models.schemas import IntentType


@pytest.fixture
def retriever():
    r = HybridRetriever.__new__(HybridRetriever)
    return r


class TestMergeAndDedup:
    def test_dedup_by_chunk_id(self, retriever):
        vec_results = [
            {"chunk_id": "a", "source": "EN 1990", "score": 0.9},
            {"chunk_id": "b", "source": "EN 1990", "score": 0.8},
        ]
        bm25_results = [
            {"chunk_id": "b", "source": "EN 1990", "score": 5.0},
            {"chunk_id": "c", "source": "EN 1991", "score": 4.0},
        ]
        merged = retriever._merge_results(vec_results, bm25_results)
        ids = [r["chunk_id"] for r in merged]
        assert len(ids) == len(set(ids))
        assert set(ids) == {"a", "b", "c"}

    def test_exact_intent_prioritizes_bm25(self, retriever):
        vec_results = [{"chunk_id": "a", "source": "EN 1990", "score": 0.9}]
        bm25_results = [{"chunk_id": "b", "source": "EN 1990", "score": 5.0}]
        merged = retriever._merge_results(vec_results, bm25_results, intent=IntentType.EXACT)
        assert merged[0]["chunk_id"] == "b"


class TestCrossDocAggregation:
    def test_limits_per_source(self, retriever):
        results = [
            {"chunk_id": f"en1990_{i}", "source": "EN 1990", "score": 0.9 - i * 0.1}
            for i in range(5)
        ] + [
            {"chunk_id": "en1991_0", "source": "EN 1991", "score": 0.5}
        ]
        aggregated = retriever._cross_doc_aggregate(results, max_per_source=2)
        en1990_count = sum(1 for r in aggregated if r["source"] == "EN 1990")
        assert en1990_count <= 2
        assert any(r["source"] == "EN 1991" for r in aggregated)
