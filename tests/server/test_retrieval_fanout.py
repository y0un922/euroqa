"""Regression tests for retrieval query fan-out."""
from __future__ import annotations

import asyncio
import time

import pytest

from server.config import ServerConfig
from server.core.retrieval import HybridRetriever
from server.models.schemas import Chunk, ChunkMetadata, ElementType


SINGLE_SEARCH_DELAY_SECONDS = 0.2


def _make_chunk(chunk_id: str) -> Chunk:
    return Chunk(
        chunk_id=chunk_id,
        content=f"content {chunk_id}",
        embedding_text=f"content {chunk_id}",
        metadata=ChunkMetadata(
            source="EN 1990",
            source_title="Basis",
            section_path=["2.3"],
            page_numbers=[1],
            page_file_index=[0],
            clause_ids=[],
            element_type=ElementType.TEXT,
        ),
    )


def _minimal_retriever() -> HybridRetriever:
    retriever = HybridRetriever.__new__(HybridRetriever)
    retriever.config = ServerConfig(
        vector_top_k=3,
        bm25_top_k=3,
        rerank_top_n=20,
    )
    return retriever


async def _patch_retrieve_tail(retriever: HybridRetriever) -> None:
    async def _fake_fetch_chunks(chunk_ids: list[str]):
        return [_make_chunk(chunk_id) for chunk_id in chunk_ids]

    async def _fake_rerank(query: str, chunks: list[Chunk], top_n: int):
        return [(chunk, 0.9) for chunk in chunks[:top_n]]

    async def _fake_fetch_parent_chunks(chunks: list[Chunk]):
        return []

    async def _fake_fetch_cross_ref_chunks(*args, **kwargs):
        return []

    async def _fake_fetch_object_chunks_by_object_ids(*args, **kwargs):
        return []

    async def _fake_retrieve_guide_chunks(*args, **kwargs):
        return []

    async def _fake_retrieve_guide_example_chunks(*args, **kwargs):
        return []

    retriever._fetch_chunks = _fake_fetch_chunks
    retriever._rerank = _fake_rerank
    retriever._fetch_parent_chunks = _fake_fetch_parent_chunks
    retriever._fetch_cross_ref_chunks = _fake_fetch_cross_ref_chunks
    retriever._fetch_object_chunks_by_object_ids = _fake_fetch_object_chunks_by_object_ids
    retriever._retrieve_guide_chunks = _fake_retrieve_guide_chunks
    retriever._retrieve_guide_example_chunks = _fake_retrieve_guide_example_chunks


@pytest.mark.asyncio
async def test_retrieve_runs_expanded_queries_concurrently():
    retriever = _minimal_retriever()
    await _patch_retrieve_tail(retriever)

    async def _fake_vector_search(query: str, top_k: int, filters: dict):
        await asyncio.sleep(SINGLE_SEARCH_DELAY_SECONDS)
        return [{"chunk_id": f"{query}-vec", "source": "EN 1990", "score": 0.9}]

    async def _fake_bm25_search(query: str, top_k: int, filters: dict, **kwargs):
        await asyncio.sleep(SINGLE_SEARCH_DELAY_SECONDS)
        return [{"chunk_id": f"{query}-bm25", "source": "EN 1990", "score": 5.0}]

    retriever._vector_search = _fake_vector_search
    retriever._bm25_search = _fake_bm25_search

    started_at = time.perf_counter()
    result = await retriever.retrieve(["q1", "q2", "q3"])
    elapsed = time.perf_counter() - started_at

    assert elapsed <= SINGLE_SEARCH_DELAY_SECONDS * 1.5
    assert {chunk.chunk_id for chunk in result.chunks} == {
        "q1-vec",
        "q1-bm25",
        "q2-vec",
        "q2-bm25",
        "q3-vec",
        "q3-bm25",
    }


@pytest.mark.asyncio
async def test_retrieve_keeps_other_query_results_when_one_query_fails():
    retriever = _minimal_retriever()
    await _patch_retrieve_tail(retriever)

    async def _fake_vector_search(query: str, top_k: int, filters: dict):
        await asyncio.sleep(0)
        if query == "bad":
            raise RuntimeError("vector unavailable")
        return [{"chunk_id": f"{query}-vec", "source": "EN 1990", "score": 0.9}]

    async def _fake_bm25_search(query: str, top_k: int, filters: dict, **kwargs):
        await asyncio.sleep(0)
        if query == "bad":
            raise RuntimeError("bm25 unavailable")
        return [{"chunk_id": f"{query}-bm25", "source": "EN 1990", "score": 5.0}]

    retriever._vector_search = _fake_vector_search
    retriever._bm25_search = _fake_bm25_search

    result = await retriever.retrieve(["good", "bad", "also-good"])

    assert {chunk.chunk_id for chunk in result.chunks} == {
        "good-vec",
        "good-bm25",
        "also-good-vec",
        "also-good-bm25",
    }
