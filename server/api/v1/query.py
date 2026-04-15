"""POST /api/v1/query — main Q&A endpoint with optional SSE streaming."""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends
from sse_starlette.sse import EventSourceResponse

from server.config import ServerConfig
from server.deps import get_config, get_conversation_manager, get_glossary, get_retriever
from server.core.query_understanding import analyze_query
from server.core.generation import generate_answer, generate_answer_stream
from server.models.schemas import QueryRequest, QueryResponse

router = APIRouter()


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
        target_hint=analysis.target_hint,
        requested_objects=analysis.requested_objects,
        preferred_element_type=analysis.preferred_element_type,
    )

    conv = conv_mgr.get_or_create(req.conversation_id)

    response = await generate_answer(
        question=req.question,
        chunks=result.chunks,
        parent_chunks=result.parent_chunks,
        scores=result.scores,
        glossary_terms=analysis.matched_terms,
        conversation_history=[],
        config=runtime_config,
        ref_chunks=result.ref_chunks,
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
        target_hint=analysis.target_hint,
        requested_objects=analysis.requested_objects,
        preferred_element_type=analysis.preferred_element_type,
    )

    conv_mgr.get_or_create(req.conversation_id)

    async def event_generator():
        async for event_type, data in generate_answer_stream(
            question=req.question,
            chunks=result.chunks,
            parent_chunks=result.parent_chunks,
            scores=result.scores,
            glossary_terms=analysis.matched_terms,
            conversation_history=[],
            config=runtime_config,
            ref_chunks=result.ref_chunks,
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
            yield {"event": event_type, "data": json.dumps(data, ensure_ascii=False)}

    return EventSourceResponse(event_generator())
