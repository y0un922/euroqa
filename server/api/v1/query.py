"""POST /api/v1/query — main Q&A endpoint with optional SSE streaming."""

from __future__ import annotations

import json
import inspect
import time

from agents import Agent
import structlog
from fastapi import APIRouter, Depends
from sse_starlette.sse import EventSourceResponse
from structlog.contextvars import get_contextvars

from server.agents.deps import QADeps
from server.agents.evidence import EvidenceBundle
from server.agents.qa_agent import AgentDecision, build_qa_agent, run_qa_agent
from server.config import ServerConfig
from server.deps import (
    get_config,
    get_conversation_manager,
    get_glossary,
    get_retriever,
)
from server.core.conversation import ConversationState
from server.core.generation import (
    generate_answer,
    generate_answer_stream,
    postprocess_citations,
)
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

_qa_agent: Agent[QADeps] | None = None


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


async def _get_conversation_state(
    conv_mgr: object, conversation_id: str | None
) -> object:
    """Load conversation state from sync or async managers."""
    getter = getattr(conv_mgr, "get_or_create_async", None)
    if getter is not None:
        return await getter(conversation_id)
    return conv_mgr.get_or_create(conversation_id)


def _get_or_build_agent(config: ServerConfig) -> Agent[QADeps]:
    """Return the lazily constructed QA agent."""
    global _qa_agent
    if _qa_agent is None:
        _qa_agent = build_qa_agent(config)
    return _qa_agent


def _conversation_state_for_agent(
    conv: object,
    req: QueryRequest,
) -> ConversationState:
    """Build the agent-facing conversation state from the loaded session."""
    history = (
        list(getattr(conv, "history", []) or []) if _uses_external_session(req) else []
    )
    return ConversationState(
        conversation_id=getattr(conv, "conversation_id"),
        history=history,
    )


def _build_agent_deps(
    *,
    runtime_config: ServerConfig,
    retriever: object,
    glossary: dict[str, str],
    conv: object,
    req: QueryRequest,
) -> QADeps:
    """Build request-scoped dependencies for agent tool execution."""
    return QADeps(
        config=runtime_config,
        retriever=retriever,
        glossary=glossary,
        bundle=EvidenceBundle(),
        conversation_state=_conversation_state_for_agent(conv, req),
        domain_filter=req.domain,
    )


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
        "request_id": get_contextvars().get("request_id", ""),
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
        summary = (
            f"找到 {evidence_count} 条相关规范证据，覆盖 {source_count} 个文档来源。"
        )
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


async def _run_agent_dispatch(
    *,
    req: QueryRequest,
    runtime_config: ServerConfig,
    retriever: object,
    glossary: dict[str, str],
    conv_mgr: object,
) -> tuple[AgentDecision, EvidenceBundle, object, QADeps]:
    """Run the QA agent and return its decision, evidence bundle, session, and deps."""
    conv = await _get_conversation_state(conv_mgr, _conversation_id_from_request(req))
    deps = _build_agent_deps(
        runtime_config=runtime_config,
        retriever=retriever,
        glossary=glossary,
        conv=conv,
        req=req,
    )
    agent = _get_or_build_agent(runtime_config)
    decision, bundle = await run_qa_agent(agent, req.question, deps, max_turns=5)
    return decision, bundle, conv, deps


async def _ensure_retrieve_called_for_compose_rag(
    *,
    decision: AgentDecision,
    bundle: EvidenceBundle,
    deps: QADeps,
    question: str,
    conversation_id: str,
) -> AgentDecision:
    """Catch the 'compose_rag without retrieve' agent state and recover.

    The agent prompt forbids returning compose_rag without first calling
    retrieve, but LLMs can still skip the tool when conversation history
    already contains a prior answer to the same question (history-shortcut
    bug). When that happens the bundle is empty, generation produces a
    fallback "no evidence" answer, and the user sees zero citations.

    This guard runs after the agent returns and before dispatch:
      * If decision != compose_rag -> no-op.
      * If decision == compose_rag and bundle.tool_trace has no retrieve
        entry -> force one retrieve call using the user's original question.
      * If post-retry the bundle is still empty -> downgrade decision to
        clarify with an explicit user-facing hint.
    """
    if decision.action != "compose_rag":
        return decision

    retrieve_called = any(
        entry.get("tool") == "retrieve" for entry in bundle.tool_trace
    )
    if retrieve_called:
        return decision

    logger.warning(
        "agent_compose_rag_without_retrieve",
        conversation_id=conversation_id,
        question=question,
    )

    from agents import RunContextWrapper
    from server.agents.tools.retrieve import _retrieve_impl

    try:
        await _retrieve_impl(RunContextWrapper(deps), question)
    except Exception:
        logger.exception(
            "agent_compose_rag_recovery_retrieve_failed",
            conversation_id=conversation_id,
        )

    if bundle.is_empty:
        return AgentDecision(
            action="clarify",
            direct_reply=(
                "抱歉，本次未检索到与您问题相关的规范条文，"
                "请补充规范号、构件类型或参数名称后重试。"
            ),
        )
    return decision


def _agent_stage_summary(
    decision: AgentDecision, bundle: EvidenceBundle
) -> tuple[str, dict]:
    """Summarize the agent decision for progress payloads."""
    facts: dict[str, object] = {"action": decision.action}
    if decision.action == "compose_rag":
        facts["chunk_count"] = bundle.chunk_count
        summary = f"已确认为规范问题，检索到 {bundle.chunk_count} 条证据。"
    elif decision.action == "clarify":
        summary = "识别为模糊问题，已请求用户补充关键信息。"
    else:
        summary = "识别为闲聊或上下文充足问题，直接生成简短回复。"
    return summary, facts


def _build_agent_chat_payload(
    *,
    decision: AgentDecision,
    bundle: EvidenceBundle,
    groundedness: str | None = None,
) -> dict[str, object]:
    """Build the external payload for chat/clarify agent responses."""
    answer_mode = decision.action
    confidence = "high"
    return {
        "answer": decision.direct_reply or "",
        "sources": [],
        "related_refs": [],
        "confidence": confidence,
        "retrieval_context": {
            "chunks": [],
            "parent_chunks": [],
            "guide_chunks": [],
            "guide_example_chunks": [],
            "ref_chunks": [],
            "resolved_refs": [],
            "unresolved_refs": [],
        },
        "question_type": None,
        "engineering_context": None,
        "groundedness": groundedness,
        "answerMode": answer_mode,
        "tool_trace": bundle.tool_trace,
    }


def _record_agent_spot_check(
    recorder: SpotCheckRecorder | None,
    decision: AgentDecision,
    bundle: EvidenceBundle,
) -> None:
    """Record agent-mode query signals without running query understanding twice."""
    if recorder is None:
        return
    recorder.record("expanded_queries", {"queries": []})
    recorder.record(
        "query_signals",
        {
            "agent_action": decision.action,
            "chunk_count": bundle.chunk_count,
            "exact_refs": [],
            "procedural_cues": False,
        },
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
        decision, bundle, conv, deps = await _run_agent_dispatch(
            req=req,
            runtime_config=runtime_config,
            retriever=retriever,
            glossary=glossary,
            conv_mgr=conv_mgr,
        )
        decision = await _ensure_retrieve_called_for_compose_rag(
            decision=decision,
            bundle=bundle,
            deps=deps,
            question=req.question,
            conversation_id=conv.conversation_id,
        )
        _record_agent_spot_check(recorder, decision, bundle)

        if decision.action == "compose_rag":
            history = (
                list(getattr(conv, "history", []) or [])[
                    -config.max_conversation_rounds :
                ]
                if _uses_external_session(req)
                else []
            )
            response = await generate_answer(
                question=req.question,
                chunks=bundle.chunks,
                parent_chunks=bundle.parent_chunks,
                scores=bundle.scores,
                glossary_terms=bundle.glossary_hits,
                conversation_history=history,
                config=runtime_config,
                ref_chunks=bundle.ref_chunks,
                guide_chunks=bundle.guide_chunks,
                guide_example_chunks=bundle.guide_example_chunks,
                groundedness=bundle.groundedness,
                resolved_refs=bundle.resolved_refs,
                unresolved_refs=bundle.unresolved_refs,
            )
            response = response.model_copy(
                update={
                    "conversation_id": conv.conversation_id,
                    "groundedness": bundle.groundedness,
                }
            )
            answer_mode = _answer_mode_from_groundedness(response.groundedness)
        else:
            response = QueryResponse(
                answer=decision.direct_reply or "",
                sources=[],
                related_refs=[],
                confidence="high",
                conversation_id=conv.conversation_id,
                degraded=False,
                retrieval_context=RetrievalContext(),
                question_type=None,
                engineering_context=None,
                groundedness=None,
            )
            answer_mode = decision.action

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
        final_action: str | None = None
        final_groundedness: str | None = None
        recorder = (
            SpotCheckRecorder(query=req.question) if is_spot_check_enabled() else None
        )
        token = set_current_recorder(recorder)
        try:
            logger.info(
                "query_start",
                question=req.question[:100],
                session_id=req.session_id,
            )
            yield {
                "event": "progress",
                "data": json.dumps(
                    _progress_event(
                        stage="agent_thinking",
                        status="running",
                        title="分析问题",
                        summary="Agent 正在理解问题并决定策略...",
                        started_at=started_at,
                    ),
                    ensure_ascii=False,
                ),
            }
            agent_t0 = time.perf_counter()
            decision, bundle, conv, deps = await _run_agent_dispatch(
                req=req,
                runtime_config=runtime_config,
                retriever=retriever,
                glossary=glossary,
                conv_mgr=conv_mgr,
            )
            decision = await _ensure_retrieve_called_for_compose_rag(
                decision=decision,
                bundle=bundle,
                deps=deps,
                question=req.question,
                conversation_id=conv.conversation_id,
            )
            logger.info(
                "agent_end",
                action=decision.action,
                tool_calls=len(bundle.tool_trace),
                duration_ms=int((time.perf_counter() - agent_t0) * 1000),
            )
            final_action = decision.action
            _record_agent_spot_check(recorder, decision, bundle)
            summary, facts = _agent_stage_summary(decision, bundle)
            yield {
                "event": "progress",
                "data": json.dumps(
                    _progress_event(
                        stage="agent_thinking",
                        status="completed",
                        title="分析问题",
                        summary=summary,
                        started_at=started_at,
                        facts=facts,
                    ),
                    ensure_ascii=False,
                ),
            }

            if decision.action != "compose_rag":
                payload = _build_agent_chat_payload(decision=decision, bundle=bundle)
                yield {
                    "event": "progress",
                    "data": json.dumps(
                        _progress_event(
                            stage=decision.action,
                            status="completed",
                            title="生成回复",
                            summary="Agent 已生成直接回复。",
                            started_at=started_at,
                            facts={"action": decision.action},
                        ),
                        ensure_ascii=False,
                    ),
                }
                yield {
                    "event": "chunk",
                    "data": json.dumps(
                        {"text": decision.direct_reply or "", "done": False},
                        ensure_ascii=False,
                    ),
                }
                data = _external_done_payload(
                    payload,
                    question_type=None,
                    groundedness=None,
                    title=None,
                    answer_mode=decision.action,
                )
                data["request_id"] = get_contextvars().get("request_id", "")
                if _uses_external_session(req):
                    title = await _add_conversation_turn(
                        conv_mgr,
                        conv.conversation_id,
                        req.question,
                        str(data.get("answer") or ""),
                        sources=[],
                        related_refs=[],
                        retrieval_context=data.get("retrievalContext")
                        or data.get("retrieval_context"),
                        question_type=None,
                        answer_mode=decision.action,
                        tool_trace=bundle.tool_trace,
                        response_payload=data,
                    )
                    data["title"] = title
                yield {"event": "done", "data": json.dumps(data, ensure_ascii=False)}
                return

            logger.info(
                "retrieve_end",
                chunk_count=len(bundle.chunks),
                ref_chunk_count=len(bundle.ref_chunks),
                groundedness=bundle.groundedness,
            )
            summary, facts = _retrieval_summary(bundle)
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
                            "evidence_count": len(bundle.chunks)
                            + len(bundle.ref_chunks),
                            "guide_count": len(bundle.guide_chunks),
                            "example_count": len(bundle.guide_example_chunks),
                        },
                    ),
                    ensure_ascii=False,
                ),
            }

            generate_t0 = time.perf_counter()
            answer_parts: list[str] = []
            reasoning_parts: list[str] = []
            history = (
                list(getattr(conv, "history", []) or [])[
                    -config.max_conversation_rounds :
                ]
                if _uses_external_session(req)
                else []
            )
            async for event_type, data in generate_answer_stream(
                question=req.question,
                chunks=bundle.chunks,
                parent_chunks=bundle.parent_chunks,
                scores=bundle.scores,
                glossary_terms=bundle.glossary_hits,
                conversation_history=history,
                config=runtime_config,
                ref_chunks=bundle.ref_chunks,
                guide_chunks=bundle.guide_chunks,
                guide_example_chunks=bundle.guide_example_chunks,
                groundedness=bundle.groundedness,
                resolved_refs=bundle.resolved_refs,
                unresolved_refs=bundle.unresolved_refs,
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
                    logger.info(
                        "generate_end",
                        duration_ms=int(
                            (time.perf_counter() - generate_t0) * 1000
                        ),
                    )
                    answer_text = data.get("answer") if isinstance(data, dict) else None
                    if not isinstance(answer_text, str):
                        answer_text = "".join(answer_parts)
                    # Citation 后处理：归一化格式变体、剔除越界编号、句内去重
                    num_sources = (
                        len(data.get("sources", [])) if isinstance(data, dict) else 0
                    )
                    normalized_answer = postprocess_citations(answer_text, num_sources)
                    title = None
                    thinking = "".join(reasoning_parts)
                    final_groundedness = bundle.groundedness
                    data = {
                        **data,
                        "groundedness": bundle.groundedness,
                        "normalized_answer": normalized_answer,
                    }
                    if thinking:
                        data["thinking"] = thinking
                    data = _external_done_payload(
                        data,
                        question_type=data.get("question_type"),
                        groundedness=bundle.groundedness,
                        title=title,
                    )
                    data["request_id"] = get_contextvars().get("request_id", "")
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
                            tool_trace=bundle.tool_trace,
                            response_payload=data,
                        )
                        data["title"] = title
                yield {
                    "event": event_type,
                    "data": json.dumps(data, ensure_ascii=False),
                }
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
            logger.info(
                "query_end",
                total_ms=int((time.perf_counter() - started_at) * 1000),
                action=final_action,
                groundedness=final_groundedness,
            )
            flush_current_recorder()
            reset_current_recorder(token)

    return EventSourceResponse(event_generator())
