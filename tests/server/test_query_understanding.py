"""Test query understanding layer."""
import json
from unittest.mock import AsyncMock, patch

import pytest

from server.core.query_understanding import (
    analyze_query,
    expand_queries,
    extract_requested_objects,
    extract_filters,
    extract_preferred_element_type,
    _parse_expansion_result,
)
from server.models.schemas import AnswerMode


class TestExtractFilters:
    def test_extract_source_filter(self):
        filters = extract_filters("EN 1992 第6章的抗弯计算")
        assert filters.get("source") == "EN 1992"

    def test_extract_dg_source_filter(self):
        filters = extract_filters("DG EN1990 里面关于 design working life 是怎么解释的？")
        assert filters.get("source") == "DG EN1990"

    def test_element_type_no_longer_in_filters(self):
        """element_type 已从 filters 中移除，改为 preferred_element_type boost。"""
        filters = extract_filters("表格A1.2的内容")
        assert "element_type" not in filters

    def test_formula_no_longer_in_filters(self):
        filters = extract_filters("公式6.10怎么用")
        assert "element_type" not in filters

    def test_no_filters(self):
        filters = extract_filters("混凝土梁如何设计")
        assert filters == {}


class TestExtractPreferredElementType:
    def test_table_keyword_chinese(self):
        assert extract_preferred_element_type("表格A1.2的内容") == "table"

    def test_table_keyword_english(self):
        assert extract_preferred_element_type("What is in Table 3.1?") == "table"

    def test_formula_keyword_chinese(self):
        assert extract_preferred_element_type("公式6.10怎么用") == "formula"

    def test_formula_keyword_english(self):
        assert extract_preferred_element_type("How to use formula 6.10?") == "formula"

    def test_no_preference(self):
        assert extract_preferred_element_type("混凝土梁如何设计") is None


class TestExtractRequestedObjects:
    def test_extracts_explicit_clause_and_table_from_question(self):
        requested = extract_requested_objects(
            "3.1.7 和表3.1里面，混凝土受压应变限值怎么取？"
        )

        assert requested == ["3.1.7", "Table 3.1"]

    def test_merges_target_hint_clause_and_object_labels(self):
        requested = extract_requested_objects(
            "欧标里这个值怎么定义？",
            target_hint={
                "clause": "3.1.7",
                "object": "Table 3.1",
            },
        )

        assert requested == ["3.1.7", "Table 3.1"]


class TestParseExpansionResult:
    def test_parses_valid_json(self):
        raw = json.dumps({
            "semantic": "design compressive strength of C30/37",
            "concepts": "concrete strength class characteristic value",
            "terms": "fcd fck αcc γc",
        })
        result = _parse_expansion_result(raw)
        assert result is not None
        assert len(result.queries) == 3
        assert "C30/37" in result.queries[0]
        assert "fcd" in result.queries[2]

    def test_parses_json_in_code_block(self):
        raw = '```json\n{"semantic": "shear design", "concepts": "VRd", "terms": "Asw"}\n```'
        result = _parse_expansion_result(raw)
        assert result is not None
        assert len(result.queries) == 3

    def test_returns_none_on_invalid_json(self):
        assert _parse_expansion_result("not json at all") is None

    def test_skips_empty_values(self):
        raw = json.dumps({"semantic": "shear", "concepts": "", "terms": "VRd"})
        result = _parse_expansion_result(raw)
        assert result is not None
        assert len(result.queries) == 2

    def test_parses_question_type(self):
        raw = json.dumps({
            "semantic": "fcd calculation",
            "concepts": "design compressive strength",
            "terms": "fcd fck",
            "question_type": "parameter",
            "context": {"concrete_class": "C30/37"},
        })
        result = _parse_expansion_result(raw)
        assert result is not None
        assert result.question_type is not None
        assert result.question_type.value == "parameter"
        assert result.engineering_context is not None
        assert result.engineering_context.concrete_class == "C30/37"

    def test_parses_routing_metadata(self):
        raw = json.dumps({
            "semantic": "basic assumptions for section design",
            "concepts": "ultimate moment resistance assumptions",
            "terms": "plane sections remain plane",
            "answer_mode": "exact",
            "intent_label": "assumption",
            "confidence": 0.92,
            "target_hint": {
                "document": "EN 1992-1-1",
                "clause": "6.1",
                "object": "basic assumptions",
            },
            "reason_short": "asks for direct normative assumptions",
        })
        result = _parse_expansion_result(raw)

        assert result is not None
        assert result.routing is not None
        assert result.routing.answer_mode == AnswerMode.EXACT
        assert result.routing.intent_label == "assumption"
        assert result.routing.intent_confidence == pytest.approx(0.92)
        assert result.routing.target_hint is not None
        assert result.routing.target_hint.document == "EN 1992-1-1"
        assert result.routing.target_hint.clause == "6.1"
        assert result.routing.target_hint.object == "basic assumptions"
        assert result.routing.reason_short == "asks for direct normative assumptions"

    def test_invalid_question_type_returns_none_type(self):
        raw = json.dumps({
            "semantic": "test",
            "concepts": "test",
            "terms": "test",
            "question_type": "invalid_type",
        })
        result = _parse_expansion_result(raw)
        assert result is not None
        assert result.question_type is None

    def test_malformed_routing_metadata_degrades_to_none(self):
        raw = json.dumps({
            "semantic": "test",
            "concepts": "test",
            "terms": "test",
            "answer_mode": "unsupported_mode",
            "intent_label": 123,
            "confidence": "high",
            "target_hint": "EN 1992-1-1 6.1",
            "reason_short": ["not", "a", "string"],
        })
        result = _parse_expansion_result(raw)

        assert result is not None
        assert result.routing is None

    def test_exact_not_grounded_mode_is_explicitly_rejected_in_query_understanding(self):
        raw = json.dumps({
            "semantic": "basic assumptions for section design",
            "concepts": "ultimate moment resistance assumptions",
            "terms": "plane sections remain plane",
            "answer_mode": "exact_not_grounded",
            "intent_label": "assumption",
            "confidence": 0.92,
            "target_hint": {
                "document": "EN 1992-1-1",
                "clause": "6.1",
                "object": "basic assumptions",
            },
            "reason_short": "groundedness is not decided in query understanding",
        })

        result = _parse_expansion_result(raw)

        assert result is not None
        assert result.routing is None

    def test_bool_confidence_is_rejected(self):
        raw = json.dumps({
            "semantic": "basic assumptions for section design",
            "concepts": "ultimate moment resistance assumptions",
            "terms": "plane sections remain plane",
            "answer_mode": "exact",
            "intent_label": "assumption",
            "confidence": True,
            "target_hint": {
                "document": "EN 1992-1-1",
                "clause": "6.1",
                "object": "basic assumptions",
            },
            "reason_short": "asks for direct normative assumptions",
        })

        result = _parse_expansion_result(raw)

        assert result is not None
        assert result.routing is None

    def test_target_hint_strips_whitespace_and_normalizes_blank_strings(self):
        raw = json.dumps({
            "semantic": "basic assumptions for section design",
            "concepts": "ultimate moment resistance assumptions",
            "terms": "plane sections remain plane",
            "answer_mode": "exact",
            "intent_label": "assumption",
            "confidence": 0.92,
            "target_hint": {
                "document": "  EN 1992-1-1  ",
                "clause": "   ",
                "object": "\tbasic assumptions\n",
            },
            "reason_short": "asks for direct normative assumptions",
        })

        result = _parse_expansion_result(raw)

        assert result is not None
        assert result.routing is not None
        assert result.routing.target_hint is not None
        assert result.routing.target_hint.document == "EN 1992-1-1"
        assert result.routing.target_hint.clause is None
        assert result.routing.target_hint.object == "basic assumptions"

    def test_backward_compatible_with_old_format(self):
        raw = json.dumps({
            "semantic": "test query",
            "concepts": "related concepts",
            "terms": "var1 var2",
        })
        result = _parse_expansion_result(raw)
        assert result is not None
        assert len(result.queries) == 3
        assert result.question_type is None
        assert result.engineering_context is None
        assert result.routing is None


class TestExpandQueries:
    @pytest.mark.asyncio
    async def test_expand_with_glossary(self):
        glossary = {"设计使用年限": "design working life"}
        llm_response = json.dumps({
            "semantic": "design working life of metro infrastructure",
            "concepts": "service life durability design period",
            "terms": "tL working life category",
        })
        mock_llm = AsyncMock(return_value=llm_response)
        with patch("server.core.query_understanding._call_llm", mock_llm):
            result = await expand_queries("地铁的设计使用年限是多久", glossary)
            assert len(result.queries) == 3
            assert "design working life" in result.queries[0]

    @pytest.mark.asyncio
    async def test_preserves_routing_metadata(self):
        llm_response = json.dumps({
            "semantic": "basic assumptions for section design",
            "concepts": "ultimate moment resistance assumptions",
            "terms": "plane sections remain plane",
            "answer_mode": "exact",
            "intent_label": "assumption",
            "confidence": 0.92,
            "target_hint": {
                "document": "EN 1992-1-1",
                "clause": "6.1",
                "object": "basic assumptions",
            },
            "reason_short": "asks for direct normative assumptions",
        })
        mock_llm = AsyncMock(return_value=llm_response)

        with patch("server.core.query_understanding._call_llm", mock_llm):
            result = await expand_queries("欧标的截面计算的基本假设前提是什么", {})

        assert result.routing is not None
        assert result.routing.answer_mode == AnswerMode.EXACT
        assert result.routing.intent_label == "assumption"
        assert result.routing.target_hint is not None
        assert result.routing.target_hint.clause == "6.1"

    @pytest.mark.asyncio
    async def test_falls_back_to_original_on_failure(self):
        mock_llm = AsyncMock(side_effect=RuntimeError("llm unavailable"))
        with patch("server.core.query_understanding._call_llm", mock_llm):
            result = await expand_queries("混凝土强度", {})
            assert result.queries == ["混凝土强度"]
            assert result.routing is None

    @pytest.mark.asyncio
    async def test_low_confidence_routing_falls_back_safely(self):
        llm_response = json.dumps({
            "semantic": "section design assumptions",
            "concepts": "design assumptions",
            "terms": "plane sections",
            "answer_mode": "exact",
            "intent_label": "assumption",
            "confidence": 0.2,
            "target_hint": {"document": "EN 1992-1-1"},
            "reason_short": "low confidence",
        })
        mock_llm = AsyncMock(return_value=llm_response)

        with patch("server.core.query_understanding._call_llm", mock_llm):
            result = await expand_queries("欧标的基本假设是什么", {})

        assert result.queries[0] == "section design assumptions"
        assert result.routing is None


class TestAnalyzeQuery:
    @pytest.mark.asyncio
    async def test_falls_back_to_original_question_when_llm_fails(self):
        glossary = {"设计使用年限": "design working life"}
        mock_llm = AsyncMock(side_effect=RuntimeError("llm unavailable"))

        with patch("server.core.query_understanding._call_llm", mock_llm):
            result = await analyze_query("巴黎地铁的设计使用年限有多久？", glossary)

        assert result.rewritten_query == "巴黎地铁的设计使用年限有多久？"
        assert result.expanded_queries == ["巴黎地铁的设计使用年限有多久？"]

    @pytest.mark.asyncio
    async def test_preserves_routing_metadata(self):
        llm_response = json.dumps({
            "semantic": "basic assumptions for section design",
            "concepts": "ultimate moment resistance assumptions",
            "terms": "plane sections remain plane",
            "answer_mode": "exact",
            "intent_label": "assumption",
            "confidence": 0.92,
            "target_hint": {
                "document": "EN 1992-1-1",
                "clause": "6.1",
                "object": "basic assumptions",
            },
            "reason_short": "asks for direct normative assumptions",
        })
        mock_llm = AsyncMock(return_value=llm_response)

        with patch("server.core.query_understanding._call_llm", mock_llm):
            result = await analyze_query("欧标的截面计算的基本假设前提是什么", {})

        assert result.answer_mode == AnswerMode.EXACT
        assert result.intent_label == "assumption"
        assert result.intent_confidence == pytest.approx(0.92)
        assert result.target_hint is not None
        assert result.target_hint.document == "EN 1992-1-1"
        assert result.target_hint.clause == "6.1"
        assert result.reason_short == "asks for direct normative assumptions"
