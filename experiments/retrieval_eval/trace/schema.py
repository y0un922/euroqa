"""Trace schema for staged retrieval diagnostics."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class RetrievalTrace:
    """Snapshot of one retrieval call across the main ranking stages."""

    queries: list[str]
    dense_hits: list[list[dict[str, Any]]] = field(default_factory=list)
    bm25_hits: list[list[dict[str, Any]]] = field(default_factory=list)
    metadata_probe: list[dict[str, Any]] = field(default_factory=list)
    rrf_fused: list[dict[str, Any]] = field(default_factory=list)
    after_cap: list[dict[str, Any]] = field(default_factory=list)
    reranked: list[dict[str, Any]] = field(default_factory=list)
    rerank_fill_added: list[dict[str, Any]] = field(default_factory=list)
    rerank_query_actual: str = ""
    rerank_queries_actual: list[str] = field(default_factory=list)
    cross_ref_added: list[str] = field(default_factory=list)
    object_id_fetched: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable dict."""
        return asdict(self)
