"""FastAPI dependency injection."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from server.config import ServerConfig
from server.core.conversation import ConversationManager
from server.core.retrieval import HybridRetriever


@lru_cache
def get_config() -> ServerConfig:
    return ServerConfig()


@lru_cache
def get_conversation_manager() -> ConversationManager:
    config = get_config()
    return ConversationManager(ttl_hours=config.conversation_ttl_hours)


@lru_cache
def get_retriever() -> HybridRetriever:
    return HybridRetriever(get_config())


@lru_cache
def get_glossary() -> dict[str, str]:
    config = get_config()
    path = Path(config.glossary_path)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}
