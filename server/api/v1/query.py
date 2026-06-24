"""POST /api/v1/query — main Q&A endpoint with optional SSE streaming."""

from __future__ import annotations

import asyncio
import json
import re
import time

import structlog
from fastapi import APIRouter, Depends
from sse_starlette.sse import EventSourceResponse

from server.agents.orchestrator import (
    AgentProgress,
    AgentResult,
    dispatch_agent,
    dispatch_agent_streamed,
)
from server.api.v1._progress import (
    _agent_stage_summary,
    _commentary_sse_event,
    _error_sse_event,
    _progress_sse_event,
    _retrieval_summary,
    _tool_progress_sse_event,
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
    get_kb_database,
    get_retriever,
)
from server.config import ServerConfig
from server.core.query_request import uses_external_session
from server.errors import LLMUnavailableError, QAError, RetrievalUnavailableError
from server.models.schemas import QueryRequest, QueryResponse
from server.services.kb_database import KBDatabase
from server.agents.tool_progress import ToolSubStep
from shared.spot_check import (
    SpotCheckRecorder,
    flush_current_recorder,
    is_spot_check_enabled,
    reset_current_recorder,
    set_current_recorder,
)

router = APIRouter()
logger = structlog.get_logger(__name__)

_TOOL_TITLES = {
    "retrieve": "检索规范知识库",
    "lookup_glossary": "查询术语表",
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


def _source_aliases_for_doc_id(doc_id: str) -> list[str]:
    aliases = [
        doc_id,
        doc_id.replace("_", " "),
        doc_id.replace("-", " "),
        doc_id.replace("_", " ").replace("-", " "),
    ]
    return list(dict.fromkeys(alias for alias in aliases if alias.strip()))


def _normalize_source_lookup(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


async def _indexed_sources_by_doc_id(
    doc_ids: list[str],
    retriever: object,
) -> list[str]:
    if not doc_ids:
        return []

    alias_map: dict[str, set[str]] = {}
    for doc_id in doc_ids:
        for alias in _source_aliases_for_doc_id(doc_id):
            alias_map.setdefault(_normalize_source_lookup(alias), set()).add(doc_id)

    get_es = getattr(retriever, "_get_es", None)
    config = getattr(retriever, "config", None)
    if get_es is None or config is None:
        return []

    try:
        es = await get_es()
        resp = await es.search(
            index=config.es_index,
            body={
                "size": 0,
                "aggs": {"sources": {"terms": {"field": "source", "size": 2000}}},
            },
        )
    except Exception as exc:
        logger.warning(
            "kb_indexed_sources_lookup_failed",
            error_type=type(exc).__name__,
            error=str(exc),
        )
        return []

    matched: list[str] = []
    seen: set[str] = set()
    buckets = resp.get("aggregations", {}).get("sources", {}).get("buckets", [])
    for bucket in buckets:
        source = str(bucket.get("key") or "").strip()
        if not source:
            continue
        if _normalize_source_lookup(source) not in alias_map or source in seen:
            continue
        seen.add(source)
        matched.append(source)
    return matched


async def _resolve_kb_sources(
    req: QueryRequest,
    kb_db: KBDatabase,
    retriever: object | None = None,
) -> list[str] | None:
    """Resolve selected knowledge-base ids into indexed document source ids."""
    kb_ids = [kb_id.strip() for kb_id in req.kb_ids if kb_id.strip()]
    if not kb_ids:
        return None
    doc_ids = await kb_db.get_doc_ids_for_kbs(kb_ids)
    if not doc_ids:
        return ["__kb_scope_no_documents__"]

    indexed_sources = (
        await _indexed_sources_by_doc_id(doc_ids, retriever)
        if retriever is not None
        else []
    )
    if indexed_sources:
        return indexed_sources

    fallback_sources: list[str] = []
    for doc_id in doc_ids:
        fallback_sources.extend(_source_aliases_for_doc_id(doc_id))
    return fallback_sources or ["__kb_scope_no_documents__"]


def _source_filter_kwargs(sources_filter: list[str] | None) -> dict[str, list[str]]:
    return {"sources_filter": sources_filter} if sources_filter is not None else {}


@router.post("/query", response_model=QueryResponse)
async def query(
    req: QueryRequest,
    config=Depends(get_config),
    retriever=Depends(get_retriever),
    glossary=Depends(get_glossary),
    conv_mgr=Depends(get_conversation_manager),
    kb_db: KBDatabase = Depends(get_kb_database),
) -> QueryResponse:
    runtime_config = _resolve_runtime_config(config, req)
    sources_filter = await _resolve_kb_sources(req, kb_db, retriever)
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
            **_source_filter_kwargs(sources_filter),
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
    except (LLMUnavailableError, RetrievalUnavailableError, QAError) as exc:
        logger.error(
            "query_qa_error",
            error_type=type(exc).__name__,
            detail=str(exc),
        )
        return QueryResponse(
            answer=f"抱歉，{exc.message}",
            sources=[],
            related_refs=[],
            confidence="low",
            conversation_id=req.session_id or req.conversation_id or "",
            degraded=True,
            retrieval_context=None,
            question_type=None,
            engineering_context=None,
            groundedness=None,
        )
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
    kb_db: KBDatabase = Depends(get_kb_database),
):
    """SSE 流式问答端点，逐步返回 LLM 生成的回答片段。"""
    runtime_config = _resolve_runtime_config(config, req)
    sources_filter = await _resolve_kb_sources(req, kb_db, retriever)

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
                agent_result: AgentResult | None = None
                tool_step_queue: asyncio.Queue[ToolSubStep] = asyncio.Queue(maxsize=100)

                class QueueToolProgress:
                    async def on_tool_sub_step(self, step: ToolSubStep) -> None:
                        try:
                            tool_step_queue.put_nowait(step)
                        except asyncio.QueueFull:
                            try:
                                tool_step_queue.get_nowait()
                            except asyncio.QueueEmpty:
                                pass
                            tool_step_queue.put_nowait(step)

                async def agent_items():
                    async for agent_item in dispatch_agent_streamed(
                        question=req.question,
                        req=req,
                        config=runtime_config,
                        retriever=retriever,
                        glossary=glossary,
                        conv_mgr=conv_mgr,
                        tool_progress=QueueToolProgress(),
                        **_source_filter_kwargs(sources_filter),
                    ):
                        yield agent_item

                async for item in _merge_agent_and_tool_progress(
                    agent_items(),
                    tool_step_queue,
                ):
                    if isinstance(item, ToolSubStep):
                        yield _tool_progress_sse_event(item, started_at)
                        continue
                    if isinstance(item, AgentProgress):
                        for event in _agent_progress_sse_events(
                            item,
                            started_at=started_at,
                        ):
                            yield event
                        continue
                    agent_result = item

                if agent_result is None:
                    raise LLMUnavailableError("agent 未返回结果，请重试")

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


def _agent_progress_sse_events(
    item: AgentProgress,
    *,
    started_at: float,
) -> list[dict[str, str]]:
    """Convert one agent progress item to SSE payloads."""
    event = item.event
    if event.kind == "thinking":
        return [
            _progress_sse_event(
                stage="agent_thinking",
                status="running",
                title="分析问题",
                summary=event.summary or "Agent 正在推理...",
                started_at=started_at,
            )
        ]

    if event.kind == "tool_calling":
        stage = _tool_stage(event.tool_name)
        summary = event.summary or "正在调用工具..."
        return [
            _progress_sse_event(
                stage=stage,
                status="running",
                title=_tool_title(event.tool_name),
                summary=summary,
                started_at=started_at,
                facts=_tool_progress_facts(event),
            ),
            _commentary_sse_event(summary, started_at),
        ]

    if event.kind == "tool_result":
        return [
            _progress_sse_event(
                stage=_tool_stage(event.tool_name),
                status="completed",
                title=_tool_title(event.tool_name),
                summary=event.summary or "工具执行完成。",
                started_at=started_at,
                facts=_tool_progress_facts(event),
            )
        ]

    if event.kind == "commentary" and event.summary:
        return [_commentary_sse_event(event.summary, started_at)]

    return []


async def _merge_agent_and_tool_progress(
    agent_items,
    tool_step_queue: asyncio.Queue[ToolSubStep],
):
    agent_done = False
    pending_agent = asyncio.create_task(anext(agent_items, None))
    pending_tool = asyncio.create_task(tool_step_queue.get())
    try:
        while True:
            pending = [pending_tool]
            if not agent_done:
                pending.append(pending_agent)
            done, _ = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)

            if pending_tool in done:
                yield pending_tool.result()
                pending_tool = asyncio.create_task(tool_step_queue.get())

            if pending_agent in done:
                item = pending_agent.result()
                if item is None:
                    agent_done = True
                    while not tool_step_queue.empty():
                        yield tool_step_queue.get_nowait()
                    break
                yield item
                pending_agent = asyncio.create_task(anext(agent_items, None))
    finally:
        for task in (pending_agent, pending_tool):
            if not task.done():
                task.cancel()


def _tool_stage(tool_name: str | None) -> str:
    return f"tool:{tool_name}" if tool_name else "tool_call"


def _tool_title(tool_name: str | None) -> str:
    if tool_name:
        return _TOOL_TITLES.get(tool_name, f"调用 {tool_name}")
    return "调用工具"


def _tool_progress_facts(event) -> dict[str, object]:
    facts: dict[str, object] = {}
    if event.tool_name:
        facts["tool_name"] = event.tool_name

    tool_args = event.tool_args or {}
    raw_arguments = tool_args.get("arguments")
    parsed_arguments = (
        _parse_json_object(raw_arguments) if isinstance(raw_arguments, str) else None
    )
    if parsed_arguments:
        facts["tool_args"] = parsed_arguments
    elif tool_args:
        facts["tool_args"] = tool_args

    call_id = tool_args.get("call_id")
    if call_id:
        facts["tool_call_id"] = call_id

    if event.tool_result:
        facts["tool_result"] = event.tool_result
    if event.tool_trace:
        facts["tool_trace"] = event.tool_trace
    return facts


def _parse_json_object(value: object) -> dict[str, object] | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None
