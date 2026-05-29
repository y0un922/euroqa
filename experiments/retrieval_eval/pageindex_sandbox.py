"""Vectorless PageIndex-style retrieval sandbox.

This module ports the core idea from ``Euro_QA_pageindex`` into the existing
retrieval-eval sandbox without importing or modifying production retrieval code:

document shortlist -> structure-tree ranking -> page/line content extraction ->
Chunk-compatible evidence.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from server.models.schemas import Chunk, ChunkMetadata

from experiments.retrieval_eval.pageindex_sandbox_utils import (
    attach_ranges,
    collect_clause_ids,
    extract_object_label,
    extract_references_from_chunks,
    flatten_structure,
    infer_element_type,
    node_pages,
    node_span,
    node_trace,
    normalize_ref,
    parse_page_range,
    ref_matches_title,
    resolved_requested_refs,
    score_node,
    shortlist_documents,
    tokenize,
)


@dataclass
class PageIndexSandboxResult:
    """RetrievalResult-compatible payload for existing eval metrics."""

    chunks: list[Chunk]
    parent_chunks: list[Chunk]
    scores: list[float]
    ref_chunks: list[Chunk] = field(default_factory=list)
    answer_mode: str = "open"
    groundedness: str = "open"
    resolved_refs: list[str] = field(default_factory=list)
    unresolved_refs: list[str] = field(default_factory=list)
    shortlist_strategy: str = ""
    selection_strategy: str = ""
    insufficient_evidence: bool = False


@dataclass
class PageIndexSandboxTrace:
    """JSON trace for one vectorless retrieval call."""

    queries: list[str]
    source_filter: str | None
    shortlisted_doc_ids: list[str]
    shortlist_strategy: str
    ranked_nodes: list[dict[str, Any]]
    selected_nodes: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "queries": self.queries,
            "source_filter": self.source_filter,
            "shortlisted_doc_ids": self.shortlisted_doc_ids,
            "shortlist_strategy": self.shortlist_strategy,
            "ranked_nodes": self.ranked_nodes,
            "selected_nodes": self.selected_nodes,
        }


class PageIndexWorkspace:
    """Read-only loader for a PageIndex workspace directory."""

    def __init__(self, workspace: str | Path) -> None:
        self.workspace = Path(workspace).expanduser()
        self.documents = self._load_documents()

    def get_document(self, doc_id: str) -> dict[str, Any]:
        return self.documents.get(doc_id, {})

    def get_structure(self, doc_id: str) -> list[dict[str, Any]]:
        doc = self.get_document(doc_id)
        structure = doc.get("structure") or []
        return structure if isinstance(structure, list) else []

    def get_line_content(self, doc_id: str, pages: str) -> list[dict[str, Any]]:
        page_nums = parse_page_range(pages)
        if not page_nums:
            return []
        start, end = min(page_nums), max(page_nums)
        results: list[dict[str, Any]] = []
        for node in flatten_structure(self.get_structure(doc_id)):
            line_num = node.get("line_num")
            if isinstance(line_num, int) and start <= line_num <= end:
                text = str(node.get("text") or "").strip()
                if text:
                    results.append({"page": line_num, "content": text})
        return results

    def _load_documents(self) -> dict[str, dict[str, Any]]:
        meta_path = self.workspace / "_meta.json"
        if not meta_path.is_file():
            raise FileNotFoundError(f"PageIndex workspace meta not found: {meta_path}")
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        documents: dict[str, dict[str, Any]] = {}
        for doc_id, entry in meta.items():
            doc_path = self.workspace / f"{doc_id}.json"
            if doc_path.is_file():
                doc = json.loads(doc_path.read_text(encoding="utf-8"))
            else:
                doc = dict(entry)
            doc.setdefault("id", doc_id)
            documents[doc_id] = doc
        return documents


class PageIndexSandboxRetriever:
    """Deterministic vectorless retriever adapted from the PageIndex project."""

    def __init__(
        self,
        workspace: str | Path,
        *,
        max_docs: int = 3,
        top_k: int = 10,
    ) -> None:
        self.workspace = PageIndexWorkspace(workspace)
        self.max_docs = max_docs
        self.top_k = top_k

    async def retrieve_with_trace(
        self,
        *,
        queries: list[str],
        original_query: str | None = None,
        filters: dict | None = None,
        requested_objects: list[str] | None = None,
        **_: Any,
    ) -> tuple[PageIndexSandboxResult, PageIndexSandboxTrace]:
        filters = filters or {}
        requested_objects = requested_objects or []
        source_filter = filters.get("source")
        shortlist = shortlist_documents(
            meta=self.workspace.documents,
            source_filter=source_filter,
            expanded_queries=queries,
            original_query=original_query,
            max_docs=self.max_docs,
        )
        ranked = self._rank_nodes(
            shortlist.doc_ids,
            queries=queries,
            original_query=original_query,
            requested_objects=requested_objects,
        )
        selected = ranked[: self.top_k]
        chunks = [
            self._build_chunk(item["doc_id"], item["node"], item["score"])
            for item in selected
        ]
        chunks = [chunk for chunk in chunks if chunk is not None]
        ref_chunks, content_refs = self._build_ref_chunks(
            shortlist.doc_ids,
            chunks=chunks,
            selected=selected,
            requested_objects=requested_objects,
        )
        resolved_refs = resolved_requested_refs(requested_objects, selected)
        for ref in content_refs:
            if ref not in resolved_refs:
                resolved_refs.append(ref)
        unresolved_refs = [
            ref for ref in requested_objects if ref and ref not in set(resolved_refs)
        ]
        result = PageIndexSandboxResult(
            chunks=chunks,
            parent_chunks=[],
            scores=[item["score"] for item in selected[: len(chunks)]],
            ref_chunks=ref_chunks,
            answer_mode="exact" if requested_objects else "open",
            groundedness="grounded" if chunks else "open",
            resolved_refs=resolved_refs,
            unresolved_refs=unresolved_refs,
            shortlist_strategy=shortlist.strategy,
            selection_strategy="requested_object_probe" if resolved_refs else "structure_keyword_rank",
        )
        trace = PageIndexSandboxTrace(
            queries=list(queries),
            source_filter=source_filter,
            shortlisted_doc_ids=shortlist.doc_ids,
            shortlist_strategy=shortlist.strategy,
            ranked_nodes=[node_trace(item) for item in ranked[:30]],
            selected_nodes=[node_trace(item) for item in selected],
        )
        return result, trace

    async def close(self) -> None:
        return None

    def _rank_nodes(
        self,
        doc_ids: list[str],
        *,
        queries: list[str],
        original_query: str | None,
        requested_objects: list[str],
    ) -> list[dict[str, Any]]:
        query_text = " ".join([*queries, original_query or ""])
        query_tokens = tokenize(query_text)
        requested = [normalize_ref(ref) for ref in requested_objects if ref]
        ranked: list[dict[str, Any]] = []
        for doc_id in doc_ids:
            nodes = attach_ranges(flatten_structure(self.workspace.get_structure(doc_id)))
            for node in nodes:
                score, reasons = score_node(node, query_tokens, requested)
                if score <= 0:
                    continue
                ranked.append(
                    {
                        "doc_id": doc_id,
                        "node": node,
                        "score": score,
                        "reasons": reasons,
                    }
                )
        ranked.sort(
            key=lambda item: (
                item["score"],
                -node_span(item["node"]),
                str(item["node"].get("title") or ""),
            ),
            reverse=True,
        )
        return ranked

    def _build_chunk(self, doc_id: str, node: dict[str, Any], score: float) -> Chunk | None:
        doc = self.workspace.get_document(doc_id)
        pages = node_pages(node)
        page_items = self.workspace.get_line_content(doc_id, pages)
        content = "\n\n".join(
            str(item.get("content") or "").strip()
            for item in page_items
            if str(item.get("content") or "").strip()
        )
        if not content:
            content = str(node.get("text") or "").strip()
        if not content:
            return None
        title = str(node.get("title") or "")
        object_label = extract_object_label(title)
        metadata = ChunkMetadata(
            source=str(doc.get("doc_name") or doc_id),
            document_id=str(doc.get("id") or doc_id),
            source_title=str(doc.get("doc_name") or doc_id),
            display_title=str(doc.get("doc_name") or doc_id),
            section_path=list(node.get("path") or [title]),
            page_numbers=parse_page_range(pages),
            page_file_index=parse_page_range(pages),
            clause_ids=collect_clause_ids(node),
            element_type=infer_element_type(object_label, content),
            object_label=object_label,
            object_aliases=[object_label] if object_label else [],
        )
        return Chunk(
            chunk_id=f"pageindex:{doc_id}:l{node.get('range_start') or node.get('line_num')}:s{score:.3f}",
            content=content,
            embedding_text=content[:500],
            metadata=metadata,
        )

    def _build_ref_chunks(
        self,
        doc_ids: list[str],
        *,
        chunks: list[Chunk],
        selected: list[dict[str, Any]],
        requested_objects: list[str],
    ) -> tuple[list[Chunk], list[str]]:
        refs = extract_references_from_chunks(chunks)
        for ref in requested_objects:
            if ref and ref not in refs:
                refs.append(ref)
        if not refs:
            return [], []

        selected_keys = {
            (item["doc_id"], item["node"].get("range_start") or item["node"].get("line_num"))
            for item in selected
        }
        ref_chunks: list[Chunk] = []
        resolved: list[str] = []
        seen_chunks: set[str] = set()
        for ref in refs[:12]:
            normalized_ref = normalize_ref(ref)
            for doc_id in doc_ids:
                for node in attach_ranges(flatten_structure(self.workspace.get_structure(doc_id))):
                    node_key = (doc_id, node.get("range_start") or node.get("line_num"))
                    if node_key in selected_keys:
                        continue
                    title = normalize_ref(str(node.get("title") or ""))
                    if not ref_matches_title(normalized_ref, title):
                        continue
                    chunk = self._build_chunk(doc_id, node, 1.0)
                    if chunk is None or chunk.chunk_id in seen_chunks:
                        continue
                    seen_chunks.add(chunk.chunk_id)
                    ref_chunks.append(chunk)
                    if ref not in resolved:
                        resolved.append(ref)
                    break
        return ref_chunks, resolved
