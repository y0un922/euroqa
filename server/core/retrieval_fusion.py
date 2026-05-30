"""Pure retrieval result fusion helpers."""

from __future__ import annotations

from typing import Any

_RRF_K = 60


def _merge_results(
    vec_results: list[dict],
    bm25_results: list[dict],
) -> list[dict]:
    """合并向量检索和 BM25 结果并去重，使用 RRF 保留两路排序信号。"""
    return _rrf_fuse_results([vec_results, bm25_results])


def _rrf_fuse_results(
    result_groups: list[list[dict]],
    *,
    rrf_k: int = _RRF_K,
) -> list[dict]:
    """Fuse ranked retrieval groups with Reciprocal Rank Fusion."""
    fused: dict[str, dict[str, Any]] = {}
    first_order = 0

    for group in result_groups:
        for rank, result in enumerate(group, start=1):
            chunk_id = result.get("chunk_id")
            if not chunk_id:
                continue
            if chunk_id not in fused:
                fused[chunk_id] = {
                    **result,
                    "score": 0.0,
                    "_first_order": first_order,
                }
                first_order += 1
            fused[chunk_id]["score"] += 1.0 / (rrf_k + rank)

    ranked = sorted(
        fused.values(),
        key=lambda item: (item["score"], -item["_first_order"]),
        reverse=True,
    )
    return [
        {key: value for key, value in item.items() if not key.startswith("_")}
        for item in ranked
    ]


def _cross_doc_aggregate(
    results: list[dict],
    max_per_source: int = 5,
    filters: dict | None = None,
) -> list[dict]:
    """跨文档聚合：限制每个来源文档的最大 chunk 数量，确保结果多样性。"""
    filters = filters or {}
    unique_sources = {result.get("source", "") for result in results}
    if "source" in filters or len(unique_sources) <= 1:
        return results

    source_counts: dict[str, int] = {}
    aggregated: list[dict] = []

    for result in results:
        src = result.get("source", "")
        count = source_counts.get(src, 0)
        if count < max_per_source:
            aggregated.append(result)
            source_counts[src] = count + 1

    return aggregated


def _append_unique_results(
    primary_results: list[dict],
    supplemental_results: list[dict],
) -> list[dict]:
    """Append supplemental candidates without disturbing primary ordering."""
    seen = {result["chunk_id"] for result in primary_results}
    merged = list(primary_results)
    for result in supplemental_results:
        chunk_id = result["chunk_id"]
        if chunk_id not in seen:
            seen.add(chunk_id)
            merged.append(result)
    return merged


def _infer_groundedness_from_scores(scores: list[float]) -> str:
    """Infer evidence groundedness from reranker scores."""
    if not scores:
        return "not_grounded"
    top = scores[0]
    if top >= 0.85:
        return "grounded"
    if top >= 0.5:
        return "partial"
    return "not_grounded"
