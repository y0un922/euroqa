"""LLM answer generation and streaming helpers."""

from __future__ import annotations

import time
from typing import Any

import httpx
import structlog
from openai import AsyncOpenAI

from server.config import ServerConfig
from server.core.generation.citations import postprocess_citations
from server.core.generation.confidence import (
    _build_related_refs_from_chunks,
    _infer_answer_confidence,
    parse_llm_response,
)
from server.core.generation.context import (
    _build_retrieval_context,
    _dedupe_chunks_and_scores,
    _dedupe_chunks_by_id,
)
from server.core.generation.prompts import (
    _build_dynamic_guidance,
    _build_json_system_prompt,
    _build_stream_mode_system_prompt,
    _normalize_engineering_context,
    _normalize_question_type,
    build_prompt,
    decide_generation_mode,
)
from server.core.generation.sources import (
    _build_prioritized_source_chunks,
    _build_sources_from_chunks,
    _normalize_sources,
)
from server.core.generation.tokens import _count_tokens
from server.models.schemas import (
    Chunk,
    Confidence,
    EngineeringContext,
    QueryResponse,
    QuestionType,
)
from shared.llm_clients import get_async_openai_client
from shared.spot_check import record_spot_check

logger = structlog.get_logger(__name__)


def _current_async_openai_factory():
    """Resolve package-level AsyncOpenAI so legacy patch paths still work."""
    from server.core import generation as generation_package

    return getattr(generation_package, "AsyncOpenAI", AsyncOpenAI)


def _is_qwen_provider(config: ServerConfig) -> bool:
    model_name = config.llm_model.lower()
    base_url = config.llm_base_url.lower()
    return "qwen" in model_name or "dashscope.aliyuncs.com" in base_url


def _should_enable_prompt_cache(config: ServerConfig) -> bool:
    """Return whether to attach DashScope explicit cache markers."""
    return config.llm_prompt_cache_enabled and _is_qwen_provider(config)


def _should_enable_reasoning(config: ServerConfig) -> bool:
    """Return whether the current model/provider should request thinking tokens."""
    if not config.llm_enable_thinking:
        return False
    return _is_qwen_provider(config)


def _build_stream_completion_kwargs(config: ServerConfig) -> dict[str, Any]:
    """Build optional kwargs for reasoning-capable streaming models."""
    kwargs: dict[str, Any] = {}
    if _should_enable_reasoning(config):
        kwargs["extra_body"] = {"enable_thinking": True}
    elif _is_qwen_provider(config):
        kwargs["extra_body"] = {"enable_thinking": False}
    if _should_enable_prompt_cache(config):
        kwargs["stream_options"] = {"include_usage": True}
    return kwargs


def _build_text_message(
    role: str,
    content: str,
    *,
    prompt_cache_enabled: bool,
) -> dict[str, Any]:
    """Build a chat message, optionally marking the text for explicit cache."""
    if not prompt_cache_enabled:
        return {"role": role, "content": content}
    return {
        "role": role,
        "content": [
            {
                "type": "text",
                "text": content,
                "cache_control": {"type": "ephemeral"},
            }
        ],
    }


def _build_chat_messages(
    *,
    system_prompt: str,
    user_prompt: str,
    config: ServerConfig,
) -> list[dict[str, Any]]:
    prompt_cache_enabled = _should_enable_prompt_cache(config)
    return [
        _build_text_message(
            "system",
            system_prompt,
            prompt_cache_enabled=prompt_cache_enabled,
        ),
        {"role": "user", "content": user_prompt},
    ]


def _extract_cached_prompt_tokens(usage: Any) -> int | None:
    """Extract provider-reported cached prompt tokens from usage payloads."""
    if usage is None:
        return None
    if isinstance(usage, dict):
        details = usage.get("prompt_tokens_details") or {}
        cached = details.get("cached_tokens")
    else:
        details = getattr(usage, "prompt_tokens_details", None)
        cached = getattr(details, "cached_tokens", None)
        if cached is None and isinstance(details, dict):
            cached = details.get("cached_tokens")
    return cached if isinstance(cached, int) else None


async def generate_answer_stream(
    question: str,
    chunks: list[Chunk],
    parent_chunks: list[Chunk],
    scores: list[float] | None = None,
    glossary_terms: dict[str, str] | None = None,
    conversation_history: list[dict] | None = None,
    config: ServerConfig | None = None,
    ref_chunks: list[Chunk] | None = None,
    guide_chunks: list[Chunk] | None = None,
    guide_example_chunks: list[Chunk] | None = None,
    question_type: str | QuestionType | None = None,
    engineering_context: EngineeringContext | dict[str, Any] | None = None,
    groundedness: str | None = None,
    resolved_refs: list[str] | None = None,
    unresolved_refs: list[str] | None = None,
    slot_results: list[dict[str, object]] | None = None,
    unresolved_slots: list[str] | None = None,
    intent_label: str | None = None,
):
    """流式生成 LLM 回答，通过异步生成器逐步输出。

    使用八段式模板动态构建 system prompt，直接输出可渲染 Markdown。
    done 事件的 sources 从检索结果的 metadata 直接构建，不依赖 LLM 解析。

    Yields:
        (event_type, data) 元组
    """
    cfg = config or ServerConfig()
    chunks, scores = _dedupe_chunks_and_scores(chunks, scores)
    parent_chunks = _dedupe_chunks_by_id(parent_chunks)
    ref_chunks = _dedupe_chunks_by_id(ref_chunks)
    guide_chunks = _dedupe_chunks_by_id(guide_chunks)
    guide_example_chunks = _dedupe_chunks_by_id(guide_example_chunks)
    qt_normalized = _normalize_question_type(question_type)
    ctx_normalized = _normalize_engineering_context(engineering_context)
    generation_mode = decide_generation_mode(groundedness)
    prepare_started = time.perf_counter()
    prompt_started = time.perf_counter()
    prompt = build_prompt(
        question,
        chunks,
        parent_chunks,
        glossary_terms,
        conversation_history,
        ref_chunks=ref_chunks,
        guide_chunks=guide_chunks,
        guide_example_chunks=guide_example_chunks,
        generation_mode=generation_mode,
        resolved_refs=resolved_refs,
        unresolved_refs=unresolved_refs,
        slot_results=slot_results,
        unresolved_slots=unresolved_slots,
        intent_label=intent_label,
        config=cfg,
    )
    prompt_duration_ms = (time.perf_counter() - prompt_started) * 1000
    system_prompt_started = time.perf_counter()
    system_prompt = _build_stream_mode_system_prompt(
        generation_mode,
        qt_normalized,
        ctx_normalized,
        intent_label=intent_label,
    )
    dynamic_guidance = _build_dynamic_guidance(
        generation_mode,
        qt_normalized,
        ctx_normalized,
    )
    full_user_prompt = f"{dynamic_guidance}\n\n{prompt}"
    system_prompt_duration_ms = (time.perf_counter() - system_prompt_started) * 1000

    client_started = time.perf_counter()
    client = await get_async_openai_client(
        api_key=cfg.llm_api_key,
        base_url=cfg.llm_base_url,
        timeout=httpx.Timeout(timeout=600.0),
        client_factory=_current_async_openai_factory(),
    )
    client_duration_ms = (time.perf_counter() - client_started) * 1000
    token_count_started = time.perf_counter()
    prompt_tokens, prompt_tokens_estimate = _count_tokens(full_user_prompt, cfg)
    token_count_duration_ms = (time.perf_counter() - token_count_started) * 1000
    prepare_duration_ms = (time.perf_counter() - prepare_started) * 1000
    record_spot_check(
        "final_prompt_tokens",
        {
            "value": prompt_tokens,
            "is_estimate": prompt_tokens_estimate,
            "model": cfg.llm_model,
        },
    )
    logger.info(
        "llm_stream_prepare_timing",
        duration_ms=round(prepare_duration_ms, 2),
        prompt_build_ms=round(prompt_duration_ms, 2),
        system_prompt_build_ms=round(system_prompt_duration_ms, 2),
        client_ready_ms=round(client_duration_ms, 2),
        token_count_ms=round(token_count_duration_ms, 2),
        prompt_len=len(prompt),
        system_prompt_len=len(system_prompt),
        prompt_tokens=prompt_tokens,
        prompt_tokens_estimate=prompt_tokens_estimate,
        chunks=len(chunks),
        parent_chunks=len(parent_chunks),
        ref_chunks=len(ref_chunks or []),
        guide_chunks=len(guide_chunks or []),
        guide_example_chunks=len(guide_example_chunks or []),
        question_type=qt_normalized,
        generation_mode=generation_mode,
    )
    try:
        logger.info(
            "llm_stream_start model=%s max_tokens=%d prompt_len=%d prompt_tokens=%d "
            "prompt_tokens_estimate=%s question_type=%s",
            cfg.llm_model,
            8192,
            len(prompt),
            prompt_tokens,
            prompt_tokens_estimate,
            qt_normalized,
        )
        stream = await client.chat.completions.create(
            model=cfg.llm_model,
            messages=_build_chat_messages(
                system_prompt=system_prompt,
                user_prompt=full_user_prompt,
                config=cfg,
            ),
            temperature=0.2,
            max_tokens=8192,
            stream=True,
            **_build_stream_completion_kwargs(cfg),
        )
        chunk_count = 0
        total_content_len = 0
        finish_reason = None
        stream_usage = None
        async for token in stream:
            if not getattr(token, "choices", None):
                stream_usage = getattr(token, "usage", None) or stream_usage
                continue

            delta = token.choices[0].delta
            reasoning = getattr(delta, "reasoning_content", None)
            if reasoning:
                yield ("reasoning", {"text": reasoning})

            content = delta.content
            if content:
                chunk_count += 1
                total_content_len += len(content)
                yield ("chunk", {"text": content, "done": False})

            # 记录 finish_reason
            token_finish_reason = getattr(token.choices[0], "finish_reason", None)
            if token_finish_reason:
                finish_reason = token_finish_reason

        logger.info(
            "llm_stream_end chunks=%d content_chars=%d finish_reason=%s "
            "cached_prompt_tokens=%s",
            chunk_count,
            total_content_len,
            finish_reason,
            _extract_cached_prompt_tokens(stream_usage),
        )

        # 从检索结果直接构建结构化元数据，不依赖 LLM 输出
        # 主 chunk、父片段、交叉引用和 guide/example chunk 统一编号，
        # 与 prompt 中的 [Ref-N] 一一对应。
        all_citable = (
            list(chunks)
            + list(parent_chunks)
            + list(ref_chunks or [])
            + list(guide_chunks or [])
            + list(guide_example_chunks or [])
        )
        prioritized_chunks = _build_prioritized_source_chunks(
            chunks,
            parent_chunks,
            ref_chunks=ref_chunks,
            guide_chunks=guide_chunks,
            guide_example_chunks=guide_example_chunks,
            generation_mode=generation_mode,
            question=question,
            intent_label=intent_label,
        )
        # 注意：sources 顺序必须与 build_prompt 中 [Ref-N] 编号完全一致，
        # 前端通过 sources[N-1] 定位 [Ref-N] 对应的证据，不能重排。
        sources = _build_sources_from_chunks(
            all_citable,
            config=cfg,
            prioritized_chunks=prioritized_chunks,
        )
        related_refs = _build_related_refs_from_chunks(chunks)
        confidence = _infer_answer_confidence(
            scores,
            has_sources=bool(sources),
            groundedness=groundedness,
        )
        retrieval_context = _build_retrieval_context(
            chunks,
            parent_chunks,
            guide_chunks=guide_chunks,
            guide_example_chunks=guide_example_chunks,
            ref_chunks=ref_chunks,
            scores=scores,
            resolved_refs=resolved_refs,
            unresolved_refs=unresolved_refs,
            slot_results=slot_results,
            unresolved_slots=unresolved_slots,
            config=cfg,
        )
        yield (
            "done",
            {
                "sources": [s.model_dump() for s in sources],
                "related_refs": related_refs,
                "confidence": confidence.value,
                "retrieval_context": retrieval_context.model_dump(),
                "question_type": qt_normalized,
                "engineering_context": ctx_normalized.model_dump()
                if ctx_normalized
                else None,
            },
        )
    except Exception:
        logger.exception("llm_stream_failed")
        yield ("error", {"message": "LLM 服务暂时不可用"})


async def generate_answer(
    question: str,
    chunks: list[Chunk],
    parent_chunks: list[Chunk],
    scores: list[float] | None = None,
    glossary_terms: dict[str, str] | None = None,
    conversation_history: list[dict] | None = None,
    config: ServerConfig | None = None,
    ref_chunks: list[Chunk] | None = None,
    guide_chunks: list[Chunk] | None = None,
    guide_example_chunks: list[Chunk] | None = None,
    question_type: str | QuestionType | None = None,
    engineering_context: EngineeringContext | dict[str, Any] | None = None,
    groundedness: str | None = None,
    resolved_refs: list[str] | None = None,
    unresolved_refs: list[str] | None = None,
    slot_results: list[dict[str, object]] | None = None,
    unresolved_slots: list[str] | None = None,
    intent_label: str | None = None,
) -> QueryResponse:
    """调用 LLM 生成基于检索内容的回答。

    Args:
        question: 用户原始问题
        chunks: 检索到的规范片段
        parent_chunks: 扩展上下文（章节级父片段）
        glossary_terms: 中英术语对照表
        conversation_history: 历史对话记录
        config: 服务器配置（为空时使用默认配置）
        ref_chunks: 交叉引用补充片段

    Returns:
        结构化的 QueryResponse；LLM 调用失败时返回降级响应
    """
    cfg = config or ServerConfig()
    chunks, scores = _dedupe_chunks_and_scores(chunks, scores)
    parent_chunks = _dedupe_chunks_by_id(parent_chunks)
    ref_chunks = _dedupe_chunks_by_id(ref_chunks)
    guide_chunks = _dedupe_chunks_by_id(guide_chunks)
    guide_example_chunks = _dedupe_chunks_by_id(guide_example_chunks)
    retrieval_context = _build_retrieval_context(
        chunks,
        parent_chunks,
        guide_chunks=guide_chunks,
        guide_example_chunks=guide_example_chunks,
        ref_chunks=ref_chunks,
        scores=scores,
        resolved_refs=resolved_refs,
        unresolved_refs=unresolved_refs,
        slot_results=slot_results,
        unresolved_slots=unresolved_slots,
        config=cfg,
    )
    qt_normalized = _normalize_question_type(question_type)
    ctx_normalized = _normalize_engineering_context(engineering_context)
    generation_mode = decide_generation_mode(groundedness)
    prompt = build_prompt(
        question,
        chunks,
        parent_chunks,
        glossary_terms,
        conversation_history,
        ref_chunks=ref_chunks,
        guide_chunks=guide_chunks,
        guide_example_chunks=guide_example_chunks,
        generation_mode=generation_mode,
        resolved_refs=resolved_refs,
        unresolved_refs=unresolved_refs,
        slot_results=slot_results,
        unresolved_slots=unresolved_slots,
        intent_label=intent_label,
        config=cfg,
    )
    system_prompt = _build_json_system_prompt(
        generation_mode,
        question_type=qt_normalized,
        engineering_context=ctx_normalized,
        intent_label=intent_label,
    )
    dynamic_guidance = _build_dynamic_guidance(
        generation_mode,
        qt_normalized,
        ctx_normalized,
    )
    full_user_prompt = f"{dynamic_guidance}\n\n{prompt}"

    client = await get_async_openai_client(
        api_key=cfg.llm_api_key,
        base_url=cfg.llm_base_url,
        client_factory=_current_async_openai_factory(),
    )
    prompt_tokens, prompt_tokens_estimate = _count_tokens(full_user_prompt, cfg)
    record_spot_check(
        "final_prompt_tokens",
        {
            "value": prompt_tokens,
            "is_estimate": prompt_tokens_estimate,
            "model": cfg.llm_model,
        },
    )
    try:
        logger.info(
            "llm_call_start model=%s max_tokens=%d prompt_len=%d prompt_tokens=%d "
            "prompt_tokens_estimate=%s",
            cfg.llm_model,
            8192,
            len(prompt),
            prompt_tokens,
            prompt_tokens_estimate,
        )
        resp = await client.chat.completions.create(
            model=cfg.llm_model,
            messages=_build_chat_messages(
                system_prompt=system_prompt,
                user_prompt=full_user_prompt,
                config=cfg,
            ),
            temperature=0.2,
            max_tokens=8192,
            response_format={"type": "json_object"},
        )
        raw = resp.choices[0].message.content.strip()
        logger.info(
            "llm_call_end finish_reason=%s usage=%s content_len=%d "
            "cached_prompt_tokens=%s",
            getattr(resp.choices[0], "finish_reason", None),
            getattr(resp, "usage", None),
            len(raw),
            _extract_cached_prompt_tokens(getattr(resp, "usage", None)),
        )
        response = parse_llm_response(raw)
        all_citable = (
            list(chunks)
            + list(parent_chunks)
            + list(ref_chunks or [])
            + list(guide_chunks or [])
            + list(guide_example_chunks or [])
        )
        prioritized_chunks = _build_prioritized_source_chunks(
            chunks,
            parent_chunks,
            ref_chunks=ref_chunks,
            guide_chunks=guide_chunks,
            guide_example_chunks=guide_example_chunks,
            generation_mode=generation_mode,
            question=question,
            intent_label=intent_label,
        )
        canonical_sources = _normalize_sources(
            _build_sources_from_chunks(
                all_citable,
                config=cfg,
                prioritized_chunks=prioritized_chunks,
            )
        )
        # Citation 后处理：归一化格式变体、剔除越界编号、句内去重
        normalized_answer = postprocess_citations(
            response.answer, len(canonical_sources)
        )
        confidence = _infer_answer_confidence(
            scores,
            has_sources=bool(canonical_sources),
            groundedness=groundedness,
        )
        return response.model_copy(
            update={
                "answer": normalized_answer,
                "sources": canonical_sources,
                "confidence": confidence,
                "retrieval_context": retrieval_context,
                "question_type": qt_normalized,
                "engineering_context": (
                    ctx_normalized.model_dump() if ctx_normalized else None
                ),
            }
        )
    except Exception:
        logger.exception("llm_call_failed")
        return QueryResponse(
            answer="LLM 服务暂时不可用，以下是检索到的相关规范片段。",
            sources=[],
            confidence=Confidence.LOW,
            degraded=True,
            retrieval_context=retrieval_context,
            question_type=qt_normalized,
            engineering_context=ctx_normalized.model_dump() if ctx_normalized else None,
        )
