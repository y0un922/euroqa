"""Conversation state management (in-memory TTL cache)."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from cachetools import TTLCache


@dataclass
class ConversationState:
    conversation_id: str
    history: list[dict] = field(default_factory=list)


class ConversationManager:
    def __init__(self, ttl_hours: int = 24, max_size: int = 1000):
        self._cache: TTLCache = TTLCache(maxsize=max_size, ttl=ttl_hours * 3600)

    def get_or_create(self, conversation_id: str | None = None) -> ConversationState:
        if conversation_id and conversation_id in self._cache:
            return self._cache[conversation_id]
        cid = conversation_id or str(uuid.uuid4())
        state = ConversationState(conversation_id=cid)
        self._cache[cid] = state
        return state

    def add_turn(self, conversation_id: str, question: str, answer: str) -> None:
        state = self._cache.get(conversation_id)
        if state:
            state.history.append({"question": question, "answer": answer})
            if len(state.history) > 3:
                state.history = state.history[-3:]
