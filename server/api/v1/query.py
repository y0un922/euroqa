"""POST /api/v1/query — main Q&A endpoint with optional SSE streaming."""

from __future__ import annotations

import asyncio
import time

import structlog
from fastapi import APIRouter, Depends
from sse_starlette.sse import EventSourceResponse

from server.agents.orchestrator import dispatch_agent
from server.api.v1._progress import (
    _agent_stage_summary,
    _error_sse_event,
    _progress_sse_event,
    _retrieval_summary,
)
from server.api.v1._response import (
    _add_conversation_turn,
    _build_query_response,
    _record_agent_spot_check,
    _stream_direct_agent_events,
    _stream_rag_answer_events,
)
from server.deps import (
    get_config,
    get_conversation_manager,
    get_glossary,
    get_retriever,
)
from server.config import ServerConfig
from server.core.query_request import uses_external_session
from server.errors import LLMUnavailableError, QAError, RetrievalUnavailableError
from server.models.schemas import QueryRequest, QueryResponse
from shared.spot_check import (
    SpotCheckRecorder,
    flush_current_recorder,
    is_spot_check_enabled,
    reset_current_recorder,
    set_current_recorder,
)

router = APIRouter()
logger = structlog.get_logger(__name__)


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
    recorder = (
        SpotCheckRecorder(query=req.question) if is_spot_check_enabled() else None
    )
    token = set_current_recorder(recorder)
    try:
        agent_result = await dispatch_agent(
            question=req.question,
            req=req,
            config=runtime_config,
            retriever=retriever,
            glossary=glossary,
            conv_mgr=conv_mgr,
        )
        agent_reply = agent_result.agent_reply
        bundle = agent_result.bundle
        conv = agent_result.conv
        _record_agent_spot_check(recorder, bundle)

        response, answer_mode = await _build_query_response(
            req=req,
            runtime_config=runtime_config,
            config=config,
            agent_reply=agent_reply,
            bundle=bundle,
            conv=conv,
            uses_external_session=uses_external_session(req),
        )

        if uses_external_session(req):
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
                answer_mode=answer_mode,
                groundedness=response.groundedness,
                tool_trace=bundle.tool_trace,
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
        final_mode: str | None = None
        final_groundedness: str | None = None
        recorder = (
            SpotCheckRecorder(query=req.question) if is_spot_check_enabled() else None
        )
        token = set_current_recorder(recorder)
        try:
            async with asyncio.timeout(runtime_config.request_deadline_seconds):
                logger.info(
                    "query_start",
                    question=req.question[:100],
                    session_id=req.session_id,
                )
                yield _progress_sse_event(
                    stage="agent_thinking",
                    status="running",
                    title="分析问题",
                    summary="Agent 正在理解问题并决定策略...",
                    started_at=started_at,
                )
                agent_t0 = time.perf_counter()
                agent_result = await dispatch_agent(
                    question=req.question,
                    req=req,
                    config=runtime_config,
                    retriever=retriever,
                    glossary=glossary,
                    conv_mgr=conv_mgr,
                )
                agent_reply = agent_result.agent_reply
                bundle = agent_result.bundle
                conv = agent_result.conv
                logger.info(
                    "agent_end",
                    needs_rag=agent_result.needs_rag,
                    tool_calls=len(bundle.tool_trace),
                    duration_ms=int((time.perf_counter() - agent_t0) * 1000),
                )
                final_mode = "rag" if agent_result.needs_rag else "direct"
                _record_agent_spot_check(recorder, bundle)
                summary, facts = _agent_stage_summary(bundle)
                yield _progress_sse_event(
                    stage="agent_thinking",
                    status="completed",
                    title="分析问题",
                    summary=summary,
                    started_at=started_at,
                    facts=facts,
                )

                if not agent_result.needs_rag:
                    async for event in _stream_direct_agent_events(
                        req=req,
                        conv_mgr=conv_mgr,
                        conv=conv,
                        agent_reply=agent_reply,
                        bundle=bundle,
                        started_at=started_at,
                        uses_external_session=uses_external_session(req),
                    ):
                        yield event
                    return

                logger.info(
                    "retrieve_end",
                    chunk_count=len(bundle.chunks),
                    ref_chunk_count=len(bundle.ref_chunks),
                    groundedness=bundle.groundedness,
                )
                summary, facts = _retrieval_summary(bundle)
                yield _progress_sse_event(
                    stage="retrieving",
                    status="completed",
                    title="检索规范条文",
                    summary=summary,
                    started_at=started_at,
                    facts=facts,
                )

                yield _progress_sse_event(
                    stage="generating",
                    status="running",
                    title="生成回答",
                    summary="正在基于检索证据组织回答...",
                    started_at=started_at,
                    facts={
                        "evidence_count": len(bundle.chunks) + len(bundle.ref_chunks),
                        "guide_count": len(bundle.guide_chunks),
                        "example_count": len(bundle.guide_example_chunks),
                    },
                )

                async for event_type, data, groundedness in _stream_rag_answer_events(
                    req=req,
                    runtime_config=runtime_config,
                    config=config,
                    conv_mgr=conv_mgr,
                    conv=conv,
                    bundle=bundle,
                    uses_external_session=uses_external_session(req),
                ):
                    if groundedness is not None:
                        final_groundedness = groundedness
                    yield {
                        "event": event_type,
                        "data": data,
                    }
        except asyncio.TimeoutError:
            logger.error("stream_request_timeout", error_type="timeout")
            yield _error_sse_event(
                code=504,
                message="请求处理超时，请简化问题或稍后重试",
            )
        except (LLMUnavailableError, RetrievalUnavailableError, QAError) as e:
            logger.error(
                "stream_qa_error",
                error_type=type(e).__name__,
                detail=str(e),
            )
            yield _error_sse_event(code=e.code, message=e.message)
        except Exception:
            logger.exception("stream_pipeline_failed")
            yield _error_sse_event(
                code=503,
                message="处理请求时发生内部错误，请重试",
            )
        finally:
            logger.info(
                "query_end",
                total_ms=int((time.perf_counter() - started_at) * 1000),
                mode=final_mode,
                groundedness=final_groundedness,
            )
            flush_current_recorder()
            reset_current_recorder(token)

    return EventSourceResponse(event_generator())
