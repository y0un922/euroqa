from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from server.core.query_understanding import (
    _parse_expansion_result,
    analyze_query,
    expand_queries,
)
from server.models.schemas import QuestionType


def test_parse_expansion_result_ignores_rewritten_question():
    raw = json.dumps(
        {
            "rewritten_question": "混凝土保护层厚度的限值是多少？",
            "semantic": "concrete cover limit",
            "concepts": "durability exposure cover",
            "terms": "cmin cnom",
        }
    )

    result = _parse_expansion_result(raw)

    assert result is not None
    assert result.rewritten_question is None


def test_parse_expansion_result_missing_rewritten_question_is_none():
    raw = json.dumps(
        {
            "semantic": "concrete cover limit",
            "concepts": "durability exposure cover",
            "terms": "cmin cnom",
        }
    )

    result = _parse_expansion_result(raw)

    assert result is not None
    assert result.rewritten_question is None


@pytest.mark.asyncio
async def test_analyze_query_does_not_send_history_to_llm():
    llm_response = json.dumps(
        {
            "rewritten_question": "原始问题",
            "semantic": "design working life",
            "concepts": "durability service life",
            "terms": "working life",
        }
    )
    mock_llm = AsyncMock(return_value=llm_response)

    with patch("server.core.query_understanding._call_llm", mock_llm):
        result = await analyze_query(
            "原始问题",
            {},
            history=[{"question": "旧问题", "answer": "旧答案"}],
        )

    sent_prompt = mock_llm.call_args.args[0]
    assert "旧问题" not in sent_prompt
    assert result.rewritten_question is None
    assert result.expanded_queries[0] == "design working life"


@pytest.mark.asyncio
async def test_partial_factor_stabilization_preserves_rewritten_question():
    llm_response = json.dumps(
        {
            "rewritten_question": "混凝土结构中作用荷载和材料的分项系数是多少？",
            "semantic": "drifted concrete safety discussion",
            "concepts": "serviceability fatigue commentary",
            "terms": "psi crack width",
            "question_type": "mechanism",
            "intent_label": "explanation",
            "target_hint": {
                "document": "Designers' Guide EN 1992",
                "clause": "2.4.2",
                "object": "safety format commentary",
            },
            "reason_short": "model drifted to commentary",
        }
    )
    mock_llm = AsyncMock(return_value=llm_response)

    with patch("server.core.query_understanding._call_llm", mock_llm):
        result = await expand_queries(
            "请给出混凝土结构设计中相关作用荷载和材料的分项系数。",
            {},
            history=[
                {
                    "question": "混凝土结构中作用荷载和材料怎么考虑？",
                    "answer": "需要分别考虑作用和材料。",
                }
            ],
        )

    assert result.question_type == QuestionType.PARAMETER
    assert result.rewritten_question is None
    assert result.target_hint is None
