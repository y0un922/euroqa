"""SSE client for /api/v1/query/stream used by the MVP runner."""

from __future__ import annotations

import json
import time
from typing import Any

import httpx


def _parse_sse_events(lines: list[str]) -> list[tuple[str, str]]:
    events: list[tuple[str, str]] = []
    event_name = "message"
    data_lines: list[str] = []

    def flush() -> None:
        nonlocal event_name, data_lines
        if data_lines:
            events.append((event_name, "\n".join(data_lines)))
        event_name = "message"
        data_lines = []

    for raw_line in lines:
        line = raw_line.rstrip("\r")
        if line == "":
            flush()
            continue
        if line.startswith(":"):
            continue
        if line.startswith("event:"):
            event_name = line.split(":", 1)[1].strip()
        elif line.startswith("data:"):
            data_lines.append(line.split(":", 1)[1].lstrip())
    flush()
    return events


def _chunk_ids_from_retrieval_context(ctx: dict[str, Any] | None) -> list[str]:
    """Ordered unique chunk IDs from EvidenceBundle.citable_chunks()-equivalent export.

    RetrievalContext serializes chunks / parent_chunks / ref_chunks /
    guide_chunks / guide_example_chunks. Order matches citable_chunks merge:
    chunks → parent → ref → guide → guide_example.
    """
    if not ctx or not isinstance(ctx, dict):
        return []
    keys = (
        "chunks",
        "parent_chunks",
        "ref_chunks",
        "guide_chunks",
        "guide_example_chunks",
    )
    seen: set[str] = set()
    ordered: list[str] = []
    for key in keys:
        items = ctx.get(key) or []
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            cid = item.get("chunk_id")
            if isinstance(cid, str) and cid and cid not in seen:
                seen.add(cid)
                ordered.append(cid)
    return ordered


def _chunk_contents_from_retrieval_context(
    ctx: dict[str, Any] | None,
) -> list[dict[str, str]]:
    """Ordered citable chunk snapshots for judge prompts / hashing."""
    if not ctx or not isinstance(ctx, dict):
        return []
    keys = (
        "chunks",
        "parent_chunks",
        "ref_chunks",
        "guide_chunks",
        "guide_example_chunks",
    )
    seen: set[str] = set()
    out: list[dict[str, str]] = []
    for key in keys:
        items = ctx.get(key) or []
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            cid = item.get("chunk_id")
            if not isinstance(cid, str) or not cid or cid in seen:
                continue
            seen.add(cid)
            text = item.get("content") or item.get("text") or ""
            out.append(
                {
                    "chunk_id": cid,
                    "content": text if isinstance(text, str) else str(text),
                    "section": str(item.get("section") or ""),
                    "title": str(item.get("title") or item.get("display_title") or ""),
                }
            )
    return out


def query_stream(
    api_url: str,
    question: str,
    *,
    timeout_s: float = 180.0,
    session_id: str | None = None,
) -> dict[str, Any]:
    """Call query/stream and normalize answer + retrievalContext + refs."""
    answer_parts: list[str] = []
    progress_events: list[dict[str, Any]] = []
    done_payload: dict[str, Any] | None = None
    pending_lines: list[str] = []
    started = time.monotonic()
    body: dict[str, Any] = {"question": question, "stream": True}
    if session_id:
        body["session_id"] = session_id

    timeout = httpx.Timeout(timeout_s)
    with httpx.Client(timeout=timeout) as client:
        with client.stream("POST", api_url, json=body) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                pending_lines.append(line)
                if line != "":
                    continue
                for event_name, data_text in _parse_sse_events(pending_lines):
                    payload = json.loads(data_text)
                    if event_name == "chunk":
                        text = payload.get("text")
                        if isinstance(text, str):
                            answer_parts.append(text)
                    elif event_name == "progress":
                        if isinstance(payload, dict):
                            progress_events.append(payload)
                    elif event_name == "done":
                        if not isinstance(payload, dict):
                            raise ValueError("done event payload must be a JSON object")
                        done_payload = payload
                    elif event_name == "error":
                        raise RuntimeError(f"stream error event: {payload}")
                pending_lines = []

    if pending_lines:
        for event_name, data_text in _parse_sse_events(pending_lines):
            payload = json.loads(data_text)
            if event_name == "done" and isinstance(payload, dict):
                done_payload = payload

    if done_payload is None:
        raise RuntimeError("stream ended before done event")

    answer = done_payload.get("normalized_answer") or done_payload.get("answer")
    if not isinstance(answer, str):
        answer = "".join(answer_parts)

    # retrievalContext may be camelCase (external) or nested.
    retrieval_context = (
        done_payload.get("retrievalContext")
        or done_payload.get("retrieval_context")
        or {}
    )
    if not isinstance(retrieval_context, dict):
        retrieval_context = {}

    unresolved_refs = list(retrieval_context.get("unresolved_refs") or [])
    # Also harvest from progress facts if context empty.
    if not unresolved_refs:
        for ev in progress_events:
            facts = ev.get("facts") or {}
            if isinstance(facts, dict) and facts.get("unresolved_refs"):
                unresolved_refs = list(facts["unresolved_refs"])
                break

    sources = done_payload.get("sources") or []
    if not isinstance(sources, list):
        sources = []

    context_chunk_ids = _chunk_ids_from_retrieval_context(retrieval_context)
    context_chunks = _chunk_contents_from_retrieval_context(retrieval_context)

    return {
        "status": "ok",
        "question": question,
        "answer": answer,
        "sources": sources,
        "citations": sources,
        "confidence": done_payload.get("confidence"),
        "groundedness": done_payload.get("groundedness"),
        "retrieval_context": retrieval_context,
        "context_chunk_ids": context_chunk_ids,
        "context_chunks": context_chunks,
        "unresolved_refs": unresolved_refs,
        "resolved_refs": list(retrieval_context.get("resolved_refs") or []),
        "elapsed_ms": int((time.monotonic() - started) * 1000),
        "raw_done": done_payload,
        "progress_events": progress_events,
    }


def context_id_sequence(result: dict[str, Any]) -> tuple[str, ...]:
    """Ordered context chunk-id sequence (not a set — order is significant)."""
    ids = result.get("context_chunk_ids") or []
    return tuple(str(x) for x in ids if x)


def context_id_set(result: dict[str, Any]) -> frozenset[str]:
    """Unordered id set (diagnostics only). Prefer context_id_sequence for precheck."""
    return frozenset(context_id_sequence(result))


def context_sequences_differ(
    baseline: dict[str, Any] | tuple[str, ...] | list[str],
    candidate: dict[str, Any] | tuple[str, ...] | list[str],
) -> bool:
    """True if ordered chunk-id sequences differ (order or membership)."""
    def _as_seq(x: dict[str, Any] | tuple[str, ...] | list[str]) -> tuple[str, ...]:
        if isinstance(x, dict):
            return context_id_sequence(x)
        return tuple(str(i) for i in x if i)

    return _as_seq(baseline) != _as_seq(candidate)
