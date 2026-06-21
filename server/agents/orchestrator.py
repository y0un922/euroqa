"""Agent lifecycle orchestration for query endpoints."""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass

from agents import Agent
from agents.exceptions import ModelBehaviorError
from openai import APIConnectionError, APITimeoutError, InternalServerError
import structlog

from server.agents.deps import QADeps
from server.agents.evidence import EvidenceBundle
from server.agents.qa_agent import (
    AgentStreamEvent,
    build_qa_agent,
    run_qa_agent,
    run_qa_agent_streamed,
)
from server.agents.tool_progress import ToolProgressCallback
from server.circuit_breaker import AsyncCircuitBreaker, CircuitBreakerOpenError
from server.config import ServerConfig
from server.core.conversation import ConversationState
from server.core.query_request import (
    conversation_id_from_request,
    uses_external_session,
)
from server.errors import LLMUnavailableError
from server.models.schemas import QueryRequest
from server.retry import with_retry

logger = structlog.get_logger(__name__)

_qa_agents: dict[str, Agent[QADeps]] = {}
_agent_semaphore: asyncio.Semaphore | None = None
_agent_circuit_breaker: AsyncCircuitBreaker | None = None
_AGENT_MAX_TURNS = 3
_DEGRADED_RAG_REPLY = "已检索到相关规范证据，正在整理回答。"


@dataclass
class AgentResult:
    agent_reply: str
    bundle: EvidenceBundle
    conv: object
    deps: QADeps

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
        domain_filter=req.domain,
        sources_filter=sources_filter,
        tool_progress=tool_progress,
    )


async def _run_agent_dispatch(
    *,
    req: QueryRequest,
    runtime_config: ServerConfig,
    retriever: object,
    glossary: dict[str, str],
    conv_mgr: object,
    sources_filter: list[str] | None = None,
) -> tuple[str, EvidenceBundle, object, QADeps]:
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
    agent = _get_or_build_agent(runtime_config)
    breaker = _get_agent_circuit_breaker(runtime_config)
    started_at = time.perf_counter()

    async def run_agent_with_limits() -> tuple[str, EvidenceBundle]:
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
            agent_reply, bundle = await breaker.call(run_agent_with_limits)
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
            return _DEGRADED_RAG_REPLY, deps.bundle, conv, deps

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
    return agent_reply, bundle, conv, deps


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
    agent_reply, bundle, conv, deps = await _run_agent_dispatch(
        req=req,
        runtime_config=config,
        retriever=retriever,
        glossary=glossary,
        conv_mgr=conv_mgr,
        sources_filter=sources_filter,
    )
    return AgentResult(agent_reply=agent_reply, bundle=bundle, conv=conv, deps=deps)


async def dispatch_agent_streamed(
    question: str,
    req: QueryRequest,
    config: ServerConfig,
    retriever: object,
    glossary: dict[str, str],
    conv_mgr: object,
    sources_filter: list[str] | None = None,
    tool_progress: ToolProgressCallback | None = None,
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
            async for item in run_qa_agent_streamed(
                agent,
                question,
                deps,
                max_turns=_AGENT_MAX_TURNS,
            ):
                if isinstance(item, AgentStreamEvent):
                    yield AgentProgress(event=item)
                    continue

                agent_reply, bundle = item
                yield AgentResult(
                    agent_reply=agent_reply,
                    bundle=bundle,
                    conv=conv,
                    deps=deps,
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
