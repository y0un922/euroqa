"""POST /api/v1/sources/translate — on-demand source translation."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from server.deps import get_config
from server.core.generation import _fill_missing_source_translations
from server.models.schemas import (
    Source,
    SourceTranslationRequest,
    SourceTranslationResponse,
)

router = APIRouter()


@router.post("/sources/translate", response_model=SourceTranslationResponse)
async def translate_source(
    request: SourceTranslationRequest,
    config=Depends(get_config),
) -> SourceTranslationResponse:
    source = Source(
        file=request.file,
        document_id=request.document_id,
        title=request.title,
        section=request.section,
        page=request.page,
        clause=request.clause,
        original_text=request.original_text,
        locator_text=request.locator_text,
        translation="",
    )
    translated_sources = await _fill_missing_source_translations([source], config)
    if not translated_sources:
        raise HTTPException(502, "Source translation unavailable")

    translation = translated_sources[0].translation.strip()
    if not translation:
        raise HTTPException(502, "Source translation unavailable")

    return SourceTranslationResponse(translation=translation)
