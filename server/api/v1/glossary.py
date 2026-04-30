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
            "请给出混凝土结构设计中相关作用荷载和材料的分项系数。",
            "请给出混凝土材料的强度与变形的相关定义、相互关系及如何计算。",
            "有哪些因素会对混凝土的徐变与收缩产生影响?",
            "钢筋的主要特性有哪些?并给出相应总结。",
            "请问都有那些环境暴露等级?",
            "保护层都与什么因素相关，该怎么计算?",
            "结构分析的目的是什么?",
            "在哪些部位当线性应变分布的假设不成立时，可能需要进行局部分析?",
            "根据性质和功能，结构构件包括哪些类型?",
            "什么是单向板?",
            "欧标的截面计算的基本假设前提是什么？",
            "混凝土受压区应变-应力分布假设是什么？",
            "混凝土压碎应变限值是多少？",
            "极限受力状态下混凝土受压区高度限值为多少？",
            "弯矩重分布限值为多少？",
            "fcd 如何计算",
            "截面计算中材料分项安全系数为多少？",
            "混凝土抗压强度标准值、设计值与平均强度之间是什么关系？",
            "钢筋的锚固长度与搭接长度受哪些因素影响？",
            "什么情况下需要考虑二阶效应？",
            "受弯构件正截面承载力计算的一般步骤是什么？",
        ],
        "domains": [
            {"id": "EN 1992-1-1", "name": "混凝土结构设计"},
        ],
    }
