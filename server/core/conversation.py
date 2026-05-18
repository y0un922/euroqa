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
    """Convert legacy Redis turn payloads into generation history items."""
    if "question" in payload and "answer" in payload:
        question = str(payload.get("question") or "").strip()
        answer = str(payload.get("answer") or "").strip()
        if question or answer:
            return {"question": question, "answer": answer}
    return None


def _messages_to_history(raw_items: list[str]) -> list[dict[str, str]]:
    """Pair Redis message-list items into Q&A history turns."""
    history: list[dict[str, str]] = []
    pending_question: str | None = None
    for raw in raw_items:
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue

        legacy_item = _message_to_history_item(payload)
        if legacy_item:
            if pending_question is not None:
                history.append({"question": pending_question, "answer": ""})
                pending_question = None
            history.append(legacy_item)
            continue

        role = payload.get("role")
        content = str(payload.get("content") or "").strip()
        if role == "user":
            if pending_question is not None:
                history.append({"question": pending_question, "answer": ""})
            pending_question = content
            continue
        if role == "assistant":
            if pending_question is not None:
                history.append({"question": pending_question, "answer": content})
                pending_question = None
            continue

    if pending_question is not None:
        history.append({"question": pending_question, "answer": ""})
    return history


def _has_existing_title(value: object) -> bool:
    """Return whether Redis metadata already has a meaningful session title."""
    if not isinstance(value, str):
        return value is not None
    stripped = value.strip()
    return bool(stripped) and stripped.lower() != "null"


def _message_payload(role: str, content: str, timestamp: str) -> str:
    """Build one Redis List message payload."""
    return json.dumps(
        {"role": role, "content": content, "timestamp": timestamp},
        ensure_ascii=False,
    )


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
        history = _messages_to_history(raw_items)
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
            _message_payload("user", question, now),
            _message_payload("assistant", answer, now),
        )
        await self._redis.expire(key, self._ttl_seconds)

        generated_title = title or _derive_session_title(question)
        should_return_title = True
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
            if _has_existing_title(existing_title):
                should_return_title = False
            else:
                metadata["title"] = generated_title
            await self._redis.hset(
                meta_key,
                conversation_id,
                json.dumps(metadata, ensure_ascii=False),
            )
        return generated_title if should_return_title else None


def _derive_session_title(question: str, limit: int = 24) -> str:
    """Derive a compact session title from the first question."""
    compact = " ".join(question.strip().split())
    if len(compact) <= limit:
        return compact
    return compact[:limit].rstrip() + "..."
