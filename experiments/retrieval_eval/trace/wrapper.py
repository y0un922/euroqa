"""Tracing wrapper around HybridRetriever.

This module intentionally lives outside server/core and depends on selected
HybridRetriever internals. It is for single-threaded evaluation runs only.
"""

from __future__ import annotations

from typing import Any

from server.config import ServerConfig
from server.core.retrieval import HybridRetriever, RetrievalResult
from server.models.schemas import Chunk

from experiments.retrieval_eval.trace.schema import RetrievalTrace


class TracingHybridRetriever(HybridRetriever):
    """HybridRetriever subclass that records staged retrieval snapshots."""

    def __init__(
        self,
        config: ServerConfig,
        *,
        disable_rerank: bool = False,
        disable_cap: bool = False,
        rerank_fill_from_candidates: bool = False,
        rerank_fill_rerank_top_n: int = 5,
        multi_query_max_rerank: bool = False,
        max_per_source_override: int | None = None,
    ) -> None:
        super().__init__(config)
        self._trace: RetrievalTrace | None = None
        self._trace_phase = "idle"
        self.disable_rerank = disable_rerank
        self.disable_cap = disable_cap
        self.rerank_fill_from_candidates = rerank_fill_from_candidates
        self.rerank_fill_rerank_top_n = rerank_fill_rerank_top_n
        self.multi_query_max_rerank = multi_query_max_rerank
        self.max_per_source_override = max_per_source_override
        self._force_rerank_query: str | None = None
        self._force_rerank_queries: list[str] = []

    async def retrieve_with_trace(
        self,
        **kwargs: Any,
    ) -> tuple[RetrievalResult, RetrievalTrace]:
        """Run retrieve() and return the normal result plus stage trace."""
        self._trace = RetrievalTrace(queries=list(kwargs.get("queries") or []))
        original_rrf = HybridRetriever._rrf_fuse_results

        def hooked_rrf(result_groups: list[list[dict]], **kw: Any) -> list[dict]:
            fused = original_rrf(result_groups, **kw)
            if self._trace is not None and self._trace_phase == "main":
                self._trace.rrf_fused = [_copy_hit(hit) for hit in fused]
            return fused

        self._rrf_fuse_results = hooked_rrf  # type: ignore[method-assign]
        self._trace_phase = "main"
        try:
            result = await super().retrieve(**kwargs)
            trace = self._trace
            if trace is None:
                raise RuntimeError("trace unexpectedly missing after retrieve")
            return result, trace
        finally:
            if "_rrf_fuse_results" in self.__dict__:
                del self.__dict__["_rrf_fuse_results"]
            self._trace = None
            self._trace_phase = "idle"

    async def _run_metadata_probe(
        self,
        queries: list[str],
        original_query: str | None,
        filters: dict,
        target_hint: Any = None,
        intent_label: str | None = None,
    ) -> list[dict]:
        hits = await super()._run_metadata_probe(
            queries=queries,
            original_query=original_query,
            filters=filters,
            target_hint=target_hint,
            intent_label=intent_label,
        )
        if self._trace is not None and self._trace_phase == "main":
            self._trace.metadata_probe = [_copy_hit(hit) for hit in hits]
        return hits

    async def _vector_search(
        self,
        query: str,
        top_k: int,
        filters: dict,
    ) -> list[dict]:
        hits = await super()._vector_search(query, top_k, filters)
        if self._trace is not None and self._trace_phase == "main":
            self._trace.dense_hits.append([_copy_hit(hit) for hit in hits])
        return hits

    async def _bm25_search(
        self,
        query: str,
        top_k: int,
        filters: dict,
        fields: list[str] | None = None,
        preferred_element_type: str | None = None,
    ) -> list[dict]:
        hits = await super()._bm25_search(
            query,
            top_k,
            filters,
            fields=fields,
            preferred_element_type=preferred_element_type,
        )
        if self._trace is not None and self._trace_phase == "main":
            self._trace.bm25_hits.append([_copy_hit(hit) for hit in hits])
        return hits

    def _cross_doc_aggregate(
        self,
        results: list[dict],
        max_per_source: int = 5,
        filters: dict | None = None,
    ) -> list[dict]:
        if self.disable_cap:
            aggregated = list(results)
        else:
            effective_max_per_source = self.max_per_source_override or max_per_source
            aggregated = super()._cross_doc_aggregate(
                results,
                max_per_source=effective_max_per_source,
                filters=filters,
            )
        if self._trace is not None and self._trace_phase == "main":
            self._trace.after_cap = [_copy_hit(hit) for hit in aggregated]
        return aggregated

    async def _rerank(
        self,
        query: str,
        chunks: list[Chunk],
        top_n: int,
    ) -> list[tuple[Chunk, float]]:
        actual_queries = self._actual_rerank_queries(query)
        actual_query = actual_queries[0]
        if self._trace is not None and self._trace_phase == "main":
            self._trace.rerank_query_actual = actual_query
            self._trace.rerank_queries_actual = list(actual_queries)

        if self.disable_rerank:
            ranked = [(chunk, 0.0) for chunk in chunks[:top_n]]
            if self._trace is not None and self._trace_phase == "main":
                self._trace.reranked = [
                    _chunk_hit(chunk, rerank_score=score)
                    for chunk, score in ranked
                ]
            return ranked

        if self.multi_query_max_rerank:
            ranked = await self._multi_query_max_rerank(actual_queries, chunks, top_n)
        elif self.rerank_fill_from_candidates:
            ranked = await self._rerank_then_fill(actual_query, chunks, top_n)
        else:
            ranked = await super()._rerank(actual_query, chunks, top_n)
        if self._trace is not None and self._trace_phase == "main":
            self._trace.reranked = [
                _chunk_hit(chunk, rerank_score=score)
                for chunk, score in ranked
            ]
        return ranked

    async def _rerank_then_fill(
        self,
        query: str,
        chunks: list[Chunk],
        top_n: int,
    ) -> list[tuple[Chunk, float]]:
        rerank_top_n = min(max(self.rerank_fill_rerank_top_n, 0), top_n)
        reranked = await super()._rerank(query, chunks, rerank_top_n)
        selected_ids = {chunk.chunk_id for chunk, _ in reranked}
        filled: list[tuple[Chunk, float]] = list(reranked)
        fill_added: list[dict[str, Any]] = []

        for chunk in chunks:
            if len(filled) >= top_n:
                break
            if chunk.chunk_id in selected_ids:
                continue
            selected_ids.add(chunk.chunk_id)
            filled.append((chunk, 0.0))
            fill_added.append(_chunk_hit(chunk, rerank_score=0.0))

        if self._trace is not None and self._trace_phase == "main":
            self._trace.rerank_fill_added = fill_added
        return filled

    def _actual_rerank_queries(self, fallback_query: str) -> list[str]:
        queries = [
            query.strip()
            for query in self._force_rerank_queries
            if (query or "").strip()
        ]
        if queries:
            return queries
        if self._force_rerank_query and self._force_rerank_query.strip():
            return [self._force_rerank_query.strip()]
        return [fallback_query]

    async def _multi_query_max_rerank(
        self,
        queries: list[str],
        chunks: list[Chunk],
        top_n: int,
    ) -> list[tuple[Chunk, float]]:
        if not chunks:
            return []

        best_scores: dict[str, float] = {}
        for query in queries:
            ranked = await super()._rerank(query, chunks, len(chunks))
            for chunk, score in ranked:
                previous = best_scores.get(chunk.chunk_id)
                if previous is None or score > previous:
                    best_scores[chunk.chunk_id] = float(score)

        ranked_all = sorted(
            enumerate(chunks),
            key=lambda item: (best_scores.get(item[1].chunk_id, float("-inf")), -item[0]),
            reverse=True,
        )
        return [
            (chunk, best_scores.get(chunk.chunk_id, 0.0))
            for _, chunk in ranked_all[:top_n]
        ]

    async def _fetch_object_chunks_by_object_ids(
        self,
        object_ids: set[str],
        existing_ids: set[str],
        filters: dict | None = None,
        max_refs: int = 5,
    ) -> list[Chunk]:
        chunks = await super()._fetch_object_chunks_by_object_ids(
            object_ids,
            existing_ids,
            filters=filters,
            max_refs=max_refs,
        )
        if self._trace is not None and self._trace_phase == "main":
            self._trace.object_id_fetched = [chunk.chunk_id for chunk in chunks]
        return chunks

    async def _fetch_cross_ref_chunks(
        self,
        refs: set[str],
        existing_ids: set[str],
        filters: dict | None = None,
        max_refs: int = 5,
    ) -> list[Chunk]:
        chunks = await super()._fetch_cross_ref_chunks(
            refs,
            existing_ids,
            filters=filters,
            max_refs=max_refs,
        )
        if self._trace is not None and self._trace_phase == "main":
            self._trace.cross_ref_added = [chunk.chunk_id for chunk in chunks]
        return chunks


def _copy_hit(hit: dict) -> dict[str, Any]:
    return {
        key: _jsonable(value)
        for key, value in hit.items()
        if key
        in {"chunk_id", "source", "score", "element_type", "clause_ids", "section_path"}
    }


def _chunk_hit(chunk: Chunk, rerank_score: float | None = None) -> dict[str, Any]:
    meta = chunk.metadata
    payload: dict[str, Any] = {
        "chunk_id": chunk.chunk_id,
        "source": meta.source,
        "clause_ids": list(meta.clause_ids),
        "section_path": list(meta.section_path),
        "element_type": getattr(meta.element_type, "value", meta.element_type),
        "object_label": meta.object_label,
    }
    if rerank_score is not None:
        payload["score"] = float(rerank_score)
        payload["rerank_score"] = float(rerank_score)
    return payload


def _jsonable(value: Any) -> Any:
    if isinstance(value, int | float | str | bool) or value is None:
        return value
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    return str(value)
