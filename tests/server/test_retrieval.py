"""Test hybrid retrieval layer (mock external services)."""

import asyncio
from unittest.mock import AsyncMock

import pytest
from elasticsearch import NotFoundError

from server.config import ServerConfig
from server.core.retrieval import HybridRetriever
from server.models.schemas import Chunk, ChunkMetadata, ElementType, GuideHint
from shared.spot_check import (
    SpotCheckRecorder,
    reset_current_recorder,
    set_current_recorder,
)


@pytest.fixture
def retriever():
    r = HybridRetriever.__new__(HybridRetriever)
    return r


def _make_chunk(
    chunk_id: str,
    text: str,
    *,
    source: str = "EN 1990:2002",
    source_title: str = "Basis",
    section_path: list[str] | None = None,
    clause_ids: list[str] | None = None,
    element_type: ElementType = ElementType.TEXT,
    object_type: str | None = None,
    object_label: str = "",
    object_id: str = "",
    ref_labels: list[str] | None = None,
    ref_object_ids: list[str] | None = None,
) -> Chunk:
    return Chunk(
        chunk_id=chunk_id,
        content=text,
        embedding_text=text,
        metadata=ChunkMetadata(
            source=source,
            source_title=source_title,
            section_path=section_path or ["2.3"],
            page_numbers=[28],
            page_file_index=[27],
            clause_ids=clause_ids or [],
            element_type=element_type,
            object_type=object_type,
            object_label=object_label,
            object_id=object_id,
            ref_labels=ref_labels or [],
            ref_object_ids=ref_object_ids or [],
        ),
    )


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

    def test_config_for_top_k_uses_per_call_limits(self, retriever):
        retriever.config = ServerConfig(
            vector_top_k=30,
            bm25_top_k=30,
            rerank_top_n=10,
        )

        cfg = retriever._config_for_top_k(5)

        assert cfg.vector_top_k == 15
        assert cfg.bm25_top_k == 15
        assert cfg.rerank_top_n == 5
        assert retriever.config.vector_top_k == 30
        assert retriever.config.bm25_top_k == 30
        assert retriever.config.rerank_top_n == 10

    def test_rrf_promotes_results_seen_by_both_retrievers(self, retriever):
        vec_results = [
            {"chunk_id": "vec-only", "source": "EN 1990", "score": 0.99},
            {"chunk_id": "shared", "source": "EN 1990", "score": 0.80},
        ]
        bm25_results = [
            {"chunk_id": "shared", "source": "EN 1990", "score": 10.0},
            {"chunk_id": "bm25-only", "source": "EN 1990", "score": 9.0},
        ]

        merged = retriever._merge_results(vec_results, bm25_results)

        assert [result["chunk_id"] for result in merged] == [
            "shared",
            "vec-only",
            "bm25-only",
        ]


class TestBm25Search:
    @pytest.mark.asyncio
    async def test_default_bm25_search_uses_weighted_metadata_fields(self):
        retriever = HybridRetriever.__new__(HybridRetriever)
        retriever.config = ServerConfig(es_index="chunks")
        seen_body: dict | None = None

        class _FakeEs:
            async def search(self, index: str, body: dict):
                nonlocal seen_body
                assert index == "chunks"
                seen_body = body
                return {"hits": {"hits": []}}

        async def _fake_get_es():
            return _FakeEs()

        retriever._get_es = _fake_get_es

        await retriever._bm25_search("design working life", 5, {})

        assert seen_body is not None
        fields = seen_body["query"]["bool"]["must"][0]["multi_match"]["fields"]
        assert fields == [
            "content^2",
            "embedding_text",
            "source_title.text^3",
            "section_path.text^2",
            "clause_ids.text^4",
            "object_aliases.text^5",
        ]

    @pytest.mark.asyncio
    async def test_bm25_search_returns_empty_when_index_missing(self):
        retriever = HybridRetriever.__new__(HybridRetriever)
        retriever.config = ServerConfig(es_index="missing_chunks")

        class _FakeEs:
            async def search(self, index: str, body: dict):
                raise NotFoundError(
                    message="index_not_found_exception",
                    meta=None,
                    body={"error": {"type": "index_not_found_exception"}},
                )

        async def _fake_get_es():
            return _FakeEs()

        retriever._get_es = _fake_get_es

        assert await retriever._bm25_search("empty index", 5, {}) == []


class TestChunkFetch:
    @pytest.mark.asyncio
    async def test_fetch_chunks_uses_mget_and_preserves_input_order(self):
        retriever = HybridRetriever.__new__(HybridRetriever)
        retriever.config = ServerConfig(es_index="chunks")
        seen_body: dict | None = None

        class _FakeEs:
            async def mget(self, index: str, body: dict):
                nonlocal seen_body
                assert index == "chunks"
                seen_body = body
                return {
                    "docs": [
                        {
                            "_id": "b",
                            "found": True,
                            "_source": {
                                "content": "chunk b",
                                "embedding_text": "chunk b",
                                "source": "EN 1990:2002",
                                "source_title": "Basis",
                                "section_path": ["1"],
                                "page_numbers": [1],
                                "page_file_index": [1],
                                "clause_ids": ["1"],
                                "element_type": "text",
                            },
                        },
                        {
                            "_id": "a",
                            "found": True,
                            "_source": {
                                "content": "chunk a",
                                "embedding_text": "chunk a",
                                "source": "EN 1991:2004",
                                "source_title": "Basis",
                                "section_path": ["1"],
                                "page_numbers": [1],
                                "page_file_index": [1],
                                "clause_ids": ["1"],
                                "element_type": "text",
                            },
                        },
                    ]
                }

        async def _fake_get_es():
            return _FakeEs()

        retriever._get_es = _fake_get_es

        chunks = await retriever._fetch_chunks(["a", "b"])

        assert seen_body == {"ids": ["a", "b"]}
        assert [chunk.chunk_id for chunk in chunks] == ["a", "b"]


class TestCrossRefConcurrency:
    @pytest.mark.asyncio
    async def test_fetch_cross_ref_chunks_keeps_stable_order_under_concurrency(
        self, retriever
    ):
        retriever.config = ServerConfig(es_index="chunks")
        events: list[str] = []

        def _fake_prioritize_cross_refs(refs: set[str]):
            return ["table 3.1", "figure 2.1"]

        async def _fake_exact_object_label_lookup(
            ref: str,
            category: str,
            filter_clauses: list[dict],
        ):
            events.append(f"lookup:{ref}")
            await asyncio.sleep(0)
            if ref == "table 3.1":
                return _make_chunk("table-3-1", "table", object_label=ref)
            return None

        async def _fake_bm25_search(
            query: str,
            top_k: int,
            filters: dict,
            fields: list[str] | None = None,
            preferred_element_type: str | None = None,
        ):
            events.append(f"bm25:{query}")
            await asyncio.sleep(0)
            if query == "figure 2.1":
                return [{"chunk_id": "figure-2-1", "score": 1.0}]
            return []

        async def _fake_fetch_chunks(chunk_ids: list[str]):
            events.append(f"fetch:{','.join(chunk_ids)}")
            chunk_map = {
                "figure-2-1": _make_chunk("figure-2-1", "figure", element_type=ElementType.IMAGE),
            }
            return [chunk_map[chunk_id] for chunk_id in chunk_ids]

        retriever._prioritize_cross_refs = _fake_prioritize_cross_refs
        retriever._exact_object_label_lookup = _fake_exact_object_label_lookup
        retriever._bm25_search = _fake_bm25_search
        retriever._fetch_chunks = _fake_fetch_chunks
        async def _fake_en_std_ref_in_corpus(ref: str):
            return True

        retriever._en_std_ref_in_corpus = _fake_en_std_ref_in_corpus

        ref_chunks = await retriever._fetch_cross_ref_chunks(
            {"figure 2.1", "table 3.1"},
            existing_ids=set(),
        )

        assert [chunk.chunk_id for chunk in ref_chunks] == ["table-3-1", "figure-2-1"]
        assert "lookup:table 3.1" in events
        assert "bm25:figure 2.1" in events


class TestCrossDocAggregation:
    def test_limits_per_source(self, retriever):
        results = [
            {"chunk_id": f"en1990_{i}", "source": "EN 1990", "score": 0.9 - i * 0.1}
            for i in range(5)
        ] + [{"chunk_id": "en1991_0", "source": "EN 1991", "score": 0.5}]
        aggregated = retriever._cross_doc_aggregate(results, max_per_source=2)
        en1990_count = sum(1 for r in aggregated if r["source"] == "EN 1990")
        assert en1990_count <= 2
        assert any(r["source"] == "EN 1991" for r in aggregated)

    def test_skips_aggregation_when_only_one_source_present(self, retriever):
        results = [
            {"chunk_id": f"en1990_{i}", "source": "EN 1990", "score": 0.9 - i * 0.1}
            for i in range(5)
        ]

        aggregated = retriever._cross_doc_aggregate(
            results,
            max_per_source=2,
            filters={},
        )

        assert aggregated == results


class TestGuideRetrieval:
    def test_should_fetch_guide_chunks_uses_question_type_or_guide_hint(
        self, retriever
    ):
        assert retriever._should_fetch_guide_chunks("calculation") is True
        assert retriever._should_fetch_guide_chunks("parameter") is True
        assert retriever._should_fetch_guide_chunks("rule") is False
        assert (
            retriever._should_fetch_guide_chunks(
                "rule",
                GuideHint(
                    need_example=True,
                    example_query="worked example",
                    example_kind="worked_example",
                ),
            )
            is True
        )

    def test_identifies_guide_chunks_from_generic_metadata(self, retriever):
        guide_chunk = _make_chunk(
            "uploaded-guide",
            "Commentary for load combinations.",
            source="Bridge Designers Guide 2024",
            source_title="Designers Guide to Eurocode load combinations",
        )
        spec_chunk = _make_chunk(
            "uploaded-spec",
            "Normative load combination rules.",
            source="EN 1990 uploaded",
            source_title="Eurocode - Basis of structural design",
        )

        assert retriever._is_guide_chunk(guide_chunk) is True
        assert retriever._is_guide_chunk(spec_chunk) is False

    @pytest.mark.asyncio
    async def test_retrieve_keeps_guide_chunks_as_citable_evidence(self, retriever):
        retriever.config = ServerConfig(rerank_top_n=3, vector_top_k=3, bm25_top_k=3)
        spec_chunk = _make_chunk(
            "spec-rule",
            "Normative rule for design value of load combinations.",
            source="EN 1990 uploaded",
            source_title="Eurocode - Basis of structural design",
            section_path=["6.4 Ultimate limit states"],
            clause_ids=["6.4.3"],
        )
        guide_chunk = _make_chunk(
            "guide-example",
            "Worked example for design value of load combinations.",
            source="Bridge Designers Guide 2024",
            source_title="Designers Guide to Eurocode load combinations",
            section_path=["Worked example 2.1"],
            clause_ids=["Worked example 2.1"],
        )
        chunk_map = {
            "spec-rule": spec_chunk,
            "guide-example": guide_chunk,
        }

        async def _fake_search(*_args, **_kwargs):
            return [
                {"chunk_id": "guide-example", "source": guide_chunk.metadata.source},
                {"chunk_id": "spec-rule", "source": spec_chunk.metadata.source},
            ]

        async def _fake_fetch_chunks(chunk_ids: list[str]):
            return [chunk_map[chunk_id] for chunk_id in chunk_ids]

        async def _fake_rerank(query: str, chunks: list[Chunk], top_n: int):
            return [
                (chunk, 0.9 - index * 0.1) for index, chunk in enumerate(chunks[:top_n])
            ]

        async def _fake_fetch_parent_chunks(chunks: list[Chunk]):
            return []

        retriever._vector_search = _fake_search
        retriever._bm25_search = _fake_search
        retriever._fetch_chunks = _fake_fetch_chunks
        retriever._rerank = _fake_rerank
        retriever._fetch_parent_chunks = _fake_fetch_parent_chunks

        result = await retriever.retrieve(
            queries=["design value load combinations"],
            original_query="怎么计算组合后的设计值？",
            question_type="calculation",
        )

        assert [chunk.chunk_id for chunk in result.chunks] == [
            "guide-example",
            "spec-rule",
        ]
        assert result.scores == [0.9, 0.8]
        assert [chunk.chunk_id for chunk in result.guide_chunks] == ["guide-example"]

    @pytest.mark.asyncio
    async def test_retrieve_does_not_empty_dg_only_evidence(self, retriever):
        retriever.config = ServerConfig(rerank_top_n=3, vector_top_k=3, bm25_top_k=3)
        guide_chunk = _make_chunk(
            "dg-rule",
            "Designers Guide explanation of partial factors.",
            source="DG_EN1990",
            source_title="Designers Guide to EN 1990",
            section_path=["Verification by the partial factor method", "6.5.4"],
            clause_ids=["6.5.4"],
        )

        async def _fake_search(*_args, **_kwargs):
            return [{"chunk_id": "dg-rule", "source": guide_chunk.metadata.source}]

        async def _fake_fetch_chunks(chunk_ids: list[str]):
            return [guide_chunk for _chunk_id in chunk_ids]

        async def _fake_rerank(query: str, chunks: list[Chunk], top_n: int):
            return [(chunk, 0.91) for chunk in chunks[:top_n]]

        async def _fake_fetch_parent_chunks(chunks: list[Chunk]):
            return []

        retriever._vector_search = _fake_search
        retriever._bm25_search = _fake_search
        retriever._fetch_chunks = _fake_fetch_chunks
        retriever._rerank = _fake_rerank
        retriever._fetch_parent_chunks = _fake_fetch_parent_chunks

        result = await retriever.retrieve(
            queries=["DG EN1990 6.5.4 partial factors"],
            original_query="DG EN1990 6.5.4 材料分项系数怎么取？",
        )

        assert [chunk.chunk_id for chunk in result.chunks] == ["dg-rule"]
        assert result.scores == [0.91]
        assert [chunk.chunk_id for chunk in result.guide_chunks] == ["dg-rule"]

    @pytest.mark.asyncio
    async def test_retrieve_guide_example_chunks_prioritizes_example_like_sections(
        self, retriever
    ):
        retriever.config = ServerConfig(rerank_top_n=3, vector_top_k=3, bm25_top_k=3)
        intro_chunk = _make_chunk(
            "guide-intro",
            "General commentary on load combinations.",
            source="Bridge Designers Guide 2024",
            source_title="Designers Guide to Eurocode load combinations",
            section_path=["2.3 Commentary"],
            clause_ids=["2.3"],
        )
        procedure_chunk = _make_chunk(
            "guide-procedure",
            "Step 1: determine the leading action. Step 2: apply combination factors.",
            source="Bridge Designers Guide 2024",
            source_title="Designers Guide to Eurocode load combinations",
            section_path=["2.3 Procedure"],
            clause_ids=["2.3"],
        )
        example_chunk = _make_chunk(
            "guide-example",
            "Worked example for design value of load combinations.",
            source="Bridge Designers Guide 2024",
            source_title="Designers Guide to Eurocode load combinations",
            section_path=["Example 2.1"],
            clause_ids=["Example 2.1"],
        )
        spec_chunk = _make_chunk(
            "spec-rule",
            "Normative rule for design value of load combinations.",
            source="EN 1990 uploaded",
            source_title="Eurocode - Basis of structural design",
            section_path=["6.4 Ultimate limit states"],
            clause_ids=["6.4.3"],
        )

        async def _fake_vector_search(query: str, top_k: int, filters: dict):
            assert filters == {}
            return [
                {"chunk_id": "spec-rule", "source": "EN 1990 uploaded", "score": 0.95},
                {
                    "chunk_id": "guide-intro",
                    "source": "Bridge Designers Guide 2024",
                    "score": 0.92,
                },
                {
                    "chunk_id": "guide-example",
                    "source": "Bridge Designers Guide 2024",
                    "score": 0.78,
                },
            ]

        async def _fake_bm25_search(
            query: str,
            top_k: int,
            filters: dict,
            fields: list[str] | None = None,
            **kwargs,
        ):
            assert filters == {}
            assert fields and "source_title.text^3" in fields
            return [
                {
                    "chunk_id": "guide-procedure",
                    "source": "Bridge Designers Guide 2024",
                    "score": 8.0,
                },
                {
                    "chunk_id": "guide-example",
                    "source": "Bridge Designers Guide 2024",
                    "score": 6.5,
                },
            ]

        async def _fake_fetch_chunks(chunk_ids: list[str]):
            chunk_map = {
                "spec-rule": spec_chunk,
                "guide-intro": intro_chunk,
                "guide-procedure": procedure_chunk,
                "guide-example": example_chunk,
            }
            return [chunk_map[chunk_id] for chunk_id in chunk_ids]

        async def _fake_rerank(query: str, chunks: list[Chunk], top_n: int):
            return [
                (intro_chunk, 0.99),
                (procedure_chunk, 0.95),
                (example_chunk, 0.88),
            ]

        retriever._vector_search = _fake_vector_search
        retriever._bm25_search = _fake_bm25_search
        retriever._fetch_chunks = _fake_fetch_chunks
        retriever._rerank = _fake_rerank

        result = await retriever._retrieve_guide_example_chunks(
            queries=["design value load combinations"],
            original_query="怎么计算组合后的设计值，最好给个算例",
            guide_hint=GuideHint(
                need_example=True,
                example_query="design value load combination worked example",
                example_kind="worked_example",
            ),
        )

        assert [chunk.chunk_id for chunk in result] == [
            "guide-example",
            "guide-procedure",
        ]


class TestCrossRefConstraints:
    def test_filter_results_by_source_matches_yearless_eurocode_filter(self, retriever):
        results = [
            {"chunk_id": "en1992", "source": "EN1992-1-1_2004", "score": 0.9},
            {"chunk_id": "dg1992", "source": "DG_EN1992-1-1__-1-2", "score": 0.8},
            {"chunk_id": "dg1992-space", "source": "DG EN1992-1-1  -1-2", "score": 0.85},
            {"chunk_id": "dg1990", "source": "DG EN1990", "score": 0.7},
            {"chunk_id": "plain-number", "source": "Guide 1992 example", "score": 0.6},
            {"chunk_id": "en19920", "source": "EN19920", "score": 0.5},
        ]

        filtered = retriever._filter_results_by_source(
            results,
            {"source": "EN 1992"},
        )

        assert [result["chunk_id"] for result in filtered] == [
            "en1992",
            "dg1992",
            "dg1992-space",
        ]

    def test_filter_results_by_sources_matches_alias_forms(self, retriever):
        results = [
            {"chunk_id": "dg1992-space", "source": "DG EN1992-1-1  -1-2", "score": 0.9},
            {"chunk_id": "en1990", "source": "EN1990_2002", "score": 0.8},
        ]

        filtered = retriever._filter_results_by_source(
            results,
            {"sources": ["DG_EN1992-1-1__-1-2"]},
        )

        assert [result["chunk_id"] for result in filtered] == ["dg1992-space"]

    def test_source_filter_matches_national_prefix_forms(self, retriever):
        results = [
            {"chunk_id": "bs1990", "source": "BS-EN-1990-2023", "score": 0.9},
            {"chunk_id": "en1993", "source": "DG_EN1993-1-1__-1-3__-1-8", "score": 0.8},
        ]

        filtered = retriever._filter_results_by_source(results, {"source": "EN 1990"})

        assert [result["chunk_id"] for result in filtered] == ["bs1990"]

    def test_build_cross_ref_filters_uses_explicit_source_filter(self, retriever):
        final_chunks = [_make_chunk("a", "See Table 3.1")]

        filters = retriever._build_cross_ref_filters(
            final_chunks,
            {"source": "EN 1992:2004"},
        )

        assert filters == {"source": "EN 1992:2004"}

    def test_build_cross_ref_filters_uses_final_chunk_sources(self, retriever):
        first = _make_chunk("a", "See Table 3.1")
        second = _make_chunk("b", "See Figure 2.1").model_copy(
            update={
                "metadata": _make_chunk("b", "See Figure 2.1").metadata.model_copy(
                    update={"source": "EN 1992:2004"}
                )
            }
        )

        filters = retriever._build_cross_ref_filters(first and [first, second], {})

        assert filters == {"sources": ["EN 1990:2002", "EN 1992:2004"]}

    def test_skips_aggregation_when_source_filter_is_explicit(self, retriever):
        results = [
            {"chunk_id": f"en1990_{i}", "source": "EN 1990", "score": 0.9 - i * 0.1}
            for i in range(5)
        ] + [{"chunk_id": "en1991_0", "source": "EN 1991", "score": 0.5}]

        aggregated = retriever._cross_doc_aggregate(
            results,
            max_per_source=2,
            filters={"source": "EN 1990"},
        )

        assert aggregated == results

    @pytest.mark.asyncio
    async def test_fetch_object_chunks_by_object_ids_uses_keyword_lookup(
        self, retriever
    ):
        retriever.config = ServerConfig(bm25_top_k=3, es_index="chunks")
        seen_bodies: list[dict] = []

        class _FakeEs:
            async def search(self, index: str, body: dict):
                assert index == "chunks"
                seen_bodies.append(body)
                return {
                    "hits": {
                        "hits": [
                            {"_id": "table-3-1", "_source": {"source": "EN 1992-1-1"}}
                        ]
                    }
                }

        async def _fake_get_es():
            return _FakeEs()

        async def _fake_fetch_chunks(chunk_ids: list[str]):
            assert chunk_ids == ["table-3-1"]
            return [
                _make_chunk(
                    "table-3-1",
                    "Table 3.1 Strength and deformation characteristics for concrete.",
                    source="EN 1992-1-1",
                    source_title="Strength and deformation characteristics for concrete",
                    section_path=["Table 3.1"],
                    clause_ids=["Table 3.1"],
                    element_type=ElementType.TABLE,
                    object_type="table",
                    object_label="Table 3.1",
                    object_id="en-1992-1-1#table:3.1",
                )
            ]

        retriever._get_es = _fake_get_es
        retriever._fetch_chunks = _fake_fetch_chunks

        ref_chunks = await retriever._fetch_object_chunks_by_object_ids(
            {"en-1992-1-1#table:3.1"},
            existing_ids=set(),
            filters={"source": "EN 1992-1-1"},
        )

        assert [chunk.chunk_id for chunk in ref_chunks] == ["table-3-1"]
        assert seen_bodies
        body = seen_bodies[0]
        assert body["query"]["bool"]["should"][0]["terms"]["object_id"] == [
            "en-1992-1-1#table:3.1"
        ]

    def test_lookup_aliases_for_table_keeps_normative_suffix_and_legacy_key(
        self, retriever
    ):
        object_type, aliases = retriever._lookup_aliases_for_object_id(
            "en-1992-1-1#table:2.1N"
        )

        assert object_type == "table"
        assert aliases == ["Table 2.1N", "Table 2.1"]

    @pytest.mark.asyncio
    async def test_fetch_object_chunks_by_object_ids_falls_back_to_alias_lookup_for_source_mismatch(
        self,
        retriever,
    ):
        retriever.config = ServerConfig(bm25_top_k=3, es_index="chunks")
        seen_bodies: list[dict] = []

        class _FakeEs:
            async def search(self, index: str, body: dict):
                assert index == "chunks"
                seen_bodies.append(body)
                return {
                    "hits": {
                        "hits": [
                            {
                                "_id": "table-3-1",
                                "_source": {"source": "EN1992-1-1 2004"},
                            }
                        ]
                    }
                }

        async def _fake_get_es():
            return _FakeEs()

        async def _fake_fetch_chunks(chunk_ids: list[str]):
            assert chunk_ids == ["table-3-1"]
            return [
                _make_chunk(
                    "table-3-1",
                    "Table 3.1 Strength and deformation characteristics for concrete.",
                    source="EN1992-1-1 2004",
                    source_title="Strength and deformation characteristics for concrete",
                    section_path=["Table 3.1"],
                    clause_ids=["Table 3.1"],
                    element_type=ElementType.TABLE,
                    object_type="table",
                    object_label="Table 3.1",
                    object_id="en1992-1-1-2004#table:3.1",
                )
            ]

        retriever._get_es = _fake_get_es
        retriever._fetch_chunks = _fake_fetch_chunks

        ref_chunks = await retriever._fetch_object_chunks_by_object_ids(
            {"en-1992-1-1#table:3.1"},
            existing_ids=set(),
            filters={"source": "EN 1992-1-1"},
        )

        assert [chunk.chunk_id for chunk in ref_chunks] == ["table-3-1"]
        assert seen_bodies
        body = seen_bodies[0]
        assert body["query"]["bool"]["minimum_should_match"] == 1
        assert any(
            clause.get("bool", {})
            .get("must", [{}])[0]
            .get("term", {})
            .get("object_type")
            == "table"
            for clause in body["query"]["bool"]["should"]
        )


class TestCrossRefExtractionAndResolution:
    """Audit-driven coverage for the cross-ref extractor + resolver fixes.

    See `.trellis/tasks/05-24-cross-ref-resolution/research/cross-ref-audit.md`
    for the bugs these tests pin down.
    """

    def test_extract_internal_refs_rejects_lowercase_annex_false_positives(
        self, retriever
    ):
        """Annex suffix must be uppercase — "National Annex proposes …" etc.
        must NOT produce fake refs like `Annex p`/`Annex m`/`Annex i`/`Annex c`.
        """
        chunk = _make_chunk(
            "fp",
            "National Annex proposes lower values. Annex may be referenced. "
            "Annex is provided. Annex can be used. National annex c overrides.",
        )
        refs = retriever._extract_internal_refs([chunk])
        for fp in ("Annex p", "Annex m", "Annex i", "Annex c"):
            assert fp not in refs, f"unexpected FP extracted: {fp}"

    def test_extract_internal_refs_normalises_trailing_punctuation(self, retriever):
        """`Figure 3.8)` and `Figure 6.1.` should normalise to the canonical form
        (no trailing `)` or `.`)."""
        chunk = _make_chunk(
            "trailing",
            "see Figure 3.8) for layout, shown in Figure 6.1. The bracket form "
            "(Table 4.7) also appears.",
        )
        refs = retriever._extract_internal_refs([chunk])
        assert "Figure 3.8" in refs
        assert "Figure 6.1" in refs
        assert "Table 4.7" in refs
        # Trailing-punct variants must not coexist with the canonical form.
        for bad in ("Figure 3.8)", "Figure 6.1.", "Table 4.7)"):
            assert bad not in refs

    def test_extract_internal_refs_preserves_normative_table_suffix(self, retriever):
        chunk = _make_chunk(
            "ndp-table",
            "Material partial factors are given in Table 2.1N and Table 4.3.",
        )
        refs = retriever._extract_internal_refs([chunk])

        assert "Table 2.1N" in refs
        assert "Table 2.1" not in refs
        assert "Table 4.3" in refs

    def test_extract_internal_refs_keeps_uppercase_annex(self, retriever):
        chunk = _make_chunk("ok", "Refer to Annex A and Annex C2 for additional rules.")
        refs = retriever._extract_internal_refs([chunk])
        assert "Annex A" in refs
        assert "Annex C2" in refs

    def test_refs_covered_by_chunks_uses_object_label_exact_match(self, retriever):
        chunk = _make_chunk(
            "tbl",
            "Table 4.7 - shear coefficients.",
            element_type=ElementType.TABLE,
            object_type="table",
            object_label="Table 4.7",
        )
        covered = retriever._refs_covered_by_chunks({"Table 4.7"}, [chunk])
        assert covered == {"Table 4.7"}

    def test_refs_covered_by_chunks_does_not_falsely_cover_figure_via_clause_digit(
        self, retriever
    ):
        """A chunk with `clause_ids=["6.10"]` must NOT be treated as covering
        a reference to `Figure 6.10` (audit bug F5)."""
        text_chunk = _make_chunk(
            "clause",
            "Expression (6.10) defines the design value.",
            element_type=ElementType.TEXT,
            section_path=["6.4.3"],
            clause_ids=["6.10"],
        )
        covered = retriever._refs_covered_by_chunks({"Figure 6.10"}, [text_chunk])
        assert covered == set()

    def test_refs_covered_by_chunks_covers_clause_ref_via_clause_ids(self, retriever):
        clause_chunk = _make_chunk(
            "clause",
            "Punching shear at column heads — see 6.4.3.",
            section_path=["6.4.3"],
            clause_ids=["6.4.3"],
        )
        covered = retriever._refs_covered_by_chunks({"6.4.3"}, [clause_chunk])
        assert "6.4.3" in covered

    def test_prioritize_cross_refs_orders_structured_refs_before_annex(self, retriever):
        refs = {
            "Annex A",
            "Table 4.7",
            "Expression (6.10)",
            "Figure 3.8",
            "EN 1992-1-1",
        }
        ordered = retriever._prioritize_cross_refs(refs)
        # Expression must be first; Annex/EN-std must be last.
        assert ordered[0] == "Expression (6.10)"
        assert ordered[-2:] == ["Annex A", "EN 1992-1-1"] or set(ordered[-2:]) == {
            "Annex A",
            "EN 1992-1-1",
        }
        # Sanity: structured group is contiguous and before Annex.
        annex_idx = ordered.index("Annex A")
        for structured in ("Expression (6.10)", "Table 4.7", "Figure 3.8"):
            assert ordered.index(structured) < annex_idx

    @pytest.mark.asyncio
    async def test_fetch_cross_ref_chunks_uses_exact_object_label_for_expression(
        self, retriever
    ):
        retriever.config = ServerConfig(bm25_top_k=3, es_index="chunks")
        retriever._en_sources_cache = {"1992-1-1"}
        seen_bodies: list[dict] = []

        class _FakeEs:
            async def search(self, index: str, body: dict):
                assert index == "chunks"
                seen_bodies.append(body)
                return {"hits": {"hits": [{"_id": "expr-6-10"}]}}

        async def _fake_get_es():
            return _FakeEs()

        async def _fake_fetch_chunks(chunk_ids: list[str]):
            assert chunk_ids == ["expr-6-10"]
            return [
                _make_chunk(
                    "expr-6-10",
                    "Expression (6.10) design value formula.",
                    element_type=ElementType.FORMULA,
                    object_type="expression",
                    object_label="Expression (6.10)",
                )
            ]

        bm25_calls: list[str] = []

        async def _fake_bm25(query: str, top_k: int, filters: dict, **kwargs):
            bm25_calls.append(query)
            return []

        retriever._get_es = _fake_get_es
        retriever._fetch_chunks = _fake_fetch_chunks
        retriever._bm25_search = _fake_bm25

        ref_chunks = await retriever._fetch_cross_ref_chunks(
            {"Expression (6.10)"},
            existing_ids=set(),
            filters={"source": "EN 1992-1-1"},
        )

        assert [c.chunk_id for c in ref_chunks] == ["expr-6-10"]
        # Deterministic path issued exactly one ES search; BM25 was NOT called.
        assert len(seen_bodies) == 1
        body = seen_bodies[0]
        filter_clauses = body["query"]["bool"]["filter"]
        label_clause = filter_clauses[0]["bool"]["should"]
        assert {"term": {"object_label": "Expression (6.10)"}} in label_clause
        assert {"terms": {"element_type": ["formula"]}} in filter_clauses
        assert bm25_calls == []

    @pytest.mark.asyncio
    async def test_exact_object_lookup_uses_object_aliases_when_label_differs(
        self,
        retriever,
    ):
        retriever.config = ServerConfig(bm25_top_k=3, es_index="chunks")
        seen_bodies: list[dict] = []

        class _FakeEs:
            async def search(self, index: str, body: dict):
                assert index == "chunks"
                seen_bodies.append(body)
                return {"hits": {"hits": [{"_id": "table-2-1"}]}}

        async def _fake_get_es():
            return _FakeEs()

        async def _fake_fetch_chunks(chunk_ids: list[str]):
            assert chunk_ids == ["table-2-1"]
            return [
                _make_chunk(
                    "table-2-1",
                    "Table 2.1N partial factors for materials.",
                    element_type=ElementType.TABLE,
                    object_type="table",
                    object_label="Table 2.1",
                )
            ]

        retriever._get_es = _fake_get_es
        retriever._fetch_chunks = _fake_fetch_chunks

        chunk = await retriever._exact_object_label_lookup(
            "Table 2.1N",
            "table",
            [],
        )

        assert chunk is not None
        assert chunk.chunk_id == "table-2-1"
        filter_clauses = seen_bodies[0]["query"]["bool"]["filter"]
        alias_clause = filter_clauses[0]["bool"]["should"][-1]
        assert alias_clause == {
            "terms": {"object_aliases": ["Table 2.1N", "Table 2.1"]}
        }

    @pytest.mark.asyncio
    async def test_fetch_cross_ref_chunks_falls_back_to_bm25_on_miss(self, retriever):
        retriever.config = ServerConfig(bm25_top_k=3, es_index="chunks")
        retriever._en_sources_cache = {"1992-1-1"}

        class _FakeEs:
            async def search(self, index: str, body: dict):
                return {"hits": {"hits": []}}

        async def _fake_get_es():
            return _FakeEs()

        bm25_calls: list[str] = []

        async def _fake_bm25(query: str, top_k: int, filters: dict, **kwargs):
            bm25_calls.append(query)
            return [{"chunk_id": "annex-a", "source": "EN 1992-1-1", "score": 1.0}]

        async def _fake_fetch_chunks(chunk_ids: list[str]):
            return [
                _make_chunk(
                    "annex-a",
                    "Annex A informative content",
                    source="EN 1992-1-1",
                )
            ]

        retriever._get_es = _fake_get_es
        retriever._bm25_search = _fake_bm25
        retriever._fetch_chunks = _fake_fetch_chunks

        ref_chunks = await retriever._fetch_cross_ref_chunks(
            {"Annex A"},
            existing_ids=set(),
            filters={"source": "EN 1992-1-1"},
        )

        assert [c.chunk_id for c in ref_chunks] == ["annex-a"]
        # Annex isn't categorized as table/figure/expression/clause, so the
        # exact-lookup path is skipped entirely and BM25 runs.
        assert bm25_calls == ["Annex A"]

    @pytest.mark.asyncio
    async def test_fetch_cross_ref_chunks_skips_absent_en_std(self, retriever):
        retriever.config = ServerConfig(bm25_top_k=3, es_index="chunks")
        retriever._en_sources_cache = {"1992-1-1", "1990"}  # `EN 1997` is absent
        bm25_calls: list[str] = []

        async def _fake_bm25(query: str, top_k: int, filters: dict, **kwargs):
            bm25_calls.append(query)
            return []

        async def _fake_get_es():
            raise AssertionError("ES must not be called for absent EN-std")

        retriever._bm25_search = _fake_bm25
        retriever._get_es = _fake_get_es

        ref_chunks = await retriever._fetch_cross_ref_chunks(
            {"EN 1997"},
            existing_ids=set(),
            filters={"source": "EN 1992-1-1"},
        )

        assert ref_chunks == []
        assert bm25_calls == []  # absent EN-std refs are skipped before lookup

    @pytest.mark.asyncio
    async def test_fetch_cross_ref_chunks_priority_attempts_expression_before_annex(
        self, retriever
    ):
        retriever.config = ServerConfig(bm25_top_k=3, es_index="chunks")
        retriever._en_sources_cache = {"1992-1-1"}
        attempted: list[str] = []

        class _FakeEs:
            async def search(self, index: str, body: dict):
                label_clause = body["query"]["bool"]["filter"][0]["bool"]["should"]
                ref = label_clause[0]["term"]["object_label"]
                attempted.append(ref)
                return {"hits": {"hits": []}}

        async def _fake_get_es():
            return _FakeEs()

        async def _fake_bm25(query: str, top_k: int, filters: dict, **kwargs):
            attempted.append(f"bm25:{query}")
            return []

        retriever._get_es = _fake_get_es
        retriever._bm25_search = _fake_bm25

        await retriever._fetch_cross_ref_chunks(
            {"Annex A", "Table 4.7", "Expression (6.10)"},
            existing_ids=set(),
            filters={"source": "EN 1992-1-1"},
        )

        # Expression must be attempted before Table; Table before Annex.
        idx = {
            name: pos
            for pos, name in enumerate(attempted)
            if not name.startswith("bm25:")
        }
        assert idx["Expression (6.10)"] < idx["Table 4.7"]
        bm25_idx = next(
            pos for pos, name in enumerate(attempted) if name == "bm25:Annex A"
        )
        assert idx["Table 4.7"] < bm25_idx


class TestReferenceClosure:
    @pytest.mark.asyncio
    async def test_metadata_probe_retrieve_resolves_direct_referenced_table_and_keeps_grounded(
        self,
    ):
        retriever = HybridRetriever.__new__(HybridRetriever)
        retriever.config = ServerConfig(rerank_top_n=3, vector_top_k=1, bm25_top_k=1)

        clause_chunk = _make_chunk(
            "clause",
            "The compressive strain in concrete shall be limited according to Table 3.1.",
            source="EN 1992-1-1",
            source_title="Stress-strain relations",
            section_path=["3.1.7"],
            clause_ids=["3.1.7"],
            object_type="clause",
            object_label="3.1.7",
            object_id="en-1992-1-1#clause:3.1.7",
            ref_object_ids=["en-1992-1-1#table:3.1"],
        )
        table_chunk = _make_chunk(
            "table-3-1",
            "Table 3.1 Strength and deformation characteristics for concrete.",
            source="EN 1992-1-1",
            source_title="Strength and deformation characteristics for concrete",
            section_path=["Table 3.1"],
            clause_ids=["Table 3.1"],
            element_type=ElementType.TABLE,
            object_type="table",
            object_label="Table 3.1",
            object_id="en-1992-1-1#table:3.1",
        )

        async def _fake_metadata_probe(**kwargs):
            return [{"chunk_id": "clause", "source": "EN 1992-1-1", "score": 0.96}]

        async def _fake_vector_search(query: str, top_k: int, filters: dict):
            return []

        async def _fake_bm25_search(query: str, top_k: int, filters: dict, **kwargs):
            return []

        async def _fake_fetch_chunks(chunk_ids: list[str]):
            chunk_map = {
                "clause": clause_chunk,
                "table-3-1": table_chunk,
            }
            return [chunk_map[chunk_id] for chunk_id in chunk_ids]

        async def _fake_rerank(query: str, chunks: list[Chunk], top_n: int):
            return [(chunks[0], 0.97)]

        async def _fake_fetch_parent_chunks(chunks: list[Chunk]):
            return []

        async def _fake_fetch_object_chunks_by_object_ids(
            object_ids: set[str],
            existing_ids: set[str],
            filters: dict | None = None,
            max_refs: int = 5,
        ):
            assert object_ids == {"en-1992-1-1#table:3.1"}
            return [table_chunk]

        async def _fake_fetch_cross_ref_chunks(*args, **kwargs):
            return []

        retriever._run_metadata_probe = _fake_metadata_probe
        retriever._vector_search = _fake_vector_search
        retriever._bm25_search = _fake_bm25_search
        retriever._fetch_chunks = _fake_fetch_chunks
        retriever._rerank = _fake_rerank
        retriever._fetch_parent_chunks = _fake_fetch_parent_chunks
        retriever._fetch_object_chunks_by_object_ids = (
            _fake_fetch_object_chunks_by_object_ids
        )
        retriever._fetch_cross_ref_chunks = _fake_fetch_cross_ref_chunks

        result = await retriever.retrieve(
            ["compressive strain limit"],
            original_query="3.1.7 里面混凝土受压应变限值怎么取",
            filters={"source": "EN 1992-1-1"},
            intent_label="limit",
            target_hint={"document": "EN 1992-1-1", "clause": "3.1.7"},
        )

        assert result.groundedness == "grounded"
        assert [chunk.chunk_id for chunk in result.chunks] == ["clause", "table-3-1"]
        assert result.ref_chunks == []
        assert result.unresolved_refs == []

    @pytest.mark.asyncio
    async def test_metadata_probe_retrieve_ignores_requested_clause_source_token_mismatch_when_clause_chunk_present(
        self,
    ):
        retriever = HybridRetriever.__new__(HybridRetriever)
        retriever.config = ServerConfig(rerank_top_n=3, vector_top_k=1, bm25_top_k=1)

        clause_chunk = _make_chunk(
            "clause",
            "The compressive strain in concrete shall be limited according to Table 3.1.",
            source="EN 1992-1-1 2004",
            source_title="Stress-strain relations",
            section_path=["3.1.7"],
            clause_ids=["3.1.7"],
            object_type="clause",
            object_label="3.1.7",
            object_id="en1992-1-1-2004#clause:3.1.7",
            ref_object_ids=["en1992-1-1-2004#table:3.1"],
            ref_labels=["Table 3.1"],
        )
        table_chunk = _make_chunk(
            "table-3-1",
            "Table 3.1 Strength and deformation characteristics for concrete.",
            source="EN 1992-1-1 2004",
            source_title="Strength and deformation characteristics for concrete",
            section_path=["Table 3.1"],
            clause_ids=["Table 3.1"],
            element_type=ElementType.TABLE,
            object_type="table",
            object_label="Table 3.1",
            object_id="en1992-1-1-2004#table:3.1",
        )

        async def _fake_metadata_probe(**kwargs):
            return [{"chunk_id": "clause", "source": "EN 1992-1-1 2004", "score": 0.96}]

        async def _fake_vector_search(query: str, top_k: int, filters: dict):
            return []

        async def _fake_bm25_search(query: str, top_k: int, filters: dict, **kwargs):
            return []

        async def _fake_fetch_chunks(chunk_ids: list[str]):
            chunk_map = {
                "clause": clause_chunk,
                "table-3-1": table_chunk,
            }
            return [chunk_map[chunk_id] for chunk_id in chunk_ids]

        async def _fake_rerank(query: str, chunks: list[Chunk], top_n: int):
            return [(chunks[0], 0.97)]

        async def _fake_fetch_parent_chunks(chunks: list[Chunk]):
            return []

        async def _fake_fetch_object_chunks_by_object_ids(
            object_ids: set[str],
            existing_ids: set[str],
            filters: dict | None = None,
            max_refs: int = 5,
        ):
            assert object_ids == {"en1992-1-1-2004#table:3.1"}
            return [table_chunk]

        async def _fake_fetch_cross_ref_chunks(*args, **kwargs):
            return []

        retriever._run_metadata_probe = _fake_metadata_probe
        retriever._vector_search = _fake_vector_search
        retriever._bm25_search = _fake_bm25_search
        retriever._fetch_chunks = _fake_fetch_chunks
        retriever._rerank = _fake_rerank
        retriever._fetch_parent_chunks = _fake_fetch_parent_chunks
        retriever._fetch_object_chunks_by_object_ids = (
            _fake_fetch_object_chunks_by_object_ids
        )
        retriever._fetch_cross_ref_chunks = _fake_fetch_cross_ref_chunks

        result = await retriever.retrieve(
            ["compressive strain limit"],
            original_query="3.1.7 里面混凝土受压应变限值怎么取",
            intent_label="limit",
            target_hint={"document": "EN 1992-1-1:2004", "clause": "3.1.7"},
            requested_objects=["3.1.7"],
        )

        assert result.groundedness == "grounded"
        assert "3.1.7" not in result.unresolved_refs

    @pytest.mark.asyncio
    async def test_metadata_probe_retrieve_does_not_require_unrequested_figures_for_reference_closure(
        self,
    ):
        retriever = HybridRetriever.__new__(HybridRetriever)
        retriever.config = ServerConfig(rerank_top_n=3, vector_top_k=1, bm25_top_k=1)

        clause_chunk = _make_chunk(
            "clause",
            "The compressive strain in concrete shall be limited according to Table 3.1 and Figure 3.5.",
            source="EN 1992-1-1",
            source_title="Stress-strain relations",
            section_path=["3.1.7"],
            clause_ids=["3.1.7"],
            object_type="clause",
            object_label="3.1.7",
            object_id="en-1992-1-1#clause:3.1.7",
            ref_object_ids=[
                "en-1992-1-1#table:3.1",
                "en-1992-1-1#figure:3.5",
            ],
            ref_labels=["Table 3.1", "Figure 3.5"],
        )
        table_chunk = _make_chunk(
            "table-3-1",
            "Table 3.1 Strength and deformation characteristics for concrete.",
            source="EN 1992-1-1",
            source_title="Strength and deformation characteristics for concrete",
            section_path=["Table 3.1"],
            clause_ids=["Table 3.1"],
            element_type=ElementType.TABLE,
            object_type="table",
            object_label="Table 3.1",
            object_id="en-1992-1-1#table:3.1",
        )

        async def _fake_metadata_probe(**kwargs):
            return [{"chunk_id": "clause", "source": "EN 1992-1-1", "score": 0.96}]

        async def _fake_vector_search(query: str, top_k: int, filters: dict):
            return []

        async def _fake_bm25_search(query: str, top_k: int, filters: dict, **kwargs):
            return []

        async def _fake_fetch_chunks(chunk_ids: list[str]):
            chunk_map = {
                "clause": clause_chunk,
                "table-3-1": table_chunk,
            }
            return [chunk_map[chunk_id] for chunk_id in chunk_ids]

        async def _fake_rerank(query: str, chunks: list[Chunk], top_n: int):
            return [(chunks[0], 0.97)]

        async def _fake_fetch_parent_chunks(chunks: list[Chunk]):
            return []

        async def _fake_fetch_object_chunks_by_object_ids(
            object_ids: set[str],
            existing_ids: set[str],
            filters: dict | None = None,
            max_refs: int = 5,
        ):
            assert object_ids == {
                "en-1992-1-1#table:3.1",
                "en-1992-1-1#figure:3.5",
            }
            return [table_chunk]

        async def _fake_fetch_cross_ref_chunks(*args, **kwargs):
            return []

        retriever._run_metadata_probe = _fake_metadata_probe
        retriever._vector_search = _fake_vector_search
        retriever._bm25_search = _fake_bm25_search
        retriever._fetch_chunks = _fake_fetch_chunks
        retriever._rerank = _fake_rerank
        retriever._fetch_parent_chunks = _fake_fetch_parent_chunks
        retriever._fetch_object_chunks_by_object_ids = (
            _fake_fetch_object_chunks_by_object_ids
        )
        retriever._fetch_cross_ref_chunks = _fake_fetch_cross_ref_chunks

        result = await retriever.retrieve(
            ["compressive strain limit"],
            original_query="3.1.7 里面混凝土受压应变限值怎么取",
            filters={"source": "EN 1992-1-1"},
            intent_label="limit",
            target_hint={"document": "EN 1992-1-1", "clause": "3.1.7"},
        )

        assert result.groundedness == "grounded"
        assert result.unresolved_refs == []

    @pytest.mark.asyncio
    async def test_metadata_probe_retrieve_ignores_shadowed_clause_request_when_same_table_is_requested(
        self,
    ):
        retriever = HybridRetriever.__new__(HybridRetriever)
        retriever.config = ServerConfig(rerank_top_n=3, vector_top_k=1, bm25_top_k=1)

        table_chunk = _make_chunk(
            "table-3-1",
            "Table 3.1 Strength and deformation characteristics for concrete.",
            source="EN 1992-1-1 2004",
            source_title="Strength and deformation characteristics for concrete",
            section_path=["Table 3.1"],
            clause_ids=["Table 3.1"],
            element_type=ElementType.TABLE,
            object_type="table",
            object_label="Table 3.1",
            object_id="en1992-1-1-2004#table:3.1",
        )

        async def _fake_metadata_probe(**kwargs):
            return [
                {"chunk_id": "table-3-1", "source": "EN 1992-1-1 2004", "score": 0.98}
            ]

        async def _fake_vector_search(query: str, top_k: int, filters: dict):
            return []

        async def _fake_bm25_search(query: str, top_k: int, filters: dict, **kwargs):
            return []

        async def _fake_fetch_chunks(chunk_ids: list[str]):
            return [table_chunk]

        async def _fake_rerank(query: str, chunks: list[Chunk], top_n: int):
            return [(chunks[0], 0.98)]

        async def _fake_fetch_parent_chunks(chunks: list[Chunk]):
            return []

        async def _fake_fetch_object_chunks_by_object_ids(
            object_ids: set[str],
            existing_ids: set[str],
            filters: dict | None = None,
            max_refs: int = 5,
        ):
            assert object_ids == set()
            return []

        async def _fake_fetch_cross_ref_chunks(*args, **kwargs):
            return []

        retriever._run_metadata_probe = _fake_metadata_probe
        retriever._vector_search = _fake_vector_search
        retriever._bm25_search = _fake_bm25_search
        retriever._fetch_chunks = _fake_fetch_chunks
        retriever._rerank = _fake_rerank
        retriever._fetch_parent_chunks = _fake_fetch_parent_chunks
        retriever._fetch_object_chunks_by_object_ids = (
            _fake_fetch_object_chunks_by_object_ids
        )
        retriever._fetch_cross_ref_chunks = _fake_fetch_cross_ref_chunks

        result = await retriever.retrieve(
            ["table 3.1 concrete strength classes"],
            original_query="Table 3.1 混凝土强度等级有哪些？",
            filters={"element_type": "table"},
            intent_label="clause_lookup",
            target_hint={"document": "EN 1992-1-1:2004", "object": "Table 3.1"},
            requested_objects=["Table 3.1", "3.1"],
        )

        assert result.groundedness == "grounded"
        assert result.unresolved_refs == []

    @pytest.mark.asyncio
    async def test_metadata_probe_retrieve_uses_selected_chunk_refs_for_reference_closure(
        self,
    ):
        retriever = HybridRetriever.__new__(HybridRetriever)
        retriever.config = ServerConfig(rerank_top_n=3, vector_top_k=1, bm25_top_k=1)

        selected_chunk = _make_chunk(
            "selected",
            "When determining the ultimate moment resistance, the following assumptions are made: plane sections remain plane.",
            source="EN 1992-1-1 2004",
            source_title="Bending with or without axial force",
            section_path=["6.1"],
            clause_ids=["6.1"],
            object_type="clause",
            object_label="6.1",
            object_id="en1992-1-1-2004#clause:6.1",
        )
        noisy_chunk = _make_chunk(
            "table-shadow",
            "Table 6.1 Coefficients for rectangular sections.",
            source="EN 1992-1-1 2004",
            source_title="Table 6.1: Coefficients for rectangular sections",
            section_path=["Table 6.1: Coefficients for rectangular sections"],
            clause_ids=["Table 6.1"],
            ref_labels=["Table 6.1"],
            ref_object_ids=["en1992-1-1-2004#table:6.1"],
        )

        async def _fake_metadata_probe(**kwargs):
            return [
                {"chunk_id": "selected", "source": "EN 1992-1-1 2004", "score": 0.99},
                {
                    "chunk_id": "table-shadow",
                    "source": "EN 1992-1-1 2004",
                    "score": 0.98,
                },
            ]

        async def _fake_vector_search(query: str, top_k: int, filters: dict):
            return []

        async def _fake_bm25_search(query: str, top_k: int, filters: dict, **kwargs):
            return []

        async def _fake_fetch_chunks(chunk_ids: list[str]):
            chunk_map = {
                "selected": selected_chunk,
                "table-shadow": noisy_chunk,
            }
            return [chunk_map[chunk_id] for chunk_id in chunk_ids]

        async def _fake_rerank(query: str, chunks: list[Chunk], top_n: int):
            return [(chunks[0], 0.97), (chunks[1], 0.96)]

        async def _fake_fetch_parent_chunks(chunks: list[Chunk]):
            return []

        async def _fake_fetch_object_chunks_by_object_ids(
            object_ids: set[str],
            existing_ids: set[str],
            filters: dict | None = None,
            max_refs: int = 5,
        ):
            assert object_ids == set()
            return []

        async def _fake_fetch_cross_ref_chunks(*args, **kwargs):
            return []

        retriever._run_metadata_probe = _fake_metadata_probe
        retriever._vector_search = _fake_vector_search
        retriever._bm25_search = _fake_bm25_search
        retriever._fetch_chunks = _fake_fetch_chunks
        retriever._rerank = _fake_rerank
        retriever._fetch_parent_chunks = _fake_fetch_parent_chunks
        retriever._fetch_object_chunks_by_object_ids = (
            _fake_fetch_object_chunks_by_object_ids
        )
        retriever._fetch_cross_ref_chunks = _fake_fetch_cross_ref_chunks

        result = await retriever.retrieve(
            ["basic assumptions for section design"],
            original_query="欧标的截面计算的基本假设前提是什么",
            filters={"source": "EN 1992-1-1"},
            intent_label="assumption",
            target_hint={
                "document": "EN 1992-1-1",
                "clause": "6.1",
                "object": "basic assumptions",
            },
        )

        assert [chunk.chunk_id for chunk in result.chunks] == [
            "selected",
            "table-shadow",
        ]
        assert result.groundedness == "grounded"
        assert result.unresolved_refs == []

    @pytest.mark.asyncio
    async def test_metadata_probe_retrieve_degrades_when_direct_referenced_table_is_unresolved(
        self,
    ):
        retriever = HybridRetriever.__new__(HybridRetriever)
        retriever.config = ServerConfig(rerank_top_n=1, vector_top_k=1, bm25_top_k=1)

        clause_chunk = _make_chunk(
            "clause",
            "The compressive strain in concrete shall be limited according to Table 3.1.",
            source="EN 1992-1-1",
            source_title="Stress-strain relations",
            section_path=["3.1.7"],
            clause_ids=["3.1.7"],
            object_type="clause",
            object_label="3.1.7",
            object_id="en-1992-1-1#clause:3.1.7",
            ref_object_ids=["en-1992-1-1#table:3.1"],
        )

        async def _fake_metadata_probe(**kwargs):
            return [{"chunk_id": "clause", "source": "EN 1992-1-1", "score": 0.96}]

        async def _fake_vector_search(query: str, top_k: int, filters: dict):
            return []

        async def _fake_bm25_search(query: str, top_k: int, filters: dict, **kwargs):
            return []

        async def _fake_fetch_chunks(chunk_ids: list[str]):
            return [clause_chunk]

        async def _fake_rerank(query: str, chunks: list[Chunk], top_n: int):
            return [(chunks[0], 0.97)]

        async def _fake_fetch_parent_chunks(chunks: list[Chunk]):
            return []

        async def _fake_fetch_object_chunks_by_object_ids(
            object_ids: set[str],
            existing_ids: set[str],
            filters: dict | None = None,
            max_refs: int = 5,
        ):
            assert object_ids == {"en-1992-1-1#table:3.1"}
            return []

        async def _fake_fetch_cross_ref_chunks(*args, **kwargs):
            return []

        retriever._run_metadata_probe = _fake_metadata_probe
        retriever._vector_search = _fake_vector_search
        retriever._bm25_search = _fake_bm25_search
        retriever._fetch_chunks = _fake_fetch_chunks
        retriever._rerank = _fake_rerank
        retriever._fetch_parent_chunks = _fake_fetch_parent_chunks
        retriever._fetch_object_chunks_by_object_ids = (
            _fake_fetch_object_chunks_by_object_ids
        )
        retriever._fetch_cross_ref_chunks = _fake_fetch_cross_ref_chunks

        result = await retriever.retrieve(
            ["compressive strain limit"],
            original_query="3.1.7 里面混凝土受压应变限值怎么取",
            filters={"source": "EN 1992-1-1"},
            intent_label="limit",
            target_hint={"document": "EN 1992-1-1", "clause": "3.1.7"},
        )

        assert result.groundedness == "partial"
        assert result.ref_chunks == []
        assert result.unresolved_refs == ["Table 3.1"]


class TestRerank:
    @pytest.mark.asyncio
    async def test_rerank_uses_client_scores(self):
        retriever = HybridRetriever(
            ServerConfig(
                rerank_provider="remote",
                rerank_api_url="https://rerank.example/v1/rerank",
                rerank_model="rerank-model",
            )
        )

        class _FakeRerankClient:
            async def rerank(self, query: str, documents: list[str], top_n: int):
                assert query == "wind load"
                assert documents == ["doc-a", "doc-b"]
                assert top_n == 2
                return [(1, 0.93), (0, 0.51)]

        retriever._rerank_client = _FakeRerankClient()

        ranked = await retriever._rerank(
            "wind load",
            [_make_chunk("a", "doc-a"), _make_chunk("b", "doc-b")],
            2,
        )

        assert [chunk.chunk_id for chunk, _ in ranked] == ["b", "a"]
        assert [score for _, score in ranked] == [0.93, 0.51]

    @pytest.mark.asyncio
    async def test_rerank_records_spot_check_token_fields(self, monkeypatch):
        retriever = HybridRetriever(
            ServerConfig(
                rerank_provider="remote",
                rerank_api_url="https://rerank.example/v1/rerank",
                rerank_model="rerank-model",
                rerank_max_length=4,
            )
        )

        class _FakeRerankClient:
            async def rerank(self, query: str, documents: list[str], top_n: int):
                return [(0, 0.9)]

        monkeypatch.setattr(
            "server.core.retrieval.count_for_rerank",
            lambda text, model: (len(text), False),
        )
        retriever._rerank_client = _FakeRerankClient()
        recorder = SpotCheckRecorder(query="wind load", query_id="q1")
        token = set_current_recorder(recorder)
        try:
            await retriever._rerank("wind load", [_make_chunk("a", "doc-a")], 1)
        finally:
            reset_current_recorder(token)

        assert recorder.data["rerank_input_tokens"] == [
            {
                "chunk_id": "a",
                "tokens": 5,
                "is_estimate": False,
                "source": "EN 1990:2002",
                "element_type": "text",
            }
        ]
        assert recorder.data["rerank_truncated"] == [
            {
                "chunk_id": "a",
                "tokens": 5,
                "max_tokens": 4,
                "truncated": True,
                "truncation_ratio": 5 / 4,
                "source": "EN 1990:2002",
                "element_type": "text",
            }
        ]


class TestRerankText:
    def test_text_chunk_uses_embedding_text(self, retriever):
        chunk = _make_chunk("a", "full content", element_type=ElementType.TEXT)
        chunk.embedding_text = "short embedding"
        assert retriever._rerank_text(chunk) == "short embedding"

    def test_text_chunk_falls_back_to_content(self, retriever):
        chunk = _make_chunk("a", "full content", element_type=ElementType.TEXT)
        chunk.embedding_text = ""
        assert retriever._rerank_text(chunk) == "full content"

    def test_table_chunk_uses_content(self, retriever):
        chunk = _make_chunk(
            "t1",
            "<table><tr><td>C30</td><td>30</td></tr></table>",
            element_type=ElementType.TABLE,
            object_label="Table 3.1",
        )
        chunk.embedding_text = "短摘要"
        result = retriever._rerank_text(chunk)
        assert "Table 3.1" in result
        assert "<table>" in result
        assert "短摘要" not in result

    def test_formula_chunk_uses_content(self, retriever):
        chunk = _make_chunk(
            "f1",
            "$$R_d = R / \\gamma$$",
            element_type=ElementType.FORMULA,
        )
        chunk.embedding_text = "公式摘要"
        result = retriever._rerank_text(chunk)
        assert "R_d" in result
        assert "公式摘要" not in result

    def test_table_content_truncated_at_2000_chars(self, retriever):
        long_content = "x" * 3000
        chunk = _make_chunk("t2", long_content, element_type=ElementType.TABLE)
        result = retriever._rerank_text(chunk)
        assert len(result) == 2000


class TestRetrieveFallback:
    @pytest.mark.asyncio
    async def test_retrieve_falls_back_to_unreranked_chunks_when_rerank_fails(self):
        retriever = HybridRetriever.__new__(HybridRetriever)
        retriever.config = ServerConfig(rerank_top_n=1)

        async def _fake_vector_search(query: str, top_k: int, filters: dict):
            return [{"chunk_id": "a", "source": "EN 1990", "score": 0.7}]

        async def _fake_bm25_search(query: str, top_k: int, filters: dict, **kwargs):
            return [{"chunk_id": "b", "source": "EN 1990", "score": 5.0}]

        async def _fake_fetch_chunks(chunk_ids: list[str]):
            return [_make_chunk(chunk_id, f"doc-{chunk_id}") for chunk_id in chunk_ids]

        async def _fake_rerank(query: str, chunks: list[Chunk], top_n: int):
            raise RuntimeError("rerank unavailable")

        async def _fake_fetch_parent_chunks(chunks: list[Chunk]):
            assert [chunk.chunk_id for chunk in chunks] == ["a"]
            return []

        retriever._vector_search = _fake_vector_search
        retriever._bm25_search = _fake_bm25_search
        retriever._fetch_chunks = _fake_fetch_chunks
        retriever._rerank = _fake_rerank
        retriever._fetch_parent_chunks = _fake_fetch_parent_chunks

        result = await retriever.retrieve(["wind load"])

        assert [chunk.chunk_id for chunk in result.chunks] == ["a"]
        assert result.parent_chunks == []
        assert result.scores == [0.0]

    @pytest.mark.asyncio
    async def test_retrieve_uses_original_query_as_vector_only_supplement(self):
        retriever = HybridRetriever.__new__(HybridRetriever)
        retriever.config = ServerConfig(rerank_top_n=3)
        seen_vector_queries: list[str] = []
        seen_bm25_queries: list[str] = []

        async def _fake_vector_search(query: str, top_k: int, filters: dict):
            seen_vector_queries.append(query)
            if query == "design working life metro":
                return [{"chunk_id": "a", "source": "EN 1990", "score": 0.9}]
            if query == "地铁的设计使用年限":
                return [{"chunk_id": "c", "source": "EN 1992", "score": 0.6}]
            return []

        async def _fake_bm25_search(query: str, top_k: int, filters: dict, **kwargs):
            seen_bm25_queries.append(query)
            return [{"chunk_id": "b", "source": "EN 1990", "score": 5.0}]

        async def _fake_fetch_chunks(chunk_ids: list[str]):
            return [_make_chunk(chunk_id, f"doc-{chunk_id}") for chunk_id in chunk_ids]

        async def _fake_rerank(query: str, chunks: list[Chunk], top_n: int):
            # rerank 使用 expanded query 的英文版本（对英文 chunks 更准）
            assert query == "design working life metro"
            assert set(chunk.chunk_id for chunk in chunks) == {"a", "b", "c"}
            return [
                (chunks[0], 0.91),
                (chunks[1], 0.74),
                (chunks[2], 0.52),
            ]

        async def _fake_fetch_parent_chunks(chunks: list[Chunk]):
            return []

        retriever._vector_search = _fake_vector_search
        retriever._bm25_search = _fake_bm25_search
        retriever._fetch_chunks = _fake_fetch_chunks
        retriever._rerank = _fake_rerank
        retriever._fetch_parent_chunks = _fake_fetch_parent_chunks

        result = await retriever.retrieve(
            ["design working life metro"],
            original_query="地铁的设计使用年限",
        )

        assert seen_vector_queries == [
            "design working life metro",
            "地铁的设计使用年限",
        ]
        assert seen_bm25_queries == ["design working life metro"]
        assert [chunk.chunk_id for chunk in result.chunks] == ["a", "b", "c"]
        assert result.scores == [0.91, 0.74, 0.52]

    @pytest.mark.asyncio
    async def test_retrieve_constrains_cross_ref_search_to_final_chunk_sources(self):
        retriever = HybridRetriever.__new__(HybridRetriever)
        retriever.config = ServerConfig(rerank_top_n=1)
        seen_bm25_filters: list[dict] = []

        async def _fake_vector_search(query: str, top_k: int, filters: dict):
            return [{"chunk_id": "a", "source": "EN 1990:2002", "score": 0.9}]

        async def _fake_bm25_search(query: str, top_k: int, filters: dict, **kwargs):
            seen_bm25_filters.append({"query": query, "filters": filters})
            if query == "wind load":
                return []
            if query == "Table 3.1":
                assert filters == {"source": "EN 1990:2002"}
                return []
            return []

        async def _fake_fetch_chunks(chunk_ids: list[str]):
            if chunk_ids == ["a"]:
                return [_make_chunk("a", "See Table 3.1 for details.")]
            return []

        async def _fake_rerank(query: str, chunks: list[Chunk], top_n: int):
            return [(chunks[0], 0.93)]

        async def _fake_fetch_parent_chunks(chunks: list[Chunk]):
            return []

        retriever._vector_search = _fake_vector_search
        retriever._bm25_search = _fake_bm25_search
        retriever._fetch_chunks = _fake_fetch_chunks
        retriever._rerank = _fake_rerank
        retriever._fetch_parent_chunks = _fake_fetch_parent_chunks

        result = await retriever.retrieve(["wind load"])

        assert result.ref_chunks == []
        assert seen_bm25_filters[-1] == {
            "query": "Table 3.1",
            "filters": {"source": "EN 1990:2002"},
        }

    def test_build_coverage_targets_splits_compound_factor_query(self, retriever):
        targets = retriever._build_coverage_targets(
            [
                "concrete structural design Eurocode partial factors for actions and materials"
            ],
            "请给出混凝土结构设计中相关作用荷载和材料的分项系数。",
        )

        assert [target.name for target in targets] == ["actions", "materials"]
        material_target = next(target for target in targets if target.name == "materials")
        assert "EN 1992-1-1" in material_target.query
        assert "Table 2.1N" in material_target.query
        assert material_target.preferred_element_type == "table"

    def test_missing_coverage_targets_detects_uncovered_material_slot(self, retriever):
        targets = retriever._build_coverage_targets(
            [
                "concrete structural design Eurocode partial factors for actions and materials"
            ],
            "请给出混凝土结构设计中相关作用荷载和材料的分项系数。",
        )
        action_chunk = _make_chunk(
            "actions",
            "Table A1.2(C): Design values of actions STR/GEO. gamma_G 1.35 and gamma_Q 1.50.",
            source="EN 1990",
            element_type=ElementType.TABLE,
            object_type="table",
            object_label="Table A1.2",
        )

        missing = retriever._missing_coverage_targets(targets, [action_chunk])

        assert [target.name for target in missing] == ["materials"]

    def test_material_coverage_requires_factor_specific_signal(self, retriever):
        targets = retriever._build_coverage_targets(
            [
                "concrete structural design Eurocode partial factors for actions and materials"
            ],
            "请给出混凝土结构设计中相关作用荷载和材料的分项系数。",
        )
        material_target = next(target for target in targets if target.name == "materials")
        background_chunk = _make_chunk(
            "background-materials",
            "The provisions of that code are applicable to all materials.",
            source="DG EN1992-1-1",
            section_path=["2.2", "General"],
        )

        assert (
            retriever._chunk_matches_coverage_target(background_chunk, material_target)
            is False
        )

    def test_action_coverage_requires_factor_specific_signal(self, retriever):
        targets = retriever._build_coverage_targets(
            [
                "concrete structural design Eurocode partial factors for actions and materials"
            ],
            "请给出混凝土结构设计中相关作用荷载和材料的分项系数。",
        )
        action_target = next(target for target in targets if target.name == "actions")
        representative_values_chunk = _make_chunk(
            "representative-actions",
            "The representative value of an action F_rep should be its characteristic value F_k.",
            source="BS-EN-1990-2023",
            section_path=["6.1.2", "Representative values of actions"],
        )
        annex_chunk = _make_chunk(
            "annex-actions",
            "Table A1.2(C): Design values of actions STR/GEO. gamma_G 1.35 and gamma_Q 1.50.",
            source="EN1990_2002",
            element_type=ElementType.TABLE,
            object_type="table",
            object_label="Table A1.2",
            section_path=["Annex A1"],
        )

        assert (
            retriever._chunk_matches_coverage_target(
                representative_values_chunk,
                action_target,
            )
            is False
        )
        assert retriever._chunk_matches_coverage_target(annex_chunk, action_target) is True

    def test_material_coverage_rejects_unrelated_gamma_table(self, retriever):
        targets = retriever._build_coverage_targets(
            [
                "EN 1992-1-1 material partial factors concrete reinforcement "
                "gamma_C gamma_S Table 2.1N"
            ],
            "请比较混凝土结构持久短暂工况与偶然工况下材料分项系数。",
        )
        material_target = next(target for target in targets if target.name == "materials")
        unrelated_table = _make_chunk(
            "table-6-1",
            "Table 6.1. Values of (0.18 / gamma_c)(100 rho_l f_ck)^(1/3).",
            source="DG EN1992-1-1",
            element_type=ElementType.TABLE,
            object_type="table",
            object_label="Table 6.1",
        )

        assert (
            retriever._chunk_matches_coverage_target(unrelated_table, material_target)
            is False
        )

    def test_material_coverage_accepts_safety_factor_synonym_table(self, retriever):
        targets = retriever._build_coverage_targets(
            [
                "EN 1992-1-1 material partial factors concrete reinforcement "
                "gamma_C gamma_S"
            ],
            "请给出混凝土结构设计中相关作用荷载和材料的分项系数。",
        )
        material_target = next(target for target in targets if target.name == "materials")
        guide_material_table = _make_chunk(
            "table-2-6",
            "Table 2.6. Partial safety factors for material properties. "
            "Concrete gamma_C 1.5 and reinforcement gamma_S 1.15.",
            source="DG EN1992-1-1",
            element_type=ElementType.TABLE,
            object_type="table",
            object_label="Table 2.6",
        )

        assert (
            retriever._chunk_matches_coverage_target(
                guide_material_table,
                material_target,
            )
            is True
        )

    @pytest.mark.asyncio
    async def test_coverage_exact_lookup_filters_same_label_by_target_semantics(
        self,
    ):
        retriever = HybridRetriever.__new__(HybridRetriever)
        retriever.config = ServerConfig(rerank_top_n=1, bm25_top_k=1, vector_top_k=1)
        targets = retriever._build_coverage_targets(
            [
                "EN 1992-1-1 material partial factors concrete reinforcement "
                "gamma_C gamma_S Table 4.3"
            ],
            "请给出混凝土结构设计中相关作用荷载和材料的分项系数。",
        )
        material_target = next(target for target in targets if target.name == "materials")
        shrinkage_table = _make_chunk(
            "table-4-3-shrinkage",
            "Table 4.3. Values of epsilon_cd for drying shrinkage.",
            source="DG EN1992-1-1",
            element_type=ElementType.TABLE,
            object_type="table",
            object_label="Table 4.3",
        )
        material_factor_table = _make_chunk(
            "table-4-3-material-factors",
            "Table 4.3. Partial factors for materials: concrete gamma_C and reinforcing steel gamma_S.",
            source="BSEN1992-1-1-2023",
            element_type=ElementType.TABLE,
            object_type="table",
            object_label="Table 4.3",
        )

        async def _fake_exact_candidates(
            ref: str,
            category: str,
            filter_clauses: list[dict],
            *,
            size: int = 1,
        ):
            assert category == "table"
            if ref == "Table 2.1N":
                return []
            assert ref == "Table 4.3"
            return [shrinkage_table, material_factor_table]

        retriever._exact_object_label_candidates = _fake_exact_candidates
        retriever._bm25_search = AsyncMock(return_value=[])
        retriever._fetch_chunks = AsyncMock(return_value=[])

        chunks = await retriever._fetch_coverage_target_chunks(
            [material_target],
            existing_ids=set(),
            filters={},
        )

        assert [chunk.chunk_id for chunk in chunks] == ["table-4-3-material-factors"]

    def test_expanded_table_query_does_not_create_generic_table_target(self, retriever):
        targets = retriever._build_coverage_targets(
            [
                "EN 1992-1-1 material partial factors concrete reinforcement "
                "gamma_C gamma_S Table 2.1N"
            ],
            "请比较混凝土结构持久短暂工况与偶然工况下材料分项系数。",
        )

        assert [target.name for target in targets] == ["materials"]

    @pytest.mark.asyncio
    async def test_retrieve_adds_coverage_supplement_for_missing_material_slot(self):
        retriever = HybridRetriever.__new__(HybridRetriever)
        retriever.config = ServerConfig(rerank_top_n=1, bm25_top_k=1, vector_top_k=1)
        seen_coverage_queries: list[str] = []

        action_chunk = _make_chunk(
            "action",
            "EN 1990 gives partial factors for actions and load combinations.",
            source="EN 1990",
        )
        material_chunk = _make_chunk(
            "material-table",
            "Table 2.1N: Partial factors for materials. gamma_C 1.5 gamma_S 1.15.",
            source="EN1992-1-1 2004",
            element_type=ElementType.TABLE,
            object_type="table",
            object_label="Table 2.1N",
            object_id="en1992-1-1-2004#table:2.1N",
        )

        async def _fake_vector_search(query: str, top_k: int, filters: dict):
            return [{"chunk_id": "action", "source": "EN 1990", "score": 0.9}]

        async def _fake_bm25_search(
            query: str,
            top_k: int,
            filters: dict,
            **kwargs,
        ):
            if "material partial factors" in query:
                seen_coverage_queries.append(query)
                return [
                    {
                        "chunk_id": "material-table",
                        "source": "EN1992-1-1 2004",
                        "score": 8.0,
                    }
                ]
            return []

        async def _fake_fetch_chunks(chunk_ids: list[str]):
            chunk_map = {
                "action": action_chunk,
                "material-table": material_chunk,
            }
            return [chunk_map[chunk_id] for chunk_id in chunk_ids]

        async def _fake_rerank(query: str, chunks: list[Chunk], top_n: int):
            return [(action_chunk, 0.91)]

        async def _fake_fetch_parent_chunks(chunks: list[Chunk]):
            return []

        retriever._vector_search = _fake_vector_search
        retriever._bm25_search = _fake_bm25_search
        retriever._fetch_chunks = _fake_fetch_chunks
        retriever._rerank = _fake_rerank
        retriever._fetch_parent_chunks = _fake_fetch_parent_chunks
        retriever._retrieve_guide_chunks = AsyncMock(return_value=[])
        retriever._retrieve_guide_example_chunks = AsyncMock(return_value=[])
        retriever._fetch_cross_ref_chunks = AsyncMock(return_value=[])

        result = await retriever.retrieve(
            [
                "concrete structural design Eurocode partial factors for actions and materials"
            ],
            original_query="请给出混凝土结构设计中相关作用荷载和材料的分项系数。",
        )

        assert seen_coverage_queries
        assert [chunk.chunk_id for chunk in result.chunks] == ["action"]
        assert [chunk.chunk_id for chunk in result.ref_chunks] == ["material-table"]

    @pytest.mark.asyncio
    async def test_coverage_supplement_does_not_restrict_missing_slot_to_main_source(
        self,
    ):
        retriever = HybridRetriever.__new__(HybridRetriever)
        retriever.config = ServerConfig(rerank_top_n=1, bm25_top_k=1, vector_top_k=1)
        exact_lookup_filters: list[list[dict]] = []
        bm25_filters: list[dict] = []

        action_chunk = _make_chunk(
            "action",
            "Table A1.2(C): Design values of actions STR/GEO. gamma_G 1.35 and gamma_Q 1.50.",
            source="EN 1990",
            element_type=ElementType.TABLE,
            object_type="table",
            object_label="Table A1.2",
        )
        material_chunk = _make_chunk(
            "material-table",
            "Table 2.1N: Partial factors for materials. gamma_C 1.5 gamma_S 1.15.",
            source="EN1992-1-1 2004",
            element_type=ElementType.TABLE,
            object_type="table",
            object_label="Table 2.1N",
            object_id="en1992-1-1-2004#table:2.1N",
        )

        async def _fake_vector_search(query: str, top_k: int, filters: dict):
            return [{"chunk_id": "action", "source": "EN 1990", "score": 0.9}]

        async def _fake_bm25_search(
            query: str,
            top_k: int,
            filters: dict,
            **kwargs,
        ):
            bm25_filters.append(filters)
            if filters.get("source") == "EN 1990":
                return []
            if "Table 2.1N" in query:
                return [
                    {
                        "chunk_id": "material-table",
                        "source": "EN1992-1-1 2004",
                        "score": 9.0,
                    }
                ]
            return []

        async def _fake_fetch_chunks(chunk_ids: list[str]):
            chunk_map = {
                "action": action_chunk,
                "material-table": material_chunk,
            }
            return [chunk_map[chunk_id] for chunk_id in chunk_ids]

        async def _fake_rerank(query: str, chunks: list[Chunk], top_n: int):
            return [(action_chunk, 0.91)]

        async def _fake_fetch_parent_chunks(chunks: list[Chunk]):
            return []

        async def _fake_exact_candidates(
            ref: str,
            category: str,
            filter_clauses: list[dict],
            *,
            size: int = 1,
        ):
            exact_lookup_filters.append(filter_clauses)
            return []

        retriever._vector_search = _fake_vector_search
        retriever._bm25_search = _fake_bm25_search
        retriever._fetch_chunks = _fake_fetch_chunks
        retriever._rerank = _fake_rerank
        retriever._fetch_parent_chunks = _fake_fetch_parent_chunks
        retriever._retrieve_guide_chunks = AsyncMock(return_value=[])
        retriever._retrieve_guide_example_chunks = AsyncMock(return_value=[])
        retriever._fetch_cross_ref_chunks = AsyncMock(return_value=[])
        retriever._exact_object_label_candidates = _fake_exact_candidates

        result = await retriever.retrieve(
            [
                "concrete structural design Eurocode partial factors for actions and materials"
            ],
            original_query="请给出混凝土结构设计中相关作用荷载和材料的分项系数。",
        )

        assert exact_lookup_filters
        assert all(
            {"term": {"source": "EN 1990"}} not in clauses
            for clauses in exact_lookup_filters
        )
        assert bm25_filters
        assert all(filters.get("source") != "EN 1990" for filters in bm25_filters)
        assert [chunk.chunk_id for chunk in result.ref_chunks] == ["material-table"]

    @pytest.mark.asyncio
    async def test_retrieve_ignores_generic_material_mentions_and_still_supplements(self):
        retriever = HybridRetriever.__new__(HybridRetriever)
        retriever.config = ServerConfig(rerank_top_n=2, bm25_top_k=2, vector_top_k=2)
        seen_coverage_queries: list[str] = []

        generic_material_chunk = _make_chunk(
            "generic-material",
            "The provisions of that code are applicable to all materials.",
            source="DG EN1992-1-1",
            section_path=["2.2", "General"],
        )
        action_chunk = _make_chunk(
            "action",
            "EN 1990 gives partial factors for actions and load combinations.",
            source="EN 1990",
        )
        material_chunk = _make_chunk(
            "material-table",
            "Table 2.1N: Partial factors for materials. gamma_C 1.5 gamma_S 1.15.",
            source="EN1992-1-1 2004",
            element_type=ElementType.TABLE,
            object_type="table",
            object_label="Table 2.1N",
            object_id="en1992-1-1-2004#table:2.1N",
        )

        async def _fake_vector_search(query: str, top_k: int, filters: dict):
            return [
                {"chunk_id": "generic-material", "source": "DG EN1992-1-1", "score": 0.95},
                {"chunk_id": "action", "source": "EN 1990", "score": 0.9},
            ]

        async def _fake_bm25_search(
            query: str,
            top_k: int,
            filters: dict,
            **kwargs,
        ):
            if "material partial factors" in query:
                seen_coverage_queries.append(query)
                return [
                    {
                        "chunk_id": "material-table",
                        "source": "EN1992-1-1 2004",
                        "score": 8.0,
                    }
                ]
            return []

        async def _fake_fetch_chunks(chunk_ids: list[str]):
            chunk_map = {
                "generic-material": generic_material_chunk,
                "action": action_chunk,
                "material-table": material_chunk,
            }
            return [chunk_map[chunk_id] for chunk_id in chunk_ids]

        async def _fake_rerank(query: str, chunks: list[Chunk], top_n: int):
            return [(generic_material_chunk, 0.93), (action_chunk, 0.91)]

        async def _fake_fetch_parent_chunks(chunks: list[Chunk]):
            return []

        retriever._vector_search = _fake_vector_search
        retriever._bm25_search = _fake_bm25_search
        retriever._fetch_chunks = _fake_fetch_chunks
        retriever._rerank = _fake_rerank
        retriever._fetch_parent_chunks = _fake_fetch_parent_chunks
        retriever._retrieve_guide_chunks = AsyncMock(return_value=[])
        retriever._retrieve_guide_example_chunks = AsyncMock(return_value=[])
        retriever._fetch_cross_ref_chunks = AsyncMock(return_value=[])

        result = await retriever.retrieve(
            [
                "concrete structural design Eurocode partial factors for actions and materials"
            ],
            original_query="请给出混凝土结构设计中相关作用荷载和材料的分项系数。",
        )

        assert seen_coverage_queries
        assert [chunk.chunk_id for chunk in result.chunks] == [
            "generic-material",
            "action",
        ]
        assert [chunk.chunk_id for chunk in result.ref_chunks] == ["material-table"]


class TestGroundednessInference:
    def test_empty_scores_are_not_grounded(self, retriever):
        assert retriever._infer_groundedness_from_scores([]) == "not_grounded"

    def test_low_top_score_is_not_grounded(self, retriever):
        assert retriever._infer_groundedness_from_scores([0.49]) == "not_grounded"

    def test_medium_top_score_is_partial(self, retriever):
        assert retriever._infer_groundedness_from_scores([0.5]) == "partial"

    def test_high_top_score_is_grounded(self, retriever):
        assert retriever._infer_groundedness_from_scores([0.85]) == "grounded"


class TestMetadataProbeBm25Fields:
    @pytest.mark.asyncio
    async def test_metadata_probe_uses_title_section_and_clause_fields(self):
        retriever = HybridRetriever.__new__(HybridRetriever)
        retriever.config = ServerConfig(bm25_top_k=2, es_index="chunks")
        seen_fields: list[list[str] | None] = []

        async def _fake_clause_probe(clause: str, filters: dict):
            assert clause == "6.1"
            assert filters == {"source": "EN 1992-1-1"}
            return []

        async def _fake_bm25_search(query: str, top_k: int, filters: dict, **kwargs):
            seen_fields.append(kwargs.get("fields"))
            return []

        retriever._run_clause_metadata_probe = _fake_clause_probe
        retriever._bm25_search = _fake_bm25_search

        await retriever._run_metadata_probe(
            queries=["basic assumptions for section design"],
            original_query="欧标的截面计算的基本假设前提是什么",
            filters={"source": "EN 1992-1-1"},
            target_hint={
                "document": "EN 1992-1-1",
                "clause": "6.1",
                "object": "basic assumptions",
            },
        )

        assert seen_fields
        first_fields = seen_fields[0]
        assert "source^6" in first_fields
        assert "source_title.text^4" in first_fields
        assert "section_path.text^7" in first_fields
        assert "clause_ids.text^8" in first_fields
        assert "object_aliases.text^5" in first_fields

    @pytest.mark.asyncio
    async def test_clause_metadata_probe_uses_keyword_fields(self):
        retriever = HybridRetriever.__new__(HybridRetriever)
        retriever.config = ServerConfig(bm25_top_k=2, es_index="chunks")
        seen_bodies: list[dict] = []

        class _FakeEs:
            async def search(self, index: str, body: dict):
                assert index == "chunks"
                seen_bodies.append(body)
                return {"hits": {"hits": []}}

        async def _fake_get_es():
            return _FakeEs()

        retriever._get_es = _fake_get_es

        await retriever._run_clause_metadata_probe("4.2", {})

        assert any(
            "should" in body["query"]["bool"]
            and any(
                "term" in clause and clause["term"].get("clause_ids") == "4.2"
                for clause in body["query"]["bool"]["should"]
            )
            for body in seen_bodies
        )

    @pytest.mark.asyncio
    async def test_retrieve_runs_metadata_probe_from_structured_hint(self):
        retriever = HybridRetriever.__new__(HybridRetriever)
        retriever.config = ServerConfig(rerank_top_n=2, vector_top_k=1, bm25_top_k=1)
        metadata_probe_calls: list[dict[str, object]] = []

        async def _fake_metadata_probe(**kwargs):
            metadata_probe_calls.append(kwargs)
            return [{"chunk_id": "probe-hit", "source": "EN 1992-1-1", "score": 0.96}]

        async def _fake_vector_search(query: str, top_k: int, filters: dict):
            return []

        async def _fake_bm25_search(query: str, top_k: int, filters: dict, **kwargs):
            return []

        async def _fake_fetch_chunks(chunk_ids: list[str]):
            return [
                _make_chunk(
                    "probe-hit",
                    "Basic assumptions for section design are given in 6.1.",
                    source="EN 1992-1-1",
                    source_title="Bending with or without axial force",
                    section_path=["6.1"],
                    clause_ids=["6.1"],
                )
            ]

        async def _fake_rerank(query: str, chunks: list[Chunk], top_n: int):
            return [(chunks[0], 0.9)]

        async def _fake_fetch_parent_chunks(chunks: list[Chunk]):
            return []

        async def _fake_fetch_cross_ref_chunks(*args, **kwargs):
            return []

        retriever._run_metadata_probe = _fake_metadata_probe
        retriever._vector_search = _fake_vector_search
        retriever._bm25_search = _fake_bm25_search
        retriever._fetch_chunks = _fake_fetch_chunks
        retriever._rerank = _fake_rerank
        retriever._fetch_parent_chunks = _fake_fetch_parent_chunks
        retriever._fetch_cross_ref_chunks = _fake_fetch_cross_ref_chunks

        result = await retriever.retrieve(
            queries=["basic assumptions for section design"],
            original_query="欧标的截面计算的基本假设前提是什么",
            filters={},
            intent_label="assumption",
            target_hint={
                "document": "EN 1992-1-1",
                "clause": "6.1",
                "object": "basic assumptions",
            },
        )

        assert metadata_probe_calls
        assert [chunk.chunk_id for chunk in result.chunks] == ["probe-hit"]
        assert result.groundedness == "grounded"
