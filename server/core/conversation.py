"""Conversation state management."""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from cachetools import TTLCache

from server.config import ServerConfig


@dataclass
class ConversationState:
    conversation_id: str
    history: list[dict[str, str]]


class ConversationManager:
    def __init__(self, ttl_hours: int = 24, max_size: int = 1000):
        self._cache: TTLCache = TTLCache(maxsize=max_size, ttl=ttl_hours * 3600)

    def get_or_create(self, conversation_id: str | None = None) -> ConversationState:
        if conversation_id and conversation_id in self._cache:
            return self._cache[conversation_id]
        cid = conversation_id or str(uuid.uuid4())
        state = ConversationState(conversation_id=cid, history=[])
        self._cache[cid] = state
        return state

    def add_turn(self, conversation_id: str, question: str, answer: str) -> None:
        state = self.get_or_create(conversation_id)
        state.history.append({"question": question, "answer": answer})


def _utc_iso() -> str:
    """Return an ISO 8601 UTC timestamp."""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _user_id_from_session_id(session_id: str) -> str | None:
    """Extract user id from the interface-document sessionId convention."""
    user_id, sep, _rest = session_id.partition("_")
    return user_id if sep and user_id else None


def _message_to_history_item(payload: dict[str, Any]) -> dict[str, str] | None:
    """Convert Redis message payloads into generation history items."""
    if "question" in payload and "answer" in payload:
        question = str(payload.get("question") or "").strip()
        answer = str(payload.get("answer") or "").strip()
        if question or answer:
            return {"question": question, "answer": answer}
    if payload.get("role") == "user":
        content = str(payload.get("content") or "").strip()
        if content:
            return {"question": content, "answer": ""}
    return None


class RedisConversationManager:
    """Redis-backed conversation manager using the external session contract."""

    def __init__(self, config: ServerConfig):
        try:
            from redis import asyncio as redis_asyncio
        except ImportError as exc:  # pragma: no cover - dependency guard
            raise RuntimeError("redis package is required for REDIS_URL") from exc

        if not config.redis_url:
            raise ValueError("REDIS_URL is required")
        self._redis = redis_asyncio.from_url(
            config.redis_url,
            decode_responses=True,
        )
        self._ttl_seconds = config.conversation_ttl_hours * 3600

    def get_or_create(self, conversation_id: str | None = None) -> ConversationState:
        cid = conversation_id or str(uuid.uuid4())
        return ConversationState(conversation_id=cid, history=[])

    async def get_or_create_async(
        self,
        conversation_id: str | None = None,
    ) -> ConversationState:
        cid = conversation_id or str(uuid.uuid4())
        raw_items = await self._redis.lrange(f"context:{cid}", 0, -1)
        history: list[dict[str, str]] = []
        for raw in raw_items:
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                item = _message_to_history_item(payload)
                if item:
                    history.append(item)
        return ConversationState(conversation_id=cid, history=history)

    def add_turn(self, conversation_id: str, question: str, answer: str) -> None:
        del conversation_id, question, answer

    async def add_turn_async(
        self,
        conversation_id: str,
        question: str,
        answer: str,
        *,
        title: str | None = None,
    ) -> str | None:
        """Append one Q&A turn and update session metadata."""
        now = _utc_iso()
        key = f"context:{conversation_id}"
        await self._redis.rpush(
            key,
            json.dumps(
                {
                    "question": question,
                    "answer": answer,
                    "createdAt": now,
                },
                ensure_ascii=False,
            ),
        )
        await self._redis.expire(key, self._ttl_seconds)

        generated_title = title or _derive_session_title(question)
        user_id = _user_id_from_session_id(conversation_id)
        if user_id:
            meta_key = f"user:{user_id}:sessions"
            raw_meta = await self._redis.hget(meta_key, conversation_id)
            metadata: dict[str, Any] = {}
            if raw_meta:
                try:
                    loaded = json.loads(raw_meta)
                    if isinstance(loaded, dict):
                        metadata.update(loaded)
                except json.JSONDecodeError:
                    metadata = {}
            existing_title = metadata.get("title")
            metadata.setdefault("createdAt", now)
            metadata["updatedAt"] = now
            if not existing_title:
                metadata["title"] = generated_title
            await self._redis.hset(
                meta_key,
                conversation_id,
                json.dumps(metadata, ensure_ascii=False),
            )
        return generated_title


def _derive_session_title(question: str, limit: int = 24) -> str:
    """Derive a compact session title from the first question."""
    compact = " ".join(question.strip().split())
    if len(compact) <= limit:
        return compact
    return compact[:limit].rstrip() + "..."
