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

    def get_session(self, conversation_id: str) -> dict[str, Any]:
        """Return one frontend-facing session from the in-memory cache."""
        state = self.get_or_create(conversation_id)
        messages = [
            {
                "id": f"{conversation_id}-{index}",
                "question": item.get("question", ""),
                "answer": item.get("answer", ""),
                "reasoning": "",
                "status": "done",
                "confidence": "none",
                "sources": [],
                "related_refs": [],
                "degraded": False,
                "conversation_id": conversation_id,
                "retrieval_context": None,
                "question_type": None,
                "engineering_context": None,
                "progress_events": [],
                "commentaries": [],
            }
            for index, item in enumerate(state.history, start=1)
        ]
        return {
            "session_id": conversation_id,
            "conversation_id": conversation_id,
            "title": None,
            "updated_at": None,
            "messages": messages,
        }

    def get_sessions(self, user_id: str) -> dict[str, Any]:
        """Return frontend-facing session summaries from the in-memory cache."""
        prefix = f"{user_id}_"
        sessions = []
        for conversation_id, state in self._cache.items():
            if not conversation_id.startswith(prefix):
                continue
            sessions.append(
                {
                    "session_id": conversation_id,
                    "conversation_id": conversation_id,
                    "title": None,
                    "updated_at": None,
                    "message_count": len(state.history),
                }
            )
        return {"sessions": sessions}

    def delete_session(self, conversation_id: str) -> dict[str, Any]:
        """Delete one session from the in-memory cache."""
        deleted = conversation_id in self._cache
        self._cache.pop(conversation_id, None)
        return {"session_id": conversation_id, "deleted": deleted}


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


def _message_content(payload: dict[str, Any]) -> str:
    """Return a normalized message content string."""
    return str(payload.get("content") or "").strip()


def _assistant_response(payload: dict[str, Any]) -> dict[str, Any]:
    """Return the stored assistant response snapshot when available."""
    response = payload.get("response")
    return response if isinstance(response, dict) else {}


def _assistant_sources(payload: dict[str, Any], response: dict[str, Any]) -> list:
    """Return persisted sources from response snapshot or assistant metadata."""
    sources = response.get("sources", payload.get("sources", []))
    return sources if isinstance(sources, list) else []


def _assistant_related_refs(payload: dict[str, Any], response: dict[str, Any]) -> list:
    """Return persisted related references from response snapshot or metadata."""
    related_refs = response.get(
        "relatedRefs",
        response.get(
            "related_refs", payload.get("relatedRefs", payload.get("related_refs", []))
        ),
    )
    return related_refs if isinstance(related_refs, list) else []


def _conversation_turns_from_messages(
    conversation_id: str,
    raw_items: list[str],
) -> list[dict[str, Any]]:
    """Convert Redis role messages into frontend chat turns."""
    turns: list[dict[str, Any]] = []
    pending_question: dict[str, Any] | None = None
    turn_index = 0

    for raw in raw_items:
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue

        legacy_item = _message_to_history_item(payload)
        if legacy_item:
            turn_index += 1
            turns.append(
                {
                    "id": f"{conversation_id}-{turn_index}",
                    "question": legacy_item["question"],
                    "answer": legacy_item["answer"],
                    "reasoning": "",
                    "status": "done",
                    "confidence": "none",
                    "sources": [],
                    "related_refs": [],
                    "degraded": False,
                    "conversation_id": conversation_id,
                    "retrieval_context": None,
                    "question_type": None,
                    "engineering_context": None,
                    "progress_events": [],
                    "commentaries": [],
                }
            )
            pending_question = None
            continue

        role = payload.get("role")
        if role == "user":
            if pending_question is not None:
                turn_index += 1
                turns.append(
                    {
                        "id": f"{conversation_id}-{turn_index}",
                        "question": _message_content(pending_question),
                        "answer": "",
                        "reasoning": "",
                        "status": "error",
                        "confidence": "none",
                        "sources": [],
                        "related_refs": [],
                        "degraded": False,
                        "conversation_id": conversation_id,
                        "error_message": "上次回答在生成过程中中断，已保留问题。",
                        "retrieval_context": None,
                        "question_type": None,
                        "engineering_context": None,
                        "progress_events": [],
                        "commentaries": [],
                    }
                )
            pending_question = payload
            continue

        if role != "assistant":
            continue

        if pending_question is None:
            continue

        response = _assistant_response(payload)
        answer = str(
            response.get("normalized_answer")
            or response.get("answer")
            or payload.get("content")
            or ""
        )
        confidence = str(
            response.get("confidence") or payload.get("confidence") or "none"
        )
        retrieval_context = response.get(
            "retrieval_context",
            response.get("retrievalContext", payload.get("retrievalContext")),
        )
        question_type = response.get(
            "question_type",
            response.get("questionType", payload.get("questionType")),
        )
        engineering_context = response.get(
            "engineering_context",
            response.get("engineeringContext", payload.get("engineeringContext")),
        )
        thinking = str(response.get("thinking") or payload.get("thinking") or "")
        turn_index += 1
        turns.append(
            {
                "id": f"{conversation_id}-{turn_index}",
                "question": _message_content(pending_question),
                "answer": answer,
                "reasoning": thinking,
                "status": "done",
                "confidence": confidence,
                "sources": _assistant_sources(payload, response),
                "related_refs": _assistant_related_refs(payload, response),
                "degraded": bool(
                    response.get("degraded", payload.get("degraded", False))
                ),
                "conversation_id": conversation_id,
                "retrieval_context": retrieval_context
                if isinstance(retrieval_context, dict)
                else None,
                "question_type": question_type
                if isinstance(question_type, str)
                else None,
                "engineering_context": engineering_context
                if isinstance(engineering_context, dict)
                else None,
                "progress_events": [],
                "commentaries": [],
            }
        )
        pending_question = None

    if pending_question is not None:
        turn_index += 1
        turns.append(
            {
                "id": f"{conversation_id}-{turn_index}",
                "question": _message_content(pending_question),
                "answer": "",
                "reasoning": "",
                "status": "error",
                "confidence": "none",
                "sources": [],
                "related_refs": [],
                "degraded": False,
                "conversation_id": conversation_id,
                "error_message": "上次回答在生成过程中中断，已保留问题。",
                "retrieval_context": None,
                "question_type": None,
                "engineering_context": None,
                "progress_events": [],
                "commentaries": [],
            }
        )

    return turns


def _has_existing_title(value: object) -> bool:
    """Return whether Redis metadata already has a meaningful session title."""
    if not isinstance(value, str):
        return value is not None
    stripped = value.strip()
    return bool(stripped) and stripped.lower() != "null"


def _metadata_string(metadata: dict[str, Any], key: str) -> str | None:
    """Return a non-empty metadata string."""
    value = metadata.get(key)
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _session_summary_title(
    conversation_id: str,
    metadata: dict[str, Any],
    turns: list[dict[str, Any]],
) -> str:
    """Return a display title for one session summary."""
    return (
        _metadata_string(metadata, "title")
        or str(turns[0].get("question") or "").strip()
        or conversation_id
    )


def _message_payload(
    role: str,
    content: str,
    timestamp: str,
    *,
    metadata: dict[str, Any] | None = None,
) -> str:
    """Build one Redis List message payload."""
    payload: dict[str, Any] = {"role": role, "content": content, "timestamp": timestamp}
    if metadata:
        payload.update(metadata)
    return json.dumps(
        payload,
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

    async def get_session_async(self, conversation_id: str) -> dict[str, Any]:
        """Return one frontend-facing session restored from Redis."""
        raw_items = await self._redis.lrange(f"context:{conversation_id}", 0, -1)
        user_id = _user_id_from_session_id(conversation_id)
        metadata: dict[str, Any] = {}
        if user_id:
            raw_meta = await self._redis.hget(
                f"user:{user_id}:sessions",
                conversation_id,
            )
            if raw_meta:
                try:
                    loaded = json.loads(raw_meta)
                    if isinstance(loaded, dict):
                        metadata = loaded
                except json.JSONDecodeError:
                    metadata = {}

        return {
            "session_id": conversation_id,
            "conversation_id": conversation_id,
            "title": metadata.get("title")
            if isinstance(metadata.get("title"), str)
            else None,
            "updated_at": metadata.get("updatedAt")
            if isinstance(metadata.get("updatedAt"), str)
            else None,
            "messages": _conversation_turns_from_messages(conversation_id, raw_items),
        }

    async def get_sessions_async(self, user_id: str) -> dict[str, Any]:
        """Return frontend-facing session summaries restored from Redis."""
        raw_sessions = await self._redis.hgetall(f"user:{user_id}:sessions")
        sessions = []
        for conversation_id, raw_meta in raw_sessions.items():
            metadata: dict[str, Any] = {}
            try:
                loaded = json.loads(raw_meta)
                if isinstance(loaded, dict):
                    metadata = loaded
            except json.JSONDecodeError:
                metadata = {}

            raw_items = await self._redis.lrange(f"context:{conversation_id}", 0, -1)
            turns = _conversation_turns_from_messages(conversation_id, raw_items)
            sessions.append(
                {
                    "session_id": conversation_id,
                    "conversation_id": conversation_id,
                    "title": _session_summary_title(
                        conversation_id,
                        metadata,
                        turns,
                    ),
                    "updated_at": _metadata_string(metadata, "updatedAt"),
                    "message_count": len(turns),
                }
            )

        sessions.sort(key=lambda item: item.get("updated_at") or "", reverse=True)
        return {"sessions": sessions}

    async def delete_session_async(self, conversation_id: str) -> dict[str, Any]:
        """Delete one frontend-facing session from Redis."""
        deleted_count = await self._redis.delete(f"context:{conversation_id}")
        user_id = _user_id_from_session_id(conversation_id)
        metadata_deleted = 0
        if user_id:
            metadata_deleted = await self._redis.hdel(
                f"user:{user_id}:sessions",
                conversation_id,
            )
        return {
            "session_id": conversation_id,
            "deleted": bool(deleted_count or metadata_deleted),
        }

    def add_turn(self, conversation_id: str, question: str, answer: str) -> None:
        del conversation_id, question, answer

    async def add_turn_async(
        self,
        conversation_id: str,
        question: str,
        answer: str,
        *,
        title: str | None = None,
        sources: list[dict[str, Any]] | None = None,
        related_refs: list[str] | None = None,
        retrieval_context: dict[str, Any] | None = None,
        question_type: str | None = None,
        engineering_context: dict[str, Any] | None = None,
        answer_mode: str | None = None,
        groundedness: str | None = None,
        thinking: str | None = None,
        response_payload: dict[str, Any] | None = None,
    ) -> str | None:
        """Append one Q&A turn and update session metadata."""
        now = _utc_iso()
        key = f"context:{conversation_id}"
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
        else:
            meta_key = None
            metadata = {}

        title_for_response = generated_title if should_return_title else None
        assistant_metadata: dict[str, Any] = {}
        if sources:
            assistant_metadata["sources"] = sources
        if related_refs:
            assistant_metadata["relatedRefs"] = related_refs
        if retrieval_context:
            assistant_metadata["retrievalContext"] = retrieval_context
        if question_type:
            assistant_metadata["questionType"] = question_type
        if engineering_context:
            assistant_metadata["engineeringContext"] = engineering_context
        if answer_mode:
            assistant_metadata["answerMode"] = answer_mode
        if groundedness:
            assistant_metadata["groundedness"] = groundedness
        if thinking:
            assistant_metadata["thinking"] = thinking
        if response_payload:
            response_snapshot = dict(response_payload)
            response_snapshot["title"] = title_for_response
            assistant_metadata["response"] = response_snapshot
        await self._redis.rpush(
            key,
            _message_payload("user", question, now),
            _message_payload("assistant", answer, now, metadata=assistant_metadata),
        )

        if meta_key is not None:
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
