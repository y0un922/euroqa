"""Retrieval result data contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from server.models.schemas import Chunk


@dataclass
class RetrievalResult:
    """检索结果，包含最终 chunk、父 chunk、交叉引用 chunk 和重排序分数。"""

    chunks: list[Chunk]
    parent_chunks: list[Chunk]
    scores: list[float]
    guide_chunks: list[Chunk] = field(default_factory=list)
    guide_example_chunks: list[Chunk] = field(default_factory=list)
    ref_chunks: list[Chunk] = field(default_factory=list)
    groundedness: str = "not_grounded"
    resolved_refs: list[str] = field(default_factory=list)
    unresolved_refs: list[str] = field(default_factory=list)
    # 每个输入 query 的向量+BM25 去重候选数（融合前），用于零命中判定
    per_query_candidate_counts: dict[str, int] = field(default_factory=dict)


def _result_entries(results: list[dict]) -> list[dict[str, Any]]:
    """Serialize retrieval result dictionaries for spot-check logs."""
    entries: list[dict[str, Any]] = []
    for result in results:
        entries.append(
            {
                "chunk_id": result.get("chunk_id"),
                "source": result.get("source"),
                "score": result.get("score"),
            }
        )
    return entries
