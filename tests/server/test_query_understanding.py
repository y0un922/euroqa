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
from server.models.schemas import AnswerMode, QuestionType


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

    def test_parses_guide_hint(self):
        raw = json.dumps({
            "semantic": "design value calculation example",
            "concepts": "load combination design value",
            "terms": "gamma psi combination",
            "question_type": "calculation",
            "guide_hint": {
                "need_example": True,
                "example_query": "design value load combination worked example",
                "example_kind": "worked_example",
            },
        })
        result = _parse_expansion_result(raw)
        assert result is not None
        assert result.guide_hint is not None
        assert result.guide_hint.need_example is True
        assert result.guide_hint.example_query == "design value load combination worked example"
        assert result.guide_hint.example_kind == "worked_example"

    def test_invalid_guide_hint_degrades_to_none(self):
        raw = json.dumps({
            "semantic": "design value calculation example",
            "concepts": "load combination design value",
            "terms": "gamma psi combination",
            "guide_hint": {
                "need_example": "yes",
                "example_query": ["not", "a", "string"],
            },
        })
        result = _parse_expansion_result(raw)
        assert result is not None
        assert result.guide_hint is None

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

    @pytest.mark.asyncio
    async def test_stabilizes_chinese_partial_factor_query_after_open_llm_routing(self):
        llm_response = json.dumps({
            "semantic": "concrete design safety discussion",
            "concepts": "serviceability fatigue commentary",
            "terms": "psi crack width",
            "question_type": "mechanism",
            "answer_mode": "open",
            "intent_label": "explanation",
            "confidence": 0.91,
            "target_hint": {
                "document": "Designers' Guide EN 1992",
                "clause": "2.4.2",
                "object": "safety format commentary",
            },
            "reason_short": "model drifted to commentary",
        })
        mock_llm = AsyncMock(return_value=llm_response)

        with patch("server.core.query_understanding._call_llm", mock_llm):
            result = await expand_queries(
                "请给出混凝土结构设计中相关作用荷载和材料的分项系数。",
                {},
            )

        assert result.queries == [
            "concrete structural design Eurocode partial factors for actions and materials",
            "EN 1990 EN 1992 EN 1992-1-1 actions materials loads load combination "
            "ultimate limit state safety factor partial factor concrete steel",
            "γF γG γQ γM γC γS γ_F γ_G γ_Q γ_M γ_C γ_S "
            "gammaF gammaG gammaQ gammaM gammaC gammaS "
            "gamma_F gamma_G gamma_Q gamma_M gamma_C gamma_S",
        ]
        assert result.question_type == QuestionType.PARAMETER
        assert result.routing is not None
        assert result.routing.answer_mode == AnswerMode.EXACT
        assert result.routing.intent_label == "limit"
        assert result.routing.target_hint.document == "EN 1990 and EN 1992-1-1"
        assert result.routing.target_hint.clause is None

    @pytest.mark.asyncio
    async def test_stabilizes_english_partial_factor_query(self):
        llm_response = json.dumps({
            "semantic": "where to find design values",
            "concepts": "values",
            "terms": "factors",
        })
        mock_llm = AsyncMock(return_value=llm_response)

        with patch("server.core.query_understanding._call_llm", mock_llm):
            result = await expand_queries(
                "In concrete structural design, what are the partial factors for "
                "actions, loads, and materials?",
                {},
            )

        assert result.question_type == QuestionType.PARAMETER
        assert result.routing is not None
        assert result.routing.answer_mode == AnswerMode.EXACT
        assert result.routing.target_hint.document == "EN 1990 and EN 1992-1-1"
        assert "γF" in result.queries[2]
        assert "gamma_F" in result.queries[2]

    @pytest.mark.asyncio
    async def test_stabilizes_gamma_symbol_partial_factor_query(self):
        llm_response = json.dumps({
            "semantic": "gamma symbols in concrete design",
            "concepts": "symbols",
            "terms": "gamma",
        })
        mock_llm = AsyncMock(return_value=llm_response)

        with patch("server.core.query_understanding._call_llm", mock_llm):
            result = await expand_queries(
                "For concrete design, what are γG, γQ, γC and γS?",
                {},
            )

        assert result.question_type == QuestionType.PARAMETER
        assert result.routing is not None
        assert result.routing.answer_mode == AnswerMode.EXACT
        assert result.routing.target_hint.object == "partial factors for actions and materials"

    @pytest.mark.asyncio
    async def test_does_not_stabilize_non_partial_factor_query(self):
        llm_response = json.dumps({
            "semantic": "concrete creep and shrinkage factors",
            "concepts": "creep shrinkage humidity member size",
            "terms": "phi epsilon_cs",
            "question_type": "mechanism",
            "answer_mode": "open",
            "intent_label": "mechanism",
            "confidence": 0.82,
            "target_hint": {
                "document": "EN 1992-1-1",
                "clause": None,
                "object": "creep and shrinkage",
            },
            "reason_short": "asks about influencing factors",
        })
        mock_llm = AsyncMock(return_value=llm_response)

        with patch("server.core.query_understanding._call_llm", mock_llm):
            result = await expand_queries("混凝土的徐变与收缩受哪些因素影响？", {})

        assert result.queries[0] == "concrete creep and shrinkage factors"
        assert result.question_type == QuestionType.MECHANISM
        assert result.routing is not None
        assert result.routing.answer_mode == AnswerMode.OPEN

    @pytest.mark.asyncio
    async def test_does_not_stabilize_generic_why_question(self):
        llm_response = json.dumps({
            "semantic": "why are safety factors used",
            "concepts": "safety factor explanation",
            "terms": "gamma explanation",
            "question_type": "mechanism",
            "answer_mode": "open",
            "intent_label": "explanation",
            "confidence": 0.84,
            "target_hint": {
                "document": "EN 1990",
                "clause": None,
                "object": "safety factor explanation",
            },
            "reason_short": "asks for explanation",
        })
        mock_llm = AsyncMock(return_value=llm_response)

        with patch("server.core.query_understanding._call_llm", mock_llm):
            result = await expand_queries("分项系数有什么作用？", {})

        assert result.queries[0] == "why are safety factors used"
        assert result.question_type == QuestionType.MECHANISM
        assert result.routing is not None
        assert result.routing.answer_mode == AnswerMode.OPEN

    @pytest.mark.asyncio
    async def test_does_not_stabilize_concrete_material_question_without_action_context(self):
        llm_response = json.dumps({
            "semantic": "concrete material partial factors",
            "concepts": "materials concrete factors",
            "terms": "gamma",
            "question_type": "parameter",
            "answer_mode": "open",
            "intent_label": "explanation",
            "confidence": 0.87,
            "target_hint": {
                "document": "EN 1992-1-1",
                "clause": None,
                "object": "material factors",
            },
            "reason_short": "missing action context",
        })
        mock_llm = AsyncMock(return_value=llm_response)

        with patch("server.core.query_understanding._call_llm", mock_llm):
            result = await expand_queries("混凝土材料的分项系数是什么？", {})

        assert result.queries[0] == "concrete material partial factors"
        assert result.question_type == QuestionType.PARAMETER
        assert result.routing is not None
        assert result.routing.answer_mode == AnswerMode.OPEN


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

    @pytest.mark.asyncio
    async def test_preserves_guide_hint(self):
        llm_response = json.dumps({
            "semantic": "design value calculation example",
            "concepts": "load combination design value",
            "terms": "gamma psi combination",
            "question_type": "calculation",
            "guide_hint": {
                "need_example": True,
                "example_query": "design value load combination worked example",
                "example_kind": "worked_example",
            },
        })
        mock_llm = AsyncMock(return_value=llm_response)

        with patch("server.core.query_understanding._call_llm", mock_llm):
            result = await analyze_query("怎么计算组合后的设计值，最好给个算例", {})

        assert result.question_type is not None
        assert result.question_type.value == "calculation"
        assert result.guide_hint is not None
        assert result.guide_hint.need_example is True
        assert result.guide_hint.example_kind == "worked_example"

    @pytest.mark.asyncio
    async def test_partial_factor_analysis_is_stable_exact_parameter(self):
        llm_response = json.dumps({
            "semantic": "drifted open discussion",
            "concepts": "commentary guide",
            "terms": "psi fatigue",
            "question_type": "mechanism",
            "answer_mode": "open",
            "intent_label": "explanation",
            "confidence": 0.9,
            "target_hint": {
                "document": "Designers' Guide",
                "clause": "2.4.2.4",
                "object": "commentary",
            },
            "reason_short": "drifted",
        })
        mock_llm = AsyncMock(return_value=llm_response)

        with patch("server.core.query_understanding._call_llm", mock_llm):
            result = await analyze_query(
                "请给出混凝土结构设计中相关作用荷载和材料的分项系数。",
                {},
            )

        assert result.expanded_queries[0] == (
            "concrete structural design Eurocode partial factors for actions and materials"
        )
        assert result.question_type == QuestionType.PARAMETER
        assert result.answer_mode == AnswerMode.EXACT
        assert result.intent_label == "limit"
        assert result.intent_confidence == pytest.approx(1.0)
        assert result.target_hint is not None
        assert result.target_hint.document == "EN 1990 and EN 1992-1-1"
        assert result.target_hint.clause is None
