"""POST /api/v1/query — main Q&A endpoint with optional SSE streaming."""
from __future__ import annotations

import json
import time

import structlog
from fastapi import APIRouter, Depends
from sse_starlette.sse import EventSourceResponse

from server.config import ServerConfig
from server.deps import get_config, get_conversation_manager, get_glossary, get_retriever
from server.core.query_understanding import analyze_query
from server.core.generation import generate_answer, generate_answer_stream
from server.models.schemas import QueryRequest, QueryResponse

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


def _camelize_source_payload(source: dict) -> dict:
    """Add interface-document camelCase aliases while preserving old keys."""
    aliases = {
        "document_id": "docId",
        "element_type": "elementType",
        "original_text": "originalText",
        "locator_text": "locatorText",
        "highlight_text": "highlightText",
    }
    payload = dict(source)
    for old_key, new_key in aliases.items():
        if old_key in source:
            payload[new_key] = source[old_key]
    return payload


def _external_done_payload(
    data: dict,
    *,
    question_type: str | None,
    answer_mode: str | None,
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
        "questionType": question_type or data.get("question_type"),
        "answerMode": answer_mode,
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
    analysis = await analyze_query(req.question, glossary, runtime_config)

    filters = analysis.filters
    if req.domain:
        filters["source"] = req.domain

    result = await retriever.retrieve(
        queries=analysis.expanded_queries,
        original_query=analysis.original_question,
        filters=filters,
        answer_mode=analysis.answer_mode.value if analysis.answer_mode else None,
        intent_label=analysis.intent_label,
        question_type=analysis.question_type.value if analysis.question_type else None,
        guide_hint=analysis.guide_hint,
        target_hint=analysis.target_hint,
        requested_objects=analysis.requested_objects,
        preferred_element_type=analysis.preferred_element_type,
    )

    conv = conv_mgr.get_or_create(_conversation_id_from_request(req))

    response = await generate_answer(
        question=req.question,
        chunks=result.chunks,
        parent_chunks=result.parent_chunks,
        scores=result.scores,
        glossary_terms=analysis.matched_terms,
        conversation_history=[],
        config=runtime_config,
        ref_chunks=result.ref_chunks,
        guide_chunks=result.guide_chunks,
        guide_example_chunks=result.guide_example_chunks,
        question_type=analysis.question_type,
        engineering_context=analysis.engineering_context,
        answer_mode=analysis.answer_mode.value if analysis.answer_mode else None,
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
            "answer_mode": analysis.answer_mode.value if analysis.answer_mode else None,
            "groundedness": result.groundedness,
        }
    )

    return response


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
                answer_mode=analysis.answer_mode.value if analysis.answer_mode else None,
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

            conv_mgr.get_or_create(_conversation_id_from_request(req))
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

            async for event_type, data in generate_answer_stream(
                question=req.question,
                chunks=result.chunks,
                parent_chunks=result.parent_chunks,
                scores=result.scores,
                glossary_terms=analysis.matched_terms,
                conversation_history=[],
                config=runtime_config,
                ref_chunks=result.ref_chunks,
                guide_chunks=result.guide_chunks,
                guide_example_chunks=result.guide_example_chunks,
                question_type=analysis.question_type,
                engineering_context=analysis.engineering_context,
                answer_mode=analysis.answer_mode.value if analysis.answer_mode else None,
                groundedness=result.groundedness,
                resolved_refs=result.resolved_refs,
                unresolved_refs=result.unresolved_refs,
                intent_label=analysis.intent_label,
            ):
                if event_type == "done":
                    data = {
                        **data,
                        "answer_mode": analysis.answer_mode.value if analysis.answer_mode else None,
                        "groundedness": result.groundedness,
                    }
                    data = _external_done_payload(
                        data,
                        question_type=analysis.question_type.value
                        if analysis.question_type else data.get("question_type"),
                        answer_mode=analysis.answer_mode.value
                        if analysis.answer_mode else None,
                        groundedness=result.groundedness,
                        title=None,
                    )
                yield {"event": event_type, "data": json.dumps(data, ensure_ascii=False)}
        except Exception:
            logger.exception("stream_pipeline_failed")
            yield {
                "event": "error",
                "data": json.dumps(
                    {"message": "处理请求时发生内部错误，请重试"},
                    ensure_ascii=False,
                ),
            }

    return EventSourceResponse(event_generator())
