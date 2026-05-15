"""POST /api/v1/sources/translate — on-demand source translation."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from server.deps import get_config
from server.core.generation import _fill_missing_source_translations
from server.models.schemas import (
    Source,
    SourceTranslationRequest,
    SourceTranslationResponse,
    TranslationRequest,
    TranslationResponse,
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


@router.post("/translate", response_model=TranslationResponse)
async def translate_text(
    request: TranslationRequest,
    config=Depends(get_config),
) -> TranslationResponse:
    """大模型翻译端点，符合外部接口文档契约。"""
    text = request.text.strip()
    if not text:
        raise HTTPException(400, "text 不能为空")

    context = request.context
    document_id = context.document_id if context else ""
    title = context.title if context else ""
    section = context.section if context else ""
    clause = context.clause if context else ""
    source = Source(
        file=document_id or title or "text",
        document_id=document_id or "",
        title=title or document_id or "text",
        section=section or "",
        page="",
        clause=clause or "",
        original_text=text,
        locator_text=clause or section or text[:80],
        translation="",
    )
    translated_sources = await _fill_missing_source_translations([source], config)
    translation = (
        translated_sources[0].translation.strip() if translated_sources else ""
    )
    if not translation:
        raise HTTPException(503, "翻译服务不可用")
    return TranslationResponse(translation=translation)
