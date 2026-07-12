"""Response formatting and conversation history helpers for query endpoints."""

from __future__ import annotations

import inspect
import json
import time
from collections.abc import AsyncIterator, Awaitable, Callable

import structlog
from structlog.contextvars import get_contextvars

from server.agents.evidence import EvidenceBundle
from server.api.v1._progress import _progress_event
from server.config import ServerConfig
from server.core.generation import (
    _build_retrieval_context,
    _build_sources_from_chunks,
)
from server.core.generation import postprocess_citations
from server.models.schemas import Chunk
from server.models.schemas import QueryRequest, QueryResponse, RetrievalContext, Source
from shared.spot_check import SpotCheckRecorder, get_current_recorder

logger = structlog.get_logger(__name__)


def _spot_check_query_signals(question_type: object) -> dict[str, object]:
    """Build the reserved query_signals spot-check shape."""
    legacy_question_type = getattr(question_type, "value", question_type)
    return {
        "legacy_question_type": legacy_question_type,
        "exact_refs": [],
        "procedural_cues": False,
    }


async def _add_conversation_turn(
    conv_mgr: object,
    conversation_id: str,
    question: str,
    answer: str,
    *,
    sources: list[Source] | list[dict] | None = None,
    related_refs: list[str] | None = None,
    retrieval_context: RetrievalContext | dict | None = None,
    question_type: str | None = None,
    engineering_context: dict[str, object] | None = None,
    answer_mode: str | None = None,
    groundedness: str | None = None,
    thinking: str | None = None,
    tool_trace: list[dict] | None = None,
    response_payload: dict[str, object] | None = None,
) -> str | None:
    """Persist one Q&A turn through sync or async managers."""
    serialized_sources = _serialize_sources_for_history(sources)
    serialized_retrieval_context = _serialize_retrieval_context_for_history(
        retrieval_context
    )
    serialized_response_payload = _serialize_response_payload_for_history(
        response_payload
    )
    metadata_kwargs = {
        "sources": serialized_sources,
        "related_refs": related_refs,
        "retrieval_context": serialized_retrieval_context,
        "question_type": question_type,
        "engineering_context": engineering_context,
        "answer_mode": answer_mode,
        "groundedness": groundedness,
        "thinking": thinking,
        "tool_trace": tool_trace,
        "response_payload": serialized_response_payload,
    }
    adder = getattr(conv_mgr, "add_turn_async", None)
    if adder is not None:
        if not _supports_turn_metadata(adder):
            return await adder(conversation_id, question, answer)
        return await adder(
            conversation_id,
            question,
            answer,
            **_filter_turn_metadata(adder, metadata_kwargs),
        )
    sync_adder = getattr(conv_mgr, "add_turn")
    if _supports_turn_metadata(sync_adder):
        sync_adder(
            conversation_id,
            question,
            answer,
            **_filter_turn_metadata(sync_adder, metadata_kwargs),
        )
    else:
        sync_adder(conversation_id, question, answer)
    return None


def _supports_turn_metadata(adder: object) -> bool:
    """Return whether an add_turn callable accepts optional metadata keywords."""
    try:
        signature = inspect.signature(adder)
    except (TypeError, ValueError):
        return False
    parameters = signature.parameters.values()
    return any(
        parameter.kind == inspect.Parameter.VAR_KEYWORD for parameter in parameters
    ) or any(
        name in signature.parameters
        for name in (
            "sources",
            "related_refs",
            "retrieval_context",
            "question_type",
            "engineering_context",
            "answer_mode",
            "groundedness",
            "thinking",
            "tool_trace",
            "response_payload",
        )
    )


def _filter_turn_metadata(adder: object, metadata_kwargs: dict) -> dict:
    """Pass only metadata keywords accepted by the conversation manager."""
    try:
        signature = inspect.signature(adder)
    except (TypeError, ValueError):
        return {}
    if any(
        parameter.kind == inspect.Parameter.VAR_KEYWORD
        for parameter in signature.parameters.values()
    ):
        return metadata_kwargs
    return {
        key: value
        for key, value in metadata_kwargs.items()
        if key in signature.parameters
    }


def _serialize_sources_for_history(
    sources: list[Source] | list[dict] | None,
) -> list[dict[str, object]]:
    """Return JSON-ready source payloads for Redis history display."""
    if not sources:
        return []
    serialized: list[dict[str, object]] = []
    for source in sources:
        if isinstance(source, Source):
            serialized.append(_camelize_source_payload(source.model_dump(mode="json")))
        elif isinstance(source, dict):
            serialized.append(_camelize_source_payload(source))
    return serialized


def _serialize_retrieval_context_for_history(
    retrieval_context: RetrievalContext | dict | None,
) -> dict[str, object] | None:
    """Return JSON-ready retrieval context for Redis history display."""
    if retrieval_context is None:
        return None
    if isinstance(retrieval_context, RetrievalContext):
        return retrieval_context.model_dump(mode="json")
    return dict(retrieval_context)


def _serialize_response_payload_for_history(
    response_payload: dict[str, object] | None,
) -> dict[str, object] | None:
    """Return a JSON-ready full response snapshot for Redis history display."""
    if response_payload is None:
        return None
    return dict(response_payload)


def _response_usage(response: object | None = None) -> dict[str, int] | None:
    """Extract token usage from a response-like object or active recorder."""
    usage = getattr(response, "usage", None) if response is not None else None
    if usage is None:
        recorder = get_current_recorder()
        usage = recorder.data.get("usage") if recorder is not None else None
    if usage is None:
        return None
    if isinstance(usage, dict):
        return {
            key: int(value or 0)
            for key, value in usage.items()
            if isinstance(value, int) or value is not None
        }

    summary: dict[str, int] = {}
    for key in (
        "requests",
        "input_tokens",
        "output_tokens",
        "total_tokens",
        "cached_tokens",
        "reasoning_tokens",
    ):
        value = getattr(usage, key, None)
        if value is not None:
            summary[key] = int(value or 0)
    return summary or None


def _response_elapsed_ms(
    response: object | None = None,
    *,
    started_at: float | None = None,
) -> int | None:
    """Extract elapsed time from a response-like object or wall clock."""
    elapsed_ms = getattr(response, "elapsed_ms", None) if response is not None else None
    if elapsed_ms is None:
        if started_at is None:
            return None
        elapsed_ms = int((time.perf_counter() - started_at) * 1000)
    try:
        return int(elapsed_ms)
    except (TypeError, ValueError):
        return None


def _camelize_source_payload(source: dict) -> dict:
    """Add interface-document camelCase aliases while preserving old keys."""
    aliases = {
        "document_id": "docId",
        "display_title": "displayTitle",
        "element_type": "elementType",
        "original_text": "originalText",
        "locator_text": "locatorText",
        "highlight_text": "highlightText",
    }
    payload = dict(source)
    for old_key, new_key in aliases.items():
        if old_key in source:
            value = source[old_key]
            if old_key == "element_type" and value == "image":
                value = "figure"
            payload[new_key] = value
    return payload


def _answer_mode_from_groundedness(groundedness: str | None) -> str:
    """Map internal evidence state to the external answerMode contract."""
    if groundedness == "grounded":
        return "standard"
    if groundedness == "partial":
        return "cautious"
    return "fallback"


def _confidence_from_groundedness(groundedness: str | None) -> str:
    """Provide a stable external confidence value when generation omits one."""
    if groundedness == "grounded":
        return "high"
    if groundedness == "partial":
        return "medium"
    return "low"


def _external_done_payload(
    data: dict,
    *,
    question_type: str | None,
    groundedness: str | None,
    title: str | None,
    answer_mode: str | None = None,
) -> dict:
    """Merge stream done metadata required by the external API document."""
    sources = [
        _camelize_source_payload(source) if isinstance(source, dict) else source
        for source in data.get("sources", [])
    ]
    related_refs = data.get("related_refs", [])
    return {
        **data,
        "code": 200,
        "sources": sources,
        "relatedRefs": related_refs,
        "confidence": data.get("confidence")
        or _confidence_from_groundedness(groundedness),
        "questionType": question_type or data.get("question_type"),
        "answerMode": answer_mode or _answer_mode_from_groundedness(groundedness),
        "groundedness": groundedness,
        "title": title,
        "usage": data.get("usage"),
        "elapsed_ms": data.get("elapsed_ms"),
    }


def _conversation_history(
    *,
    conv: object,
    req: QueryRequest,
    config: ServerConfig,
    uses_external_session: bool,
) -> list:
    """Return the conversation history visible to answer generation."""
    return (
        list(getattr(conv, "history", []) or [])[-config.max_conversation_rounds :]
        if uses_external_session
        else []
    )


def _bundle_metadata(bundle: EvidenceBundle, key: str) -> object:
    """Read optional query metadata threaded through the evidence bundle."""
    value = getattr(bundle, key, None)
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    return value


def _ref_ordered_chunks(bundle: EvidenceBundle) -> list[Chunk]:
    chunks = bundle.citable_chunks()
    bundle.ensure_ref_ids(chunks)
    return sorted(
        chunks,
        key=lambda chunk: _ref_index(bundle.ref_ids_by_chunk_id.get(chunk.chunk_id)),
    )


def _ref_index(label: str | None) -> int:
    if not label:
        return 10**9
    try:
        return int(label.rsplit("-", 1)[1])
    except (IndexError, ValueError):
        return 10**9


def _sources_from_bundle(bundle: EvidenceBundle) -> list[Source]:
    if not bundle.has_rag_evidence:
        return []
    chunks = _ref_ordered_chunks(bundle)
    return _build_sources_from_chunks(chunks, prioritized_chunks=chunks)


def _retrieval_context_from_bundle(bundle: EvidenceBundle) -> RetrievalContext:
    if not bundle.has_rag_evidence:
        return RetrievalContext()
    return _build_retrieval_context(
        bundle.chunks,
        bundle.parent_chunks,
        guide_chunks=bundle.guide_chunks,
        guide_example_chunks=bundle.guide_example_chunks,
        ref_chunks=bundle.ref_chunks,
        scores=bundle.scores,
        resolved_refs=bundle.resolved_refs,
        unresolved_refs=bundle.unresolved_refs,
        slot_results=bundle.slot_results,
        unresolved_slots=bundle.unresolved_slots,
    )


async def _build_query_response(
    *,
    req: QueryRequest,
    runtime_config: ServerConfig,
    config: ServerConfig,
    agent_reply: str,
    bundle: EvidenceBundle,
    conv: object,
    uses_external_session: bool,
    generate_answer_fn: Callable[..., Awaitable[QueryResponse]] | None = None,
) -> tuple[QueryResponse, str]:
    """Build the non-streaming query response and answer mode."""
    del generate_answer_fn, runtime_config, config, uses_external_session
    sources = _sources_from_bundle(bundle)
    normalized_answer = postprocess_citations(agent_reply, len(sources))
    groundedness = bundle.groundedness if bundle.has_rag_evidence else None
    response = QueryResponse(
        answer=normalized_answer,
        sources=sources,
        related_refs=[],
        confidence=_confidence_from_groundedness(groundedness),
        conversation_id=conv.conversation_id,
        degraded=False,
        usage=None,
        elapsed_ms=None,
        retrieval_context=_retrieval_context_from_bundle(bundle),
        question_type=_bundle_metadata(bundle, "question_type"),
        engineering_context=_bundle_metadata(bundle, "engineering_context"),
        groundedness=groundedness,
    )
    return response, _answer_mode_from_groundedness(groundedness)


def _build_direct_agent_payload(
    *,
    agent_reply: str,
    bundle: EvidenceBundle,
    groundedness: str | None = None,
) -> dict[str, object]:
    """Build the external payload for direct agent responses."""
    effective_groundedness = groundedness or (
        bundle.groundedness if bundle.has_rag_evidence else None
    )
    sources = _sources_from_bundle(bundle)
    answer_mode = (
        _answer_mode_from_groundedness(effective_groundedness)
        if bundle.has_rag_evidence
        else "direct"
    )
    confidence = _confidence_from_groundedness(effective_groundedness)
    return {
        "answer": postprocess_citations(agent_reply, len(sources)),
        "sources": [source.model_dump(mode="json") for source in sources],
        "related_refs": [],
        "confidence": confidence,
        "retrieval_context": _retrieval_context_from_bundle(bundle).model_dump(
            mode="json"
        ),
        "question_type": _bundle_metadata(bundle, "question_type"),
        "engineering_context": _bundle_metadata(bundle, "engineering_context"),
        "groundedness": effective_groundedness,
        "answerMode": answer_mode,
        "tool_trace": bundle.tool_trace,
    }


async def _stream_direct_agent_events(
    *,
    req: QueryRequest,
    conv_mgr: object,
    conv: object,
    agent_reply: str,
    bundle: EvidenceBundle,
    started_at: float,
    uses_external_session: bool,
    request_started_at: float | None = None,
    usage: dict[str, int] | None = None,
    emit_answer_chunk: bool = True,
) -> AsyncIterator[dict[str, str]]:
    """Yield stream events for direct agent responses."""
    payload = _build_direct_agent_payload(agent_reply=agent_reply, bundle=bundle)
    yield {
        "event": "progress",
        "data": json.dumps(
            _progress_event(
                stage="direct",
                status="completed",
                title="生成回复",
                summary="Agent 已生成最终回复。",
                started_at=started_at,
                facts={
                    "needs_rag": bundle.has_rag_evidence,
                    "tool_calls": len(bundle.tool_trace),
                },
            ),
            ensure_ascii=False,
        ),
    }
    if emit_answer_chunk:
        yield {
            "event": "chunk",
            "data": json.dumps(
                {"text": str(payload.get("answer") or agent_reply), "done": False},
                ensure_ascii=False,
            ),
        }
    data = _external_done_payload(
        payload,
        question_type=payload.get("question_type"),
        groundedness=payload.get("groundedness"),
        title=None,
        answer_mode=str(payload.get("answerMode") or "direct"),
    )
    data["usage"] = usage or _response_usage()
    data["elapsed_ms"] = _response_elapsed_ms(
        started_at=request_started_at or started_at
    )
    data["request_id"] = get_contextvars().get("request_id", "")
    if uses_external_session:
        title = await _add_conversation_turn(
            conv_mgr,
            conv.conversation_id,
            req.question,
            str(data.get("answer") or ""),
            sources=data.get("sources", []),
            related_refs=data.get("relatedRefs", []),
            retrieval_context=data.get("retrievalContext")
            or data.get("retrieval_context"),
            question_type=data.get("questionType"),
            engineering_context=data.get("engineeringContext")
            or data.get("engineering_context"),
            answer_mode=data.get("answerMode"),
            groundedness=data.get("groundedness"),
            tool_trace=bundle.tool_trace,
            response_payload=data,
        )
        data["title"] = title
    yield {
        "event": "done",
        "data": json.dumps(data, ensure_ascii=False),
    }


def _record_agent_spot_check(
    recorder: SpotCheckRecorder | None,
    bundle: EvidenceBundle,
) -> None:
    """Record agent-mode query signals without running query understanding twice."""
    if recorder is None:
        return
    recorder.record("expanded_queries", {"queries": []})
    recorder.record(
        "query_signals",
        {
            "needs_rag": bundle.has_rag_evidence,
            "chunk_count": bundle.chunk_count,
            "exact_refs": [],
            "procedural_cues": False,
        },
    )
