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
