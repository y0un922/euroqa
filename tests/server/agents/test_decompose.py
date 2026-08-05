from __future__ import annotations

import pytest

from server.agents import decompose
from server.config import ServerConfig


@pytest.mark.asyncio
async def test_decompose_query_falls_back_on_bad_llm(monkeypatch):
    async def _raise(*args, **kwargs):
        raise ValueError("bad json")

    monkeypatch.setattr(decompose, "_call_decompose_llm", _raise)

    result = await decompose.decompose_query(
        "EN 1992-1-1 表 2.1N 的材料分项系数是多少？",
        conversation_history=[],
        glossary={},
        config=ServerConfig(),
    )

    assert result.rewritten_question == "EN 1992-1-1 表 2.1N 的材料分项系数是多少？"
    assert result.sub_queries == [result.rewritten_question]
    assert result.needs_retrieval
    assert result.filters == {"source": "EN 1992-1-1"}
    assert "Table 2.1N" in result.requested_objects


@pytest.mark.asyncio
async def test_decompose_query_normalizes_llm_payload(monkeypatch):
    async def _fake(*args, **kwargs):
        return """
        {
          "rewritten_question": "What are concrete material partial factors in EN 1992-1-1?",
          "sub_queries": [
            "EN 1992-1-1 concrete partial factor Table 2.1N",
            "EN 1992-1-1 reinforcement partial factor Table 2.1N"
          ],
          "implicit_context": "EN 1992-1-1 material factors",
          "needs_retrieval": true,
          "is_chitchat": false
        }
        """

    monkeypatch.setattr(decompose, "_call_decompose_llm", _fake)

    result = await decompose.decompose_query(
        "混凝土和钢筋材料分项系数？",
        conversation_history=[],
        glossary={},
        config=ServerConfig(),
    )

    assert result.rewritten_question.startswith("What are concrete")
    assert len(result.sub_queries) == 2
    assert result.implicit_context == "EN 1992-1-1 material factors"
    assert result.needs_retrieval
    assert not result.is_chitchat


@pytest.mark.asyncio
async def test_decompose_query_forwards_selected_sources(monkeypatch):
    captured: dict[str, object] = {}

    async def _fake(*args, **kwargs):
        captured.update(kwargs)
        return """
        {
          "rewritten_question": "What is a one-way spanning slab?",
          "sub_queries": [
            "one-way spanning slab definition",
            "one-way slab versus two-way slab criteria"
          ],
          "implicit_context": "",
          "needs_retrieval": true,
          "is_chitchat": false
        }
        """

    monkeypatch.setattr(decompose, "_call_decompose_llm", _fake)

    result = await decompose.decompose_query(
        "什么是单向板？",
        conversation_history=[],
        glossary={},
        config=ServerConfig(),
        selected_sources=["EN 1990:2002", "DG EN1990", "EN 1990:2002"],
    )

    assert captured["selected_sources"] == [
        "EN 1990:2002",
        "DG EN1990",
        "EN 1990:2002",
    ]
    assert result.sub_queries == [
        "one-way spanning slab definition",
        "one-way slab versus two-way slab criteria",
    ]
    assert "EN 1992" not in " ".join(result.sub_queries)


def test_decompose_prompt_forbids_invented_standard_codes():
    assert "Do NOT invent EN/BS/DG document numbers" in decompose._SYSTEM_PROMPT
    assert "one-way spanning slab definition" in decompose._SYSTEM_PROMPT
    assert 'prefixing "EN 1992-1-1"' in decompose._SYSTEM_PROMPT


def test_normalize_selected_sources_dedupes_and_caps():
    labels = [f"src-{i}" for i in range(30)]
    labels.extend(["src-1", "  ", "src-2"])
    normalized = decompose._normalize_selected_sources(labels)
    assert len(normalized) == 24
    assert normalized[0] == "src-0"
    assert normalized.count("src-1") == 1


@pytest.mark.asyncio
async def test_decompose_query_can_skip_retrieval(monkeypatch):
    async def _fake(*args, **kwargs):
        return """
        {
          "rewritten_question": "Hello",
          "sub_queries": [],
          "needs_retrieval": false,
          "is_chitchat": true
        }
        """

    monkeypatch.setattr(decompose, "_call_decompose_llm", _fake)

    result = await decompose.decompose_query(
        "你好",
        conversation_history=[],
        glossary={},
        config=ServerConfig(),
    )

    assert not result.needs_retrieval
    assert result.is_chitchat


@pytest.mark.asyncio
async def test_assess_evidence_normalizes_missing_queries(monkeypatch):
    async def _fake(*args, **kwargs):
        return """
        {
          "sufficient": false,
          "missing_queries": [
            "EN 1992-1-1 Table 2.1N material partial factors",
            "EN 1992-1-1 Table 2.1N material partial factors",
            "Designers Guide material partial factors explanation"
          ],
          "reason": "missing guide explanation"
        }
        """

    monkeypatch.setattr(decompose, "_call_assessment_llm", _fake)

    result = await decompose.assess_evidence(
        question="材料分项系数？",
        rewritten_question="material partial factors",
        implicit_context="Use EN 1992-1-1 framework",
        evidence_text="[Ref-1] partial factor text",
        previous_queries=["EN 1992-1-1 Table 2.1N material partial factors"],
        config=ServerConfig(),
    )

    assert not result.sufficient
    assert result.missing_queries == ["Designers Guide material partial factors explanation"]
    assert result.reason == "missing guide explanation"


def test_assessment_prompt_requires_english_missing_queries():
    assert "missing_queries 必须是英文" in decompose._ASSESSMENT_PROMPT
    assert "主题定义" in decompose._ASSESSMENT_PROMPT
    assert "隐含需求" in decompose._ASSESSMENT_PROMPT
    assert "不要编造用户/历史/已有证据未出现的规范号" in decompose._ASSESSMENT_PROMPT


@pytest.mark.asyncio
async def test_outline_answer_returns_normalized_outline(monkeypatch):
    async def _fake(*args, **kwargs):
        return """
        {
          "narrative_angle": "基于 EN 1992-1-1 的材料定义",
          "sections": [
            {"title": "强度定义", "bullets": ["说明 fck"], "ref_ids": ["Ref-1"]}
          ],
          "calculation_steps": [
            {"step": "1. 求 fcm", "formula": "fcm=fck+8", "ref_ids": ["Ref-1"]}
          ],
          "self_check": ["引用是否都来自 Ref"]
        }
        """

    monkeypatch.setattr(decompose, "_call_outline_llm", _fake)

    outline = await decompose.outline_answer(
        question="混凝土强度定义？",
        rewritten_question="concrete strength definitions",
        implicit_context="EN 1992-1-1",
        conversation_history=[],
        evidence_text="[Ref-1] fck means characteristic strength",
        config=ServerConfig(),
    )

    assert outline["narrative_angle"].startswith("基于 EN 1992")
    assert outline["sections"][0]["title"] == "强度定义"
    assert outline["calculation_steps"][0]["formula"] == "fcm=fck+8"
    assert outline["self_check"] == ["引用是否都来自 Ref"]


@pytest.mark.asyncio
async def test_outline_answer_falls_back_to_empty_outline(monkeypatch):
    async def _raise(*args, **kwargs):
        raise ValueError("bad outline json")

    monkeypatch.setattr(decompose, "_call_outline_llm", _raise)

    outline = await decompose.outline_answer(
        question="混凝土强度定义？",
        rewritten_question="concrete strength definitions",
        implicit_context="",
        conversation_history=[],
        evidence_text="[Ref-1] fck means characteristic strength",
        config=ServerConfig(),
    )

    assert outline == {}
