"""Agent lifecycle orchestration for query endpoints."""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass

from agents import Agent
from agents.exceptions import ModelBehaviorError
from openai import APIConnectionError, APITimeoutError, InternalServerError
import structlog

from server.agents.decompose import (
    DecomposedQuery,
    assess_evidence,
    decompose_query,
    outline_answer,
)
from server.agents.deps import QADeps
from server.agents.evidence import EvidenceBundle
from server.agents.qa_agent import (
    AgentStreamEvent,
    build_qa_agent,
    run_qa_agent,
    run_qa_agent_streamed,
)
from server.agents.tool_progress import ToolProgressCallback, ToolProgressEmitter
from server.agents.tools._utils import (
    base_filters,
    limit_retrieval_result,
    merge_retrieval_filters,
)
from server.circuit_breaker import AsyncCircuitBreaker, CircuitBreakerOpenError
from server.config import ServerConfig
from server.core.conversation import ConversationState
from server.core.query_request import (
    conversation_id_from_request,
    uses_external_session,
)
from server.core.retrieval import RetrievalResult
from server.errors import LLMUnavailableError
from server.models.schemas import QueryRequest
from server.retry import with_retry

logger = structlog.get_logger(__name__)

_qa_agents: dict[str, Agent[QADeps]] = {}
_agent_semaphore: asyncio.Semaphore | None = None
_agent_circuit_breaker: AsyncCircuitBreaker | None = None
_AGENT_MAX_TURNS = 4
_DEGRADED_RAG_REPLY = "已检索到相关规范证据，正在整理回答。"
_MAX_SUPPLEMENT_ROUNDS = 2
_MAX_ASSESSMENT_EVIDENCE_CHARS = 12000


@dataclass
class AgentResult:
    agent_reply: str
    bundle: EvidenceBundle
    conv: object
    deps: QADeps
    usage: dict[str, int] | None = None

    @property
    def needs_rag(self) -> bool:
        """Return whether accumulated tool artifacts require RAG generation."""
        return self.bundle.has_rag_evidence


@dataclass(frozen=True)
class AgentProgress:
    event: AgentStreamEvent


async def _get_conversation_state(
    conv_mgr: object, conversation_id: str | None
) -> object:
    """Load conversation state from sync or async managers."""
    getter = getattr(conv_mgr, "get_or_create_async", None)
    if getter is not None:
        return await getter(conversation_id)
    return conv_mgr.get_or_create(conversation_id)


def _get_or_build_agent(config: ServerConfig) -> Agent[QADeps]:
    """Return a cached QA agent keyed by resolved agent LLM config."""
    cache_key = (
        f"{config.resolved_agent_llm_base_url}:{config.resolved_agent_llm_model}"
    )
    if cache_key not in _qa_agents:
        _qa_agents[cache_key] = build_qa_agent(config)
    return _qa_agents[cache_key]


def _get_agent_semaphore(config: ServerConfig) -> asyncio.Semaphore:
    """Return the process-local agent LLM concurrency semaphore."""
    global _agent_semaphore
    if _agent_semaphore is None:
        _agent_semaphore = asyncio.Semaphore(config.agent_max_concurrency)
    return _agent_semaphore


def _get_agent_circuit_breaker(config: ServerConfig) -> AsyncCircuitBreaker:
    """Return the process-local agent LLM circuit breaker."""
    global _agent_circuit_breaker
    if _agent_circuit_breaker is None:
        _agent_circuit_breaker = AsyncCircuitBreaker(
            failure_threshold=config.agent_circuit_breaker_failure_threshold,
            recovery_timeout_seconds=config.agent_circuit_breaker_recovery_seconds,
        )
    return _agent_circuit_breaker


def _conversation_state_for_agent(
    conv: object,
    req: QueryRequest,
) -> ConversationState:
    """Build the agent-facing conversation state from the loaded session."""
    history = (
        list(getattr(conv, "history", []) or []) if uses_external_session(req) else []
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
    sources_filter: list[str] | None = None,
    tool_progress: ToolProgressCallback | None = None,
) -> QADeps:
    """Build request-scoped dependencies for agent tool execution."""
    return QADeps(
        config=runtime_config,
        retriever=retriever,
        glossary=glossary,
        bundle=EvidenceBundle(),
        conversation_state=_conversation_state_for_agent(conv, req),
        user_question=req.question,
        domain_filter=req.domain,
        sources_filter=sources_filter,
        tool_progress=tool_progress,
    )


async def _prepare_evidence_for_agent(
    *,
    req: QueryRequest,
    deps: QADeps,
    glossary: dict[str, str],
) -> None:
    """Run route/decompose, corrective retrieval, and evidence assessment."""
    async for _event in _prepare_evidence_for_agent_streamed(
        req=req,
        deps=deps,
        glossary=glossary,
    ):
        pass


async def _prepare_evidence_for_agent_streamed(
    *,
    req: QueryRequest,
    deps: QADeps,
    glossary: dict[str, str],
) -> AsyncIterator[AgentProgress]:
    """Run corrective prefetch and emit user-facing progress events."""
    if getattr(deps.retriever, "retrieve", None) is None:
        deps.bundle.tool_trace.append(
            {"tool": "prefetch_retrieve", "skipped": True, "reason": "unsupported"}
        )
        return

    yield AgentProgress(
        event=AgentStreamEvent(
            kind="thinking",
            summary="正在判断问题是否需要检索，并生成检索子问题...",
        )
    )
    history = (
        list(deps.conversation_state.history)
        if deps.conversation_state is not None
        else []
    )
    decomposed = await decompose_query(
        req.question,
        history,
        glossary,
        deps.config,
        selected_sources=list(deps.sources_filter or []),
    )
    deps.bundle.tool_trace.append(
        {
            "tool": "decompose",
            "rewritten_question": decomposed.rewritten_question,
            "sub_queries": decomposed.sub_queries,
            "needs_retrieval": decomposed.needs_retrieval,
            "is_chitchat": decomposed.is_chitchat,
            "implicit_context": decomposed.implicit_context,
            "requested_objects": decomposed.requested_objects,
            "filters": decomposed.filters,
        }
    )
    yield AgentProgress(
        event=AgentStreamEvent(
            kind="commentary",
            summary=_decompose_summary(decomposed),
        )
    )
    if decomposed.is_chitchat or not decomposed.needs_retrieval:
        yield AgentProgress(
            event=AgentStreamEvent(
                kind="commentary",
                summary="该问题无需规范检索，直接组织回答。",
            )
        )
        return

    attempted_queries: list[str] = []
    # rewritten_question 的向量补召回只预取一次，所有轮次复用
    prefetch = getattr(deps.retriever, "prefetch_vectors", None)
    original_candidates: list[dict] | None = None
    if prefetch is not None:
        prefetch_filters = merge_retrieval_filters(
            base_filters(deps),
            decomposed.filters,
        )
        original_candidates = await prefetch(
            decomposed.rewritten_question,
            filters=prefetch_filters,
        )
    initial_top_k = _round_top_k(deps.config, len(decomposed.sub_queries))
    yield _prefetch_calling_progress(decomposed.sub_queries, initial_top_k, 1)
    await _retrieve_decomposed_queries(
        deps=deps,
        decomposed=decomposed,
        top_k=initial_top_k,
        prefetched_original_results=original_candidates,
    )
    attempted_queries.extend(_new_queries(decomposed.sub_queries, attempted_queries))
    yield _prefetch_result_progress(deps.bundle, decomposed.sub_queries, 1)

    for round_no in range(1, _MAX_SUPPLEMENT_ROUNDS + 1):
        yield AgentProgress(
            event=AgentStreamEvent(
                kind="tool_calling",
                tool_name="evidence_assessment",
                tool_args={
                    "arguments": json.dumps(
                        {
                            "round": round_no,
                            "previous_queries": attempted_queries,
                        },
                        ensure_ascii=False,
                    )
                },
                summary="正在判断现有证据是否足够回答...",
            )
        )
        assessment = await assess_evidence(
            question=req.question,
            rewritten_question=decomposed.rewritten_question,
            implicit_context=decomposed.implicit_context,
            evidence_text=_format_assessment_evidence(deps.bundle),
            previous_queries=attempted_queries,
            config=deps.config,
            selected_sources=list(deps.sources_filter or []),
            conversation_history=history,
        )
        deps.bundle.tool_trace.append(
            {
                "tool": "evidence_assessment",
                "round": round_no,
                "sufficient": assessment.sufficient,
                "missing_queries": assessment.missing_queries,
                "reason": assessment.reason,
            }
        )
        yield AgentProgress(
            event=AgentStreamEvent(
                kind="tool_result",
                tool_name="evidence_assessment",
                tool_args={
                    "arguments": json.dumps(
                        {
                            "round": round_no,
                            "previous_queries": attempted_queries,
                        },
                        ensure_ascii=False,
                    )
                },
                tool_result=json.dumps(
                    {
                        "sufficient": assessment.sufficient,
                        "missing_queries": assessment.missing_queries,
                        "reason": assessment.reason,
                    },
                    ensure_ascii=False,
                ),
                tool_trace=_latest_tool_trace(
                    deps.bundle.tool_trace,
                    "evidence_assessment",
                ),
                summary=_assessment_summary(
                    assessment.sufficient,
                    assessment.missing_queries,
                ),
            )
        )
        if assessment.sufficient or not assessment.missing_queries:
            break

        followup_queries = _new_queries(assessment.missing_queries, attempted_queries)
        if not followup_queries:
            break
        followup = DecomposedQuery(
            rewritten_question=decomposed.rewritten_question,
            sub_queries=followup_queries,
            implicit_context=decomposed.implicit_context,
            needs_retrieval=True,
            is_chitchat=False,
            requested_objects=decomposed.requested_objects,
            filters=decomposed.filters,
        )
        supplement_round = round_no + 1
        followup_top_k = _round_top_k(deps.config, len(followup.sub_queries))
        yield _prefetch_calling_progress(
            followup.sub_queries,
            followup_top_k,
            supplement_round,
        )
        await _retrieve_decomposed_queries(
            deps=deps,
            decomposed=followup,
            top_k=followup_top_k,
            prefetched_original_results=original_candidates,
        )
        attempted_queries.extend(_new_queries(followup.sub_queries, attempted_queries))
        yield _prefetch_result_progress(
            deps.bundle, followup.sub_queries, supplement_round
        )

    if deps.bundle.has_rag_evidence:
        yield AgentProgress(
            event=AgentStreamEvent(
                kind="thinking",
                summary="正在构建回答大纲...",
            )
        )
        deps.bundle.outline = await outline_answer(
            question=req.question,
            rewritten_question=decomposed.rewritten_question,
            implicit_context=decomposed.implicit_context,
            conversation_history=history,
            evidence_text=_format_assessment_evidence(deps.bundle),
            config=deps.config,
        )
        deps.bundle.tool_trace.append(
            {
                "tool": "answer_outline",
                "success": bool(deps.bundle.outline),
            }
        )


def _round_top_k(config: ServerConfig, query_count: int) -> int:
    """Per-round rerank budget: scales with sub-query count, capped by config."""
    base = config.prefetch_rerank_top_n_base
    extra = config.prefetch_rerank_top_n_per_extra_query * max(0, query_count - 1)
    return min(base + extra, config.prefetch_rerank_top_n_max)


async def _retrieve_decomposed_queries(
    *,
    deps: QADeps,
    decomposed: DecomposedQuery,
    top_k: int,
    prefetched_original_results: list[dict] | None = None,
) -> RetrievalResult | None:
    """Run one merged multi-query retrieval round (single fuse + rerank)."""
    if not decomposed.sub_queries:
        return None
    required_filters = base_filters(deps)
    filters = merge_retrieval_filters(required_filters, decomposed.filters)
    progress = ToolProgressEmitter("retrieve", deps.tool_progress)
    result = await deps.retriever.retrieve(
        decomposed.sub_queries,
        original_query=decomposed.rewritten_question,
        filters=filters,
        requested_objects=decomposed.requested_objects,
        prefetched_original_results=prefetched_original_results,
        top_k=top_k,
        progress=progress,
    )
    limited = limit_retrieval_result(result, top_k)
    deps.bundle.add_retrieval(limited, query="; ".join(decomposed.sub_queries))
    deps.bundle.tool_trace.append(
        {
            "tool": "prefetch_retrieve",
            "queries": list(decomposed.sub_queries),
            "top_k": top_k,
            "chunk_count": len(limited.chunks),
            "max_score": max(limited.scores) if limited.scores else None,
            "per_query_candidate_counts": dict(
                getattr(result, "per_query_candidate_counts", None) or {}
            ),
            "groundedness": limited.groundedness,
        }
    )
    return result


def _prefetch_calling_progress(
    queries: list[str],
    top_k: int,
    round_no: int,
) -> AgentProgress:
    return AgentProgress(
        event=AgentStreamEvent(
            kind="tool_calling",
            tool_name="prefetch_retrieve",
            tool_args={
                "arguments": json.dumps(
                    {
                        "round": round_no,
                        "queries": queries,
                        "top_k": top_k,
                    },
                    ensure_ascii=False,
                )
            },
            summary=_prefetch_calling_summary(queries, round_no),
        )
    )


def _prefetch_result_progress(
    bundle: EvidenceBundle,
    queries: list[str],
    round_no: int,
) -> AgentProgress:
    attempt = bundle.retrieval_attempts[-1] if bundle.retrieval_attempts else {}
    return AgentProgress(
        event=AgentStreamEvent(
            kind="tool_result",
            tool_name="prefetch_retrieve",
            tool_args={
                "arguments": json.dumps(
                    {"round": round_no, "queries": queries},
                    ensure_ascii=False,
                )
            },
            tool_result=json.dumps(
                {
                    "queries": queries,
                    "chunk_count": attempt.get("chunk_count"),
                    "max_score": attempt.get("max_score"),
                    "groundedness": attempt.get("groundedness"),
                },
                ensure_ascii=False,
            ),
            tool_trace=_latest_tool_trace(bundle.tool_trace, "prefetch_retrieve"),
            summary=_prefetch_result_summary(bundle),
        )
    )


def _new_queries(queries: list[str], attempted_queries: list[str]) -> list[str]:
    seen = {query.strip().lower() for query in attempted_queries if query.strip()}
    new_items: list[str] = []
    for query in queries:
        key = query.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        new_items.append(query)
    return new_items


def _format_assessment_evidence(bundle: EvidenceBundle) -> str:
    chunks = bundle.citable_chunks()
    bundle.ensure_ref_ids(chunks)
    lines: list[str] = []
    for chunk in chunks:
        ref = bundle.ref_label_for(chunk)
        meta = chunk.metadata
        section = " > ".join(meta.section_path) if meta.section_path else "unknown"
        page = ", ".join(map(str, meta.page_numbers)) if meta.page_numbers else "unknown"
        label = f" | {meta.object_label}" if meta.object_label else ""
        preview = chunk.content[:1200].replace("\n", " ").strip()
        lines.append(f"[{ref}] {meta.source} | {section} | p.{page}{label}")
        if preview:
            lines.append(preview)
        if len("\n".join(lines)) >= _MAX_ASSESSMENT_EVIDENCE_CHARS:
            break
    return "\n".join(lines)


def _decompose_summary(decomposed: DecomposedQuery) -> str:
    if decomposed.is_chitchat or not decomposed.needs_retrieval:
        return "小模型判断无需检索。"
    queries = "；".join(decomposed.sub_queries[:4])
    return f"已解构为 {len(decomposed.sub_queries)} 个检索子问题：{queries}"


def _prefetch_calling_summary(queries: list[str], round_no: int) -> str:
    preview = "；".join(queries[:3])
    if len(queries) > 3:
        preview += f"；等 {len(queries)} 个 query"
    return f"第 {round_no} 轮并行检索：{preview}"


def _prefetch_result_summary(bundle: EvidenceBundle) -> str:
    attempt = bundle.retrieval_attempts[-1] if bundle.retrieval_attempts else {}
    chunk_count = int(attempt.get("chunk_count") or 0)
    return f"本轮检索返回 {chunk_count} 条候选证据，累计 {bundle.chunk_count} 条去重证据。"


def _assessment_summary(sufficient: bool, missing_queries: list[str]) -> str:
    if sufficient:
        return "小模型判断证据已足够，开始组织最终回答。"
    if not missing_queries:
        return "小模型未生成新的缺口 query，基于当前证据组织回答。"
    preview = "；".join(missing_queries[:3])
    return f"证据仍有缺口，将补检索：{preview}"


def _latest_tool_trace(
    traces: list[dict],
    tool_name: str,
) -> dict[str, object] | None:
    for trace in reversed(traces):
        if trace.get("tool") == tool_name:
            return trace
    return None


async def _run_agent_dispatch(
    *,
    req: QueryRequest,
    runtime_config: ServerConfig,
    retriever: object,
    glossary: dict[str, str],
    conv_mgr: object,
    sources_filter: list[str] | None = None,
) -> tuple[str, EvidenceBundle, object, QADeps, dict[str, int] | None]:
    """Run the QA agent and return its reply, evidence bundle, session, and deps."""
    conv = await _get_conversation_state(conv_mgr, conversation_id_from_request(req))
    deps = _build_agent_deps(
        runtime_config=runtime_config,
        retriever=retriever,
        glossary=glossary,
        conv=conv,
        req=req,
        sources_filter=sources_filter,
    )
    await _prepare_evidence_for_agent(req=req, deps=deps, glossary=glossary)
    agent = _get_or_build_agent(runtime_config)
    breaker = _get_agent_circuit_breaker(runtime_config)
    started_at = time.perf_counter()

    async def run_agent_with_limits() -> tuple[
        str, EvidenceBundle, dict[str, int] | None
    ]:
        semaphore_wait_started_at = time.perf_counter()
        async with _get_agent_semaphore(runtime_config):
            logger.info(
                "agent_semaphore_acquired",
                wait_ms=int((time.perf_counter() - semaphore_wait_started_at) * 1000),
                breaker_state=breaker.state,
            )
            return await with_retry(
                lambda: run_qa_agent(
                    agent,
                    req.question,
                    deps,
                    max_turns=_AGENT_MAX_TURNS,
                ),
                max_attempts=2,
                retryable=(
                    APITimeoutError,
                    APIConnectionError,
                    InternalServerError,
                ),
            )

    try:
        async with asyncio.timeout(runtime_config.agent_timeout_seconds):
            agent_reply, bundle, usage = await breaker.call(run_agent_with_limits)
        logger.info(
            "agent_dispatch_completed",
            needs_rag=bundle.has_rag_evidence,
            tool_calls=len(bundle.tool_trace),
            duration_ms=int((time.perf_counter() - started_at) * 1000),
            breaker_state=breaker.state,
        )
    except asyncio.TimeoutError:
        logger.warning(
            "agent_dispatch_timeout",
            duration_ms=int((time.perf_counter() - started_at) * 1000),
            breaker_state=breaker.state,
            has_evidence=deps.bundle.has_rag_evidence,
            chunk_count=deps.bundle.chunk_count,
            groundedness=deps.bundle.groundedness,
        )
        if deps.bundle.has_rag_evidence:
            logger.info(
                "agent_dispatch_timeout_graceful",
                chunk_count=deps.bundle.chunk_count,
                groundedness=deps.bundle.groundedness,
            )
            return _DEGRADED_RAG_REPLY, deps.bundle, conv, deps, None

        await breaker.record_failure()
        raise LLMUnavailableError("agent 决策超时")
    except CircuitBreakerOpenError as exc:
        logger.warning("agent_circuit_breaker_open", breaker_state=breaker.state)
        raise LLMUnavailableError("agent LLM 熔断中，请稍后重试") from exc
    except ModelBehaviorError as exc:
        logger.warning(
            "agent_model_behavior_error",
            error=str(exc),
            duration_ms=int((time.perf_counter() - started_at) * 1000),
            breaker_state=breaker.state,
        )
        raise LLMUnavailableError("agent 输出异常，请重试") from exc
    except (APITimeoutError, APIConnectionError, InternalServerError) as exc:
        logger.warning(
            "agent_dispatch_unavailable",
            error_type=type(exc).__name__,
            duration_ms=int((time.perf_counter() - started_at) * 1000),
            breaker_state=breaker.state,
        )
        raise LLMUnavailableError(f"agent LLM 不可用: {exc}") from exc
    return agent_reply, bundle, conv, deps, usage


async def dispatch_agent(
    question: str,
    req: QueryRequest,
    config: ServerConfig,
    retriever: object,
    glossary: dict[str, str],
    conv_mgr: object,
    sources_filter: list[str] | None = None,
) -> AgentResult:
    """Run the agent for a query request."""
    agent_reply, bundle, conv, deps, usage = await _run_agent_dispatch(
        req=req,
        runtime_config=config,
        retriever=retriever,
        glossary=glossary,
        conv_mgr=conv_mgr,
        sources_filter=sources_filter,
    )
    return AgentResult(
        agent_reply=agent_reply,
        bundle=bundle,
        conv=conv,
        deps=deps,
        usage=usage,
    )


async def dispatch_agent_streamed(
    question: str,
    req: QueryRequest,
    config: ServerConfig,
    retriever: object,
    glossary: dict[str, str],
    conv_mgr: object,
    tool_progress: ToolProgressCallback | None = None,
    sources_filter: list[str] | None = None,
) -> AsyncIterator[AgentProgress | AgentResult]:
    """Run the agent and yield progress events before the final result."""
    conv = await _get_conversation_state(conv_mgr, conversation_id_from_request(req))
    deps = _build_agent_deps(
        runtime_config=config,
        retriever=retriever,
        glossary=glossary,
        conv=conv,
        req=req,
        sources_filter=sources_filter,
        tool_progress=tool_progress,
    )
    async for progress in _prepare_evidence_for_agent_streamed(
        req=req,
        deps=deps,
        glossary=glossary,
    ):
        yield progress
    agent = _get_or_build_agent(config)
    breaker = _get_agent_circuit_breaker(config)
    started_at = time.perf_counter()

    async def stream_agent_with_limits() -> AsyncIterator[AgentProgress | AgentResult]:
        semaphore_wait_started_at = time.perf_counter()
        async with _get_agent_semaphore(config):
            logger.info(
                "agent_semaphore_acquired",
                wait_ms=int((time.perf_counter() - semaphore_wait_started_at) * 1000),
                breaker_state=breaker.state,
                streamed=True,
            )
            if deps.bundle.has_rag_evidence:
                yield AgentProgress(
                    event=AgentStreamEvent(
                        kind="thinking",
                        summary="正在基于证据组织最终回答...",
                    )
                )
            async for item in run_qa_agent_streamed(
                agent,
                question,
                deps,
                max_turns=_AGENT_MAX_TURNS,
            ):
                if isinstance(item, AgentStreamEvent):
                    yield AgentProgress(event=item)
                    continue

                agent_reply, bundle, usage = item
                yield AgentResult(
                    agent_reply=agent_reply,
                    bundle=bundle,
                    conv=conv,
                    deps=deps,
                    usage=usage,
                )

    try:
        await breaker._before_call()
        try:
            async with asyncio.timeout(config.agent_timeout_seconds):
                async for item in stream_agent_with_limits():
                    if isinstance(item, AgentResult):
                        logger.info(
                            "agent_dispatch_completed",
                            needs_rag=item.bundle.has_rag_evidence,
                            tool_calls=len(item.bundle.tool_trace),
                            duration_ms=int((time.perf_counter() - started_at) * 1000),
                            breaker_state=breaker.state,
                            streamed=True,
                        )
                    yield item
        except asyncio.TimeoutError:
            raise
        except Exception:
            await breaker.record_failure()
            raise
        await breaker.record_success()
    except asyncio.TimeoutError:
        logger.warning(
            "agent_dispatch_timeout",
            duration_ms=int((time.perf_counter() - started_at) * 1000),
            breaker_state=breaker.state,
            streamed=True,
            has_evidence=deps.bundle.has_rag_evidence,
            chunk_count=deps.bundle.chunk_count,
            groundedness=deps.bundle.groundedness,
        )
        if deps.bundle.has_rag_evidence:
            logger.info(
                "agent_dispatch_timeout_graceful",
                chunk_count=deps.bundle.chunk_count,
                groundedness=deps.bundle.groundedness,
                streamed=True,
            )
            yield AgentResult(
                agent_reply=_DEGRADED_RAG_REPLY,
                bundle=deps.bundle,
                conv=conv,
                deps=deps,
                usage=None,
            )
            return

        await breaker.record_failure()
        raise LLMUnavailableError("agent 决策超时")
    except CircuitBreakerOpenError as exc:
        logger.warning("agent_circuit_breaker_open", breaker_state=breaker.state)
        raise LLMUnavailableError("agent LLM 熔断中，请稍后重试") from exc
    except ModelBehaviorError as exc:
        logger.warning(
            "agent_model_behavior_error",
            error=str(exc),
            duration_ms=int((time.perf_counter() - started_at) * 1000),
            breaker_state=breaker.state,
            streamed=True,
        )
        raise LLMUnavailableError("agent 输出异常，请重试") from exc
    except (APITimeoutError, APIConnectionError, InternalServerError) as exc:
        logger.warning(
            "agent_dispatch_unavailable",
            error_type=type(exc).__name__,
            duration_ms=int((time.perf_counter() - started_at) * 1000),
            breaker_state=breaker.state,
            streamed=True,
        )
        raise LLMUnavailableError(f"agent LLM 不可用: {exc}") from exc
