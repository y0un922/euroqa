"""Read-only settings endpoints for frontend configuration."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from server.config import ServerConfig
from server.deps import get_config
from server.models.schemas import LlmSettingsResponse

router = APIRouter()


@router.get("/settings/llm", response_model=LlmSettingsResponse)
async def get_llm_settings(config: ServerConfig = Depends(get_config)) -> LlmSettingsResponse:
    """Return masked server-side defaults for the frontend settings panel."""
    return LlmSettingsResponse(
        base_url=config.llm_base_url,
        model=config.llm_model,
        enable_thinking=config.llm_enable_thinking,
        api_key_configured=bool(config.llm_api_key.strip()),
    )
