"""Test query understanding layer."""
from unittest.mock import AsyncMock, patch

import pytest

from server.core.query_understanding import classify_intent, rewrite_query, extract_filters
from server.models.schemas import IntentType


class TestClassifyIntent:
    def test_exact_query_formula(self):
        result = classify_intent("公式6.10怎么用")
        assert result == IntentType.EXACT

    def test_exact_query_table(self):
        result = classify_intent("Table A1.2 的内容")
        assert result == IntentType.EXACT

    def test_exact_query_clause_number(self):
        result = classify_intent("6.3.5条怎么理解")
        assert result == IntentType.EXACT

    def test_concept_query(self):
        result = classify_intent("什么是极限状态")
        assert result == IntentType.CONCEPT

    def test_reasoning_query(self):
        result = classify_intent("巴黎地铁的使用期限有多久")
        assert result == IntentType.REASONING


class TestExtractFilters:
    def test_extract_source_filter(self):
        filters = extract_filters("EN 1992 第6章的抗弯计算")
        assert filters.get("source") == "EN 1992"

    def test_extract_element_type_table(self):
        filters = extract_filters("表格A1.2的内容")
        assert filters.get("element_type") == "table"

    def test_extract_element_type_formula(self):
        filters = extract_filters("公式6.10怎么用")
        assert filters.get("element_type") == "formula"

    def test_no_filters(self):
        filters = extract_filters("混凝土梁如何设计")
        assert filters == {}


class TestRewriteQuery:
    @pytest.mark.asyncio
    async def test_rewrite_with_glossary(self):
        glossary = {"设计使用年限": "design working life"}
        mock_llm = AsyncMock(return_value="design working life infrastructure")
        with patch("server.core.query_understanding._call_llm", mock_llm):
            result = await rewrite_query("地铁的设计使用年限是多久", glossary)
            assert "design working life" in result
