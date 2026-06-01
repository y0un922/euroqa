"""Session restore endpoints backed by the conversation store."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from server.deps import get_conversation_manager
from server.models.schemas import ConversationSessionResponse

router = APIRouter()


@router.get("/sessions/{session_id}", response_model=ConversationSessionResponse)
async def get_session(
    session_id: str,
    conv_mgr=Depends(get_conversation_manager),
) -> ConversationSessionResponse:
    """Restore a chat session from Redis or the in-memory fallback store."""
    getter = getattr(conv_mgr, "get_session_async", None)
    if getter is not None:
        payload = await getter(session_id)
    else:
        payload = conv_mgr.get_session(session_id)
    return ConversationSessionResponse.model_validate(payload)
