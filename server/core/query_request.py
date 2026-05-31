"""Helpers for query request aliases."""

from __future__ import annotations

from server.models.schemas import QueryRequest


def conversation_id_from_request(req: QueryRequest) -> str | None:
    """Resolve old conversation_id and external sessionId aliases."""
    return req.session_id or req.conversation_id


def uses_external_session(req: QueryRequest) -> bool:
    """Return whether the request opted into Redis-style session behavior."""
    return bool(req.session_id)
