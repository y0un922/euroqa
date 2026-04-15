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


async def invalidate_retriever_cache() -> None:
    """关闭旧 retriever 并清除缓存，使新文档数据立即可查询。"""
    if get_retriever.cache_info().currsize > 0:
        try:
            retriever = get_retriever()
            await retriever.close()
        except Exception:
            pass
    get_retriever.cache_clear()


@lru_cache
def get_glossary() -> dict[str, str]:
    config = get_config()
    path = Path(config.glossary_path)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}
