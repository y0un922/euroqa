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
            "混凝土梁的抗弯承载力如何计算？",
            "风荷载的基本风压如何取值？",
            "设计使用年限怎么确定？",
            "荷载组合的基本原则是什么？",
            "地震设计的重要性系数怎么确定？",
        ],
        "domains": [
            {"id": "EN 1990", "name": "结构基础"},
            {"id": "EN 1991", "name": "荷载与作用"},
            {"id": "EN 1992", "name": "混凝土结构"},
            {"id": "EN 1993", "name": "钢结构"},
            {"id": "EN 1994", "name": "钢-混凝土组合结构"},
            {"id": "EN 1995", "name": "木结构"},
            {"id": "EN 1996", "name": "砌体结构"},
            {"id": "EN 1997", "name": "岩土工程"},
            {"id": "EN 1998", "name": "抗震设计"},
            {"id": "EN 1999", "name": "铝结构"},
        ],
        "query_types": [
            {"id": "clause", "name": "查条款"},
            {"id": "concept", "name": "问概念"},
            {"id": "parameter", "name": "算参数"},
            {"id": "comparison", "name": "比差异"},
        ],
    }
