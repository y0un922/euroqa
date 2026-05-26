"""POST /api/v1/query — main Q&A endpoint with optional SSE streaming."""
from __future__ import annotations

import json
import inspect
import time

import structlog
from fastapi import APIRouter, Depends
from sse_starlette.sse import EventSourceResponse

from server.config import ServerConfig
from server.deps import get_config, get_conversation_manager, get_glossary, get_retriever
from server.core.query_understanding import analyze_query
from server.core.generation import generate_answer, generate_answer_stream, postprocess_citations
from server.models.schemas import QueryRequest, QueryResponse, RetrievalContext, Source
from shared.spot_check import (
    SpotCheckRecorder,
    flush_current_recorder,
    is_spot_check_enabled,
    reset_current_recorder,
    set_current_recorder,
)

router = APIRouter()
logger = structlog.get_logger(__name__)


_QUESTION_TYPE_LABELS = {
    "rule": "规则/假设类问题",
    "parameter": "参数/限值类问题",
    "calculation": "计算类问题",
    "mechanism": "机理/影响因素类问题",
}


def _resolve_runtime_config(config: ServerConfig, req: QueryRequest) -> ServerConfig:
    """Merge request-scoped LLM overrides with the default server config."""
    if req.llm is None:
        return config

    return config.with_llm_override(
        api_key=req.llm.api_key,
        base_url=req.llm.base_url,
        model=req.llm.model,
        enable_thinking=req.llm.enable_thinking,
    )


def _conversation_id_from_request(req: QueryRequest) -> str | None:
    """Resolve old conversation_id and external sessionId aliases."""
    return req.session_id or req.conversation_id


def _uses_external_session(req: QueryRequest) -> bool:
    """Return whether the request opted into Redis-style session behavior."""
    return bool(req.session_id)


def _spot_check_query_signals(question_type: object) -> dict[str, object]:
    """Build the reserved query_signals spot-check shape."""
    legacy_question_type = getattr(question_type, "value", question_type)
    return {
        "legacy_question_type": legacy_question_type,
        "exact_refs": [],
        "procedural_cues": False,
    }


async def _get_conversation_state(conv_mgr: object, conversation_id: str | None) -> object:
    """Load conversation state from sync or async managers."""
    getter = getattr(conv_mgr, "get_or_create_async", None)
    if getter is not None:
        return await getter(conversation_id)
    return conv_mgr.get_or_create(conversation_id)


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
    response_payload: dict[str, object] | None = None,
) -> str | None:
    """Persist one Q&A turn through sync or async managers."""
    serialized_sources = _serialize_sources_for_history(sources)
    serialized_retrieval_context = _serialize_retrieval_context_for_history(retrieval_context)
    serialized_response_payload = _serialize_response_payload_for_history(response_payload)
    metadata_kwargs = {
        "sources": serialized_sources,
        "related_refs": related_refs,
        "retrieval_context": serialized_retrieval_context,
        "question_type": question_type,
        "engineering_context": engineering_context,
        "answer_mode": answer_mode,
        "groundedness": groundedness,
        "thinking": thinking,
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
            **metadata_kwargs,
        )
    sync_adder = getattr(conv_mgr, "add_turn")
    if _supports_turn_metadata(sync_adder):
        sync_adder(conversation_id, question, answer, **metadata_kwargs)
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
    return any(parameter.kind == inspect.Parameter.VAR_KEYWORD for parameter in parameters) or any(
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
            "response_payload",
        )
    )


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
        "confidence": data.get("confidence") or _confidence_from_groundedness(groundedness),
        "questionType": question_type or data.get("question_type"),
        "answerMode": _answer_mode_from_groundedness(groundedness),
        "groundedness": groundedness,
        "title": title,
    }


def _field_value(payload: object, key: str) -> object:
    """Read a value from a dict, model, enum-like object, or namespace."""
    if payload is None:
        return None
    if isinstance(payload, dict):
        return payload.get(key)
    return getattr(payload, key, None)


def _enum_value(payload: object) -> str | None:
    """Normalize enum-like values to a displayable string."""
    if payload is None:
        return None
    value = getattr(payload, "value", payload)
    return str(value) if value is not None else None


def _target_summary(target_hint: object) -> str:
    """Build a compact user-facing target string from routing hints."""
    parts: list[str] = []
    document = _field_value(target_hint, "document")
    clause = _field_value(target_hint, "clause")
    obj = _field_value(target_hint, "object")
    if document:
        parts.append(str(document))
    if clause:
        parts.append(f"Clause {clause}")
    if obj:
        parts.append(str(obj))
    return " ".join(parts)


def _source_count(chunks: list[object]) -> int:
    """Count distinct source labels in retrieved chunks."""
    sources: set[str] = set()
    for chunk in chunks:
        metadata = getattr(chunk, "metadata", None)
        source = getattr(metadata, "source", "")
        if source:
            sources.add(str(source))
    return len(sources)


def _progress_event(
    *,
    stage: str,
    status: str,
    title: str,
    summary: str,
    started_at: float,
    facts: dict | None = None,
) -> dict:
    """Create one query progress SSE payload."""
    return {
        "stage": stage,
        "status": status,
        "title": title,
        "summary": summary,
        "elapsed_ms": int((time.perf_counter() - started_at) * 1000),
        "facts": facts or {},
    }


def _understanding_summary(analysis: object) -> tuple[str, dict]:
    """Summarize query-understanding output for end users."""
    question_type = _enum_value(_field_value(analysis, "question_type"))
    label = _QUESTION_TYPE_LABELS.get(question_type or "", "规范问答问题")
    target = _target_summary(_field_value(analysis, "target_hint"))
    if target:
        summary = f"识别为{label}，优先查找 {target}。"
    else:
        summary = f"识别为{label}，将进行跨文档规范检索。"
    facts = {"question_type": question_type}
    if target:
        facts["target"] = target
    return summary, facts


def _retrieval_summary(result: object) -> tuple[str, dict]:
    """Summarize retrieved evidence counts without exposing raw chunks."""
    chunks = list(getattr(result, "chunks", []) or [])
    ref_chunks = list(getattr(result, "ref_chunks", []) or [])
    evidence_count = len(chunks) + len(ref_chunks)
    source_count = _source_count(chunks + ref_chunks)
    if evidence_count == 0:
        summary = "暂未稳定定位到规范证据，回答会明确说明当前证据不足。"
    elif source_count > 0:
        summary = f"找到 {evidence_count} 条相关规范证据，覆盖 {source_count} 个文档来源。"
    else:
        summary = f"找到 {evidence_count} 条相关规范证据。"
    return summary, {
        "evidence_count": evidence_count,
        "source_count": source_count,
    }


def _reference_summary(result: object) -> tuple[str, dict]:
    """Summarize deterministic and fallback cross-reference closure."""
    resolved_refs = list(getattr(result, "resolved_refs", []) or [])
    unresolved_refs = list(getattr(result, "unresolved_refs", []) or [])
    ref_chunks = list(getattr(result, "ref_chunks", []) or [])
    if resolved_refs and unresolved_refs:
        summary = (
            f"已补齐 {', '.join(resolved_refs)}；"
            f"仍有 {', '.join(unresolved_refs)} 未补齐。"
        )
    elif resolved_refs:
        summary = f"已补齐 {', '.join(resolved_refs)}。"
    elif unresolved_refs:
        summary = f"仍有 {', '.join(unresolved_refs)} 未补齐，回答会提示证据不足。"
    elif ref_chunks:
        summary = f"已补齐 {len(ref_chunks)} 条表格、公式或附录引用。"
    else:
        summary = "未发现必须补充的表格、公式或附录引用。"
    return summary, {
        "resolved_refs": resolved_refs,
        "unresolved_refs": unresolved_refs,
    }


def _guide_summary(result: object) -> tuple[str, str, dict]:
    """Summarize Designers' Guide and worked-example evidence."""
    guide_count = len(getattr(result, "guide_chunks", []) or [])
    example_count = len(getattr(result, "guide_example_chunks", []) or [])
    total = guide_count + example_count
    facts = {"guide_count": guide_count, "example_count": example_count}
    if total == 0:
        return "skipped", "当前问题未命中可用的 Designers' Guide 参考或算例。", facts
    return (
        "completed",
        f"找到 {total} 条 Designers' Guide 参考，可作为理解补充。",
        facts,
    )


@router.post("/query", response_model=QueryResponse)
async def query(
    req: QueryRequest,
    config=Depends(get_config),
    retriever=Depends(get_retriever),
    glossary=Depends(get_glossary),
    conv_mgr=Depends(get_conversation_manager),
) -> QueryResponse:
    runtime_config = _resolve_runtime_config(config, req)
    recorder = SpotCheckRecorder(query=req.question) if is_spot_check_enabled() else None
    token = set_current_recorder(recorder)
    try:
        analysis = await analyze_query(req.question, glossary, runtime_config)
        if recorder:
            recorder.record(
                "expanded_queries",
                {"queries": analysis.expanded_queries},
            )
            recorder.record(
                "query_signals",
                _spot_check_query_signals(analysis.question_type),
            )

        filters = analysis.filters
        if req.domain:
            filters["source"] = req.domain

        result = await retriever.retrieve(
            queries=analysis.expanded_queries,
            original_query=analysis.original_question,
            filters=filters,
            intent_label=analysis.intent_label,
            question_type=analysis.question_type.value if analysis.question_type else None,
            guide_hint=analysis.guide_hint,
            target_hint=analysis.target_hint,
            requested_objects=analysis.requested_objects,
            preferred_element_type=analysis.preferred_element_type,
        )

        conv = await _get_conversation_state(conv_mgr, _conversation_id_from_request(req))
        history = list(getattr(conv, "history", []) or []) if _uses_external_session(req) else []

        response = await generate_answer(
            question=req.question,
            chunks=result.chunks,
            parent_chunks=result.parent_chunks,
            scores=result.scores,
            glossary_terms=analysis.matched_terms,
            conversation_history=history[-config.max_conversation_rounds:],
            config=runtime_config,
            ref_chunks=result.ref_chunks,
            guide_chunks=result.guide_chunks,
            guide_example_chunks=result.guide_example_chunks,
            question_type=analysis.question_type,
            engineering_context=analysis.engineering_context,
            groundedness=result.groundedness,
            resolved_refs=result.resolved_refs,
            unresolved_refs=result.unresolved_refs,
            intent_label=analysis.intent_label,
        )
        response = response.model_copy(
            update={
                "conversation_id": conv.conversation_id,
                "question_type": analysis.question_type.value if analysis.question_type else None,
                "engineering_context": analysis.engineering_context.model_dump() if analysis.engineering_context else None,
                "groundedness": result.groundedness,
            }
        )
        if _uses_external_session(req):
            await _add_conversation_turn(
                conv_mgr,
                conv.conversation_id,
                req.question,
                response.answer,
                sources=response.sources,
                related_refs=response.related_refs,
                retrieval_context=response.retrieval_context,
                question_type=response.question_type,
                engineering_context=response.engineering_context,
                answer_mode=_answer_mode_from_groundedness(response.groundedness),
                groundedness=response.groundedness,
            )

        return response
    finally:
        flush_current_recorder()
        reset_current_recorder(token)


@router.post("/query/stream")
async def query_stream(
    req: QueryRequest,
    config=Depends(get_config),
    retriever=Depends(get_retriever),
    glossary=Depends(get_glossary),
    conv_mgr=Depends(get_conversation_manager),
):
    """SSE 流式问答端点，逐步返回 LLM 生成的回答片段。"""
    runtime_config = _resolve_runtime_config(config, req)

    async def event_generator():
        started_at = time.perf_counter()
        recorder = SpotCheckRecorder(query=req.question) if is_spot_check_enabled() else None
        token = set_current_recorder(recorder)
        try:
            yield {
                "event": "progress",
                "data": json.dumps(
                    _progress_event(
                        stage="understanding",
                        status="running",
                        title="理解问题",
                        summary="正在理解问题并提取检索线索...",
                        started_at=started_at,
                    ),
                    ensure_ascii=False,
                ),
            }
            analysis = await analyze_query(req.question, glossary, runtime_config)
            if recorder:
                recorder.record(
                    "expanded_queries",
                    {"queries": analysis.expanded_queries},
                )
                recorder.record(
                    "query_signals",
                    _spot_check_query_signals(analysis.question_type),
                )
            summary, facts = _understanding_summary(analysis)
            yield {
                "event": "progress",
                "data": json.dumps(
                    _progress_event(
                        stage="understanding",
                        status="completed",
                        title="理解问题",
                        summary=summary,
                        started_at=started_at,
                        facts=facts,
                    ),
                    ensure_ascii=False,
                ),
            }

            filters = analysis.filters
            if req.domain:
                filters["source"] = req.domain

            yield {
                "event": "progress",
                "data": json.dumps(
                    _progress_event(
                        stage="retrieving",
                        status="running",
                        title="检索规范条文",
                        summary="正在检索规范条文...",
                        started_at=started_at,
                    ),
                    ensure_ascii=False,
                ),
            }
            result = await retriever.retrieve(
                queries=analysis.expanded_queries,
                original_query=analysis.original_question,
                filters=filters,
                intent_label=analysis.intent_label,
                question_type=analysis.question_type.value if analysis.question_type else None,
                guide_hint=analysis.guide_hint,
                target_hint=analysis.target_hint,
                requested_objects=analysis.requested_objects,
                preferred_element_type=analysis.preferred_element_type,
            )
            summary, facts = _retrieval_summary(result)
            yield {
                "event": "progress",
                "data": json.dumps(
                    _progress_event(
                        stage="retrieving",
                        status="completed",
                        title="检索规范条文",
                        summary=summary,
                        started_at=started_at,
                        facts=facts,
                    ),
                    ensure_ascii=False,
                ),
            }

            summary, facts = _reference_summary(result)
            yield {
                "event": "progress",
                "data": json.dumps(
                    _progress_event(
                        stage="references",
                        status="completed",
                        title="补齐引用",
                        summary=summary,
                        started_at=started_at,
                        facts=facts,
                    ),
                    ensure_ascii=False,
                ),
            }

            guide_status, summary, facts = _guide_summary(result)
            yield {
                "event": "progress",
                "data": json.dumps(
                    _progress_event(
                        stage="guide",
                        status=guide_status,
                        title="检索指南参考",
                        summary=summary,
                        started_at=started_at,
                        facts=facts,
                    ),
                    ensure_ascii=False,
                ),
            }

            conv = await _get_conversation_state(
                conv_mgr,
                _conversation_id_from_request(req),
            )
            history = list(getattr(conv, "history", []) or []) if _uses_external_session(req) else []
            yield {
                "event": "progress",
                "data": json.dumps(
                    _progress_event(
                        stage="generating",
                        status="running",
                        title="生成回答",
                        summary="正在基于检索证据组织回答...",
                        started_at=started_at,
                        facts={
                            "evidence_count": len(result.chunks) + len(result.ref_chunks),
                            "guide_count": len(result.guide_chunks),
                            "example_count": len(result.guide_example_chunks),
                        },
                    ),
                    ensure_ascii=False,
                ),
            }

            answer_parts: list[str] = []
            reasoning_parts: list[str] = []
            async for event_type, data in generate_answer_stream(
                question=req.question,
                chunks=result.chunks,
                parent_chunks=result.parent_chunks,
                scores=result.scores,
                glossary_terms=analysis.matched_terms,
                conversation_history=history[-config.max_conversation_rounds:],
                config=runtime_config,
                ref_chunks=result.ref_chunks,
                guide_chunks=result.guide_chunks,
                guide_example_chunks=result.guide_example_chunks,
                question_type=analysis.question_type,
                engineering_context=analysis.engineering_context,
                groundedness=result.groundedness,
                resolved_refs=result.resolved_refs,
                unresolved_refs=result.unresolved_refs,
                intent_label=analysis.intent_label,
            ):
                if event_type == "reasoning":
                    text = data.get("text") if isinstance(data, dict) else None
                    if isinstance(text, str):
                        reasoning_parts.append(text)
                if event_type == "chunk":
                    text = data.get("text") if isinstance(data, dict) else None
                    if isinstance(text, str):
                        answer_parts.append(text)
                if event_type == "done":
                    answer_text = data.get("answer") if isinstance(data, dict) else None
                    if not isinstance(answer_text, str):
                        answer_text = "".join(answer_parts)
                    # Citation 后处理：归一化格式变体、剔除越界编号、句内去重
                    num_sources = len(data.get("sources", [])) if isinstance(data, dict) else 0
                    normalized_answer = postprocess_citations(answer_text, num_sources)
                    title = None
                    thinking = "".join(reasoning_parts)
                    data = {
                        **data,
                        "groundedness": result.groundedness,
                        "normalized_answer": normalized_answer,
                    }
                    if thinking:
                        data["thinking"] = thinking
                    data = _external_done_payload(
                        data,
                        question_type=analysis.question_type.value
                        if analysis.question_type else data.get("question_type"),
                        groundedness=result.groundedness,
                        title=title,
                    )
                    if _uses_external_session(req):
                        title = await _add_conversation_turn(
                            conv_mgr,
                            conv.conversation_id,
                            req.question,
                            normalized_answer,
                            sources=data.get("sources", []),
                            related_refs=data.get("relatedRefs", []),
                            retrieval_context=data.get("retrievalContext")
                            or data.get("retrieval_context"),
                            question_type=data.get("questionType"),
                            engineering_context=data.get("engineeringContext")
                            or data.get("engineering_context"),
                            answer_mode=data.get("answerMode"),
                            groundedness=data.get("groundedness"),
                            thinking=thinking or None,
                            response_payload=data,
                        )
                        data["title"] = title
                yield {"event": event_type, "data": json.dumps(data, ensure_ascii=False)}
        except Exception:
            logger.exception("stream_pipeline_failed")
            yield {
                "event": "error",
                "data": json.dumps(
                    {"code": 503, "message": "处理请求时发生内部错误，请重试"},
                    ensure_ascii=False,
                ),
            }
        finally:
            flush_current_recorder()
            reset_current_recorder(token)

    return EventSourceResponse(event_generator())
