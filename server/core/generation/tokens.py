from __future__ import annotations

from functools import lru_cache

import tiktoken

from server.config import ServerConfig
from shared.tokenizers import count_for_llm


def _current_count_for_llm():
    """Resolve package-level tokenizer so legacy monkeypatch paths still work."""
    from server.core import generation as generation_package

    return getattr(generation_package, "count_for_llm", count_for_llm)


@lru_cache(maxsize=1)
def _get_legacy_encoding():
    return tiktoken.get_encoding("cl100k_base")


def _legacy_count_tokens(text: str) -> int:
    try:
        return len(_get_legacy_encoding().encode(text))
    except Exception:
        return max(1, len(text or "") // 2)


def _count_tokens(text: str, config: ServerConfig | None = None) -> tuple[int, bool]:
    cfg = config or ServerConfig()
    if not cfg.use_unified_tokenizer:
        return _legacy_count_tokens(text), True
    return _current_count_for_llm()(text, cfg.llm_model)
