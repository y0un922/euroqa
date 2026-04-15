"""GET /api/v1/glossary, /api/v1/suggest."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from server.deps import get_glossary
from server.models.schemas import GlossaryEntry

router = APIRouter()


@router.get("/glossary", response_model=list[GlossaryEntry])
async def list_glossary(
    q: str | None = None,
    glossary=Depends(get_glossary),
) -> list[GlossaryEntry]:
    entries = []
    for zh, en in glossary.items():
        if q and q not in zh and q not in en:
            continue
        entries.append(GlossaryEntry(zh=[zh], en=en))
    return entries


@router.get("/suggest")
async def suggest() -> dict:
    return {
        "hot_questions": [
            "结构分析的目的是什么?",
            "在哪些部位当线性应变分布的假设不成立时，可能需要进行局部分析?",
            "根据性质和功能，结构构件包括哪些类型?",
            "什么是单向板?",
            "长细比是如何定义的?",
            "有效长度是如何定义的?",
        ],
        "domains": [
            {"id": "EN 1992-1-1", "name": "混凝土结构设计"},
        ],
    }
