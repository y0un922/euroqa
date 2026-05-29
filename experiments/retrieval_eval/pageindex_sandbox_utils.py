"""Helper functions for the PageIndex vectorless retrieval sandbox."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from server.models.schemas import Chunk, ElementType


@dataclass
class Shortlist:
    """Document shortlist result."""

    doc_ids: list[str]
    strategy: str
    scores: dict[str, float]


def shortlist_documents(
    *,
    meta: dict[str, dict[str, Any]],
    source_filter: str | None,
    expanded_queries: list[str],
    original_query: str | None,
    max_docs: int,
) -> Shortlist:
    """Select candidate PageIndex documents from metadata and query text."""
    if source_filter:
        candidates = _metadata_candidates(meta, source_filter)
        if candidates:
            return _build_shortlist(candidates, "metadata", max_docs)
    query_text = " ".join([*expanded_queries, original_query or ""])
    query_words = tokenize(query_text)
    candidates: dict[str, float] = {}
    for doc_id, entry in meta.items():
        doc_words = tokenize(f"{entry.get('doc_name', '')} {entry.get('doc_description', '')}")
        score = float(len(query_words & doc_words))
        normalized_name = normalize_doc_text(str(entry.get("doc_name") or ""))
        score += sum(2.0 for token in query_words if token in normalized_name)
        candidates[doc_id] = score if score > 0 else 0.1
    return _build_shortlist(candidates, "description", max_docs)


def flatten_structure(
    structure: list[dict[str, Any]] | dict[str, Any],
    parents: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Flatten nested PageIndex structure nodes while preserving title path."""
    items: list[dict[str, Any]] = []
    nodes = structure if isinstance(structure, list) else [structure]
    parent_path = parents or []
    for node in nodes or []:
        if not isinstance(node, dict):
            continue
        title = str(node.get("title") or "").strip()
        path = [*parent_path, title] if title else list(parent_path)
        item = dict(node)
        item["path"] = path
        items.append(item)
        items.extend(flatten_structure(node.get("nodes") or [], path))
    return items


def attach_ranges(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Attach markdown line ranges to flattened PageIndex nodes."""
    line_nodes = [node for node in nodes if isinstance(node.get("line_num"), int)]
    line_nodes.sort(key=lambda node: int(node["line_num"]))
    for index, node in enumerate(line_nodes):
        start = int(node["line_num"])
        end = int(line_nodes[index + 1]["line_num"]) - 1 if index + 1 < len(line_nodes) else start
        node["range_start"] = start
        node["range_end"] = max(start, end)
    return line_nodes


def score_node(
    node: dict[str, Any],
    query_tokens: set[str],
    requested_refs: list[str],
) -> tuple[float, list[str]]:
    """Score one structure node by query overlap and explicit references."""
    title = str(node.get("title") or "")
    haystack = f"{title} {node.get('summary') or ''} {str(node.get('text') or '')[:800]}"
    node_tokens = tokenize(haystack)
    score = float(len(query_tokens & node_tokens))
    reasons: list[str] = ["token_overlap"] if score else []
    normalized_title = normalize_ref(title)
    for ref in requested_refs:
        if ref and ref_matches_title(ref, normalized_title):
            score += 100.0
            reasons.append(f"requested_ref:{ref}")
    clause = leading_clause(title)
    if clause and clause in query_tokens:
        score += 25.0
        reasons.append(f"clause:{clause}")
    if extract_object_label(title):
        score += 2.0
    return score, reasons


def ref_matches_title(requested: str, title: str) -> bool:
    """Return whether a normalized requested reference matches a node title."""
    if requested == title:
        return True
    requested_clause = leading_clause(requested)
    title_clause = leading_clause(title)
    if requested_clause and requested_clause == title_clause:
        return True
    return requested.replace(" ", "") in title.replace(" ", "")


def resolved_requested_refs(
    requested_objects: list[str],
    selected: list[dict[str, Any]],
) -> list[str]:
    """Return requested objects resolved by selected structure nodes."""
    resolved: list[str] = []
    titles = [normalize_ref(str(item["node"].get("title") or "")) for item in selected]
    for ref in requested_objects:
        normalized = normalize_ref(ref)
        if any(ref_matches_title(normalized, title) for title in titles):
            resolved.append(ref)
    return resolved


def extract_references_from_chunks(chunks: list[Chunk]) -> list[str]:
    """Extract simple cross-reference labels from selected chunks."""
    refs: list[str] = []
    pattern = re.compile(
        r"\b(?:Table|Figure|Expression|Equation|Annex)\s+[A-Z]?\d+(?:\.\d+)*(?:[A-Z])?\b",
        re.IGNORECASE,
    )
    for chunk in chunks:
        text = " ".join([chunk.content, " ".join(chunk.metadata.section_path), chunk.metadata.object_label])
        for match in pattern.findall(text):
            normalized = " ".join(match.split())
            if normalized not in refs:
                refs.append(normalized)
    return refs


def node_trace(item: dict[str, Any]) -> dict[str, Any]:
    """Return a compact JSON trace entry for a ranked node."""
    node = item["node"]
    return {
        "doc_id": item["doc_id"],
        "title": node.get("title"),
        "pages": node_pages(node),
        "score": round(float(item["score"]), 4),
        "reasons": list(item.get("reasons") or []),
    }


def node_pages(node: dict[str, Any]) -> str:
    """Convert a structure node line range to PageIndex page syntax."""
    start = node.get("range_start") or node.get("line_num")
    end = node.get("range_end") or start
    if not isinstance(start, int):
        return ""
    if not isinstance(end, int):
        end = start
    return f"{start}-{end}" if end > start else str(start)


def node_span(node: dict[str, Any]) -> int:
    """Return the approximate node span for tie-breaking."""
    start = node.get("range_start") or node.get("line_num")
    end = node.get("range_end") or start
    if not isinstance(start, int) or not isinstance(end, int):
        return 0
    return max(0, end - start)


def parse_page_range(pages: str) -> list[int]:
    """Parse '5-7', '3,8', or '12' into a list of line/page numbers."""
    result: list[int] = []
    for part in str(pages or "").split(","):
        token = part.strip()
        if not token:
            continue
        if "-" in token:
            try:
                start, end = token.split("-", 1)
                result.extend(range(int(start), int(end) + 1))
            except ValueError:
                continue
        else:
            try:
                result.append(int(token))
            except ValueError:
                continue
    return result


def collect_clause_ids(node: dict[str, Any]) -> list[str]:
    """Collect clause ids from one node path."""
    clause_ids: list[str] = []
    for title in list(node.get("path") or []) + [str(node.get("title") or "")]:
        clause = leading_clause(title)
        if clause and clause not in clause_ids:
            clause_ids.append(clause)
    return clause_ids


def leading_clause(text: str) -> str:
    """Extract leading Eurocode-style numeric clause from text."""
    match = re.match(r"^\s*(\d+(?:\.\d+)*)\b", str(text or ""))
    return match.group(1) if match else ""


def extract_object_label(title: str) -> str:
    """Return object label when a title is a table/figure/expression/annex."""
    normalized = str(title or "").strip()
    if re.match(r"^(Table|Figure|Expression|Equation|Annex)\b", normalized, re.IGNORECASE):
        return normalized
    return ""


def infer_element_type(object_label: str, content: str) -> ElementType:
    """Infer Chunk element type from object label and content prefix."""
    label = f"{object_label} {content[:120]}"
    if re.search(r"\btable\b", label, re.IGNORECASE):
        return ElementType.TABLE
    if re.search(r"\b(figure|fig\.)\b", label, re.IGNORECASE):
        return ElementType.IMAGE
    if re.search(r"\b(expression|equation|formula)\b", label, re.IGNORECASE):
        return ElementType.FORMULA
    return ElementType.TEXT


def tokenize(text: str) -> set[str]:
    """Tokenize English/code-ish retrieval text."""
    tokens = {
        token
        for token in re.findall(r"[a-z0-9]+(?:\.[0-9]+)*", str(text or "").lower())
        if len(token) > 1
    }
    return tokens - {"the", "and", "for", "with", "from", "what", "when", "how"}


def normalize_ref(text: str) -> str:
    """Normalize reference label/title text for matching."""
    return re.sub(r"[^a-z0-9.]+", " ", str(text or "").lower()).strip()


def _build_shortlist(candidates: dict[str, float], strategy: str, max_docs: int) -> Shortlist:
    ranked = sorted(candidates.items(), key=lambda item: (item[1], item[0]), reverse=True)
    selected = ranked[:max_docs]
    return Shortlist(
        doc_ids=[doc_id for doc_id, _ in selected],
        strategy=strategy,
        scores={doc_id: score for doc_id, score in selected},
    )


def _metadata_candidates(meta: dict[str, dict[str, Any]], source_filter: str) -> dict[str, float]:
    normalized_filter = normalize_doc_text(source_filter)
    candidates: dict[str, float] = {}
    for doc_id, entry in meta.items():
        normalized_name = normalize_doc_text(str(entry.get("doc_name") or ""))
        if normalized_filter and normalized_filter in normalized_name:
            candidates[doc_id] = 10.0 + len(normalized_filter)
    return candidates


def normalize_doc_text(text: str) -> str:
    """Normalize document names for shortlist matching."""
    return re.sub(r"[^a-z0-9]+", "", str(text or "").lower())
