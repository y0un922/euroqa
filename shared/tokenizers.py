"""Shared tokenizer utilities for retrieval and generation token accounting."""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Any

import structlog
import tiktoken

logger = structlog.get_logger()

_DEFAULT_EMBEDDING_MODEL = "BAAI/bge-m3"
_DEFAULT_RERANK_MODEL = "BAAI/bge-reranker-v2-m3"
_HF_TOKENIZER_BY_MODEL = {
    "baai/bge-m3": "BAAI/bge-m3",
    "baai/bge-reranker-v2-m3": "BAAI/bge-reranker-v2-m3",
}
_OPENAI_MODEL_PREFIXES = ("gpt-", "o1-", "o3-")
_FAILED_HF_TOKENIZERS: set[str] = set()


def count_for_embedding(
    text: str,
    model: str = _DEFAULT_EMBEDDING_MODEL,
) -> tuple[int, bool]:
    """Count tokens for embedding input.

    Returns:
        ``(count, is_estimate)``. BGE models use local/online HF tokenizer
        loading. Qwen API models use the DashScope tokenizer when installed,
        otherwise a character estimate. Billing must use provider ``usage``,
        not these pre-counts. Other models fall back to a character estimate.
    """
    return _count_for_model(text, model)


def count_for_rerank(
    text: str,
    model: str = _DEFAULT_RERANK_MODEL,
) -> tuple[int, bool]:
    """Count tokens for rerank input."""
    return _count_for_model(text, model)


def count_for_llm(text: str, model: str) -> tuple[int, bool]:
    """Count tokens for an LLM model."""
    normalized_model = _normalize_model(model)
    if _is_openai_model(normalized_model):
        return _count_with_tiktoken(text, normalized_model), False
    if _is_qwen_model(normalized_model):
        official = _qwen_tokenizer_count(text)
        if official is not None:
            return official
        return _estimate_with_log(text, normalized_model, "qwen_tokenizer_unavailable")
    return _estimate_with_log(text, normalized_model, "llm_tokenizer_unavailable")


def count_for_bge_embedding(text: str) -> int:
    """Count BGE-M3 embedding tokens, returning only the count."""
    count, _ = count_for_embedding(text, _DEFAULT_EMBEDDING_MODEL)
    return count


def count_for_bge_rerank(text: str) -> int:
    """Count BGE reranker tokens, returning only the count."""
    count, _ = count_for_rerank(text, _DEFAULT_RERANK_MODEL)
    return count


def _count_for_model(text: str, model: str) -> tuple[int, bool]:
    normalized_model = _normalize_model(model)
    tokenizer_name = _resolve_hf_tokenizer_name(normalized_model)
    if tokenizer_name:
        try:
            return _count_with_hf_tokenizer_strict(text, tokenizer_name), False
        except Exception:
            logger.warning(
                "hf_tokenizer_fallback_to_char_estimate",
                model=normalized_model,
                tokenizer=tokenizer_name,
                exc_info=True,
            )
            return _char_token_estimate(text), True

    if _is_qwen_model(normalized_model):
        official = _qwen_tokenizer_count(text)
        if official is not None:
            return official
        return _estimate_with_log(text, normalized_model, "qwen_tokenizer_unavailable")

    return _estimate_with_log(text, normalized_model, "tokenizer_mapping_missing")


def _count_with_hf_tokenizer_strict(text: str, tokenizer_name: str) -> int:
    if tokenizer_name in _FAILED_HF_TOKENIZERS:
        raise RuntimeError(f"HF tokenizer unavailable: {tokenizer_name}")
    tokenizer = _get_hf_tokenizer(tokenizer_name)
    return len(tokenizer.encode(text or "", add_special_tokens=False))


@lru_cache(maxsize=8)
def _get_hf_tokenizer(tokenizer_name: str) -> Any:
    try:
        return _load_hf_tokenizer(tokenizer_name, local_files_only=True)
    except Exception:
        logger.warning(
            "hf_tokenizer_local_cache_miss",
            tokenizer=tokenizer_name,
            exc_info=True,
        )
    try:
        return _load_hf_tokenizer(tokenizer_name, local_files_only=False)
    except Exception:
        _FAILED_HF_TOKENIZERS.add(tokenizer_name)
        raise


def _load_hf_tokenizer(tokenizer_name: str, *, local_files_only: bool) -> Any:
    from transformers import AutoTokenizer

    return AutoTokenizer.from_pretrained(
        tokenizer_name,
        local_files_only=local_files_only,
        trust_remote_code=True,
    )


def _resolve_hf_tokenizer_name(model: str) -> str | None:
    if not model:
        return None

    alias_key = _alias_env_key(model)
    alias_override = os.getenv(f"TOKENIZER_NAME_{alias_key}")
    if alias_override and alias_override.strip():
        return alias_override.strip()

    return _HF_TOKENIZER_BY_MODEL.get(model.lower())


def _estimate_with_log(text: str, model: str, event: str) -> tuple[int, bool]:
    if model:
        logger.warning(event, model=model)
    return _char_token_estimate(text), True


def _normalize_model(model: str) -> str:
    return (model or "").strip()


def _alias_env_key(model: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in model.upper()).strip("_")


def _is_openai_model(model: str) -> bool:
    return model.lower().startswith(_OPENAI_MODEL_PREFIXES)


def _is_qwen_model(model: str) -> bool:
    return "qwen" in model.lower()


def _qwen_tokenizer_count(text: str) -> tuple[int, bool] | None:
    """Count with the official Qwen tokenizer when DashScope is installed."""
    try:
        from dashscope import get_tokenizer

        tokenizer = get_tokenizer("qwen-turbo")
        return len(tokenizer.encode(text or "")), False
    except Exception:
        return None


def _count_with_tiktoken(text: str, model: str) -> int:
    try:
        encoding = tiktoken.encoding_for_model(model)
    except Exception:
        encoding = tiktoken.get_encoding("cl100k_base")
    return len(encoding.encode(text or ""))


def _char_token_estimate(text: str) -> int:
    return max(1, len(text or "") // 2)
