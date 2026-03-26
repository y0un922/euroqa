"""Test generation layer (mock LLM)."""
from unittest.mock import AsyncMock, patch
import json

import pytest

from server.core.generation import build_prompt, parse_llm_response
from server.models.schemas import Confidence


class TestBuildPrompt:
    def test_includes_question(self, sample_text_chunk, sample_table_chunk):
        prompt = build_prompt("巴黎地铁寿命", [sample_text_chunk, sample_table_chunk], [])
        assert "巴黎地铁寿命" in prompt

    def test_includes_source_info(self, sample_text_chunk, sample_table_chunk):
        prompt = build_prompt("test", [sample_text_chunk], [])
        assert "EN 1990:2002" in prompt
        assert "2.3" in prompt or "Section 2" in prompt

    def test_includes_glossary(self, sample_text_chunk):
        glossary = {"设计使用年限": "design working life"}
        prompt = build_prompt("test", [sample_text_chunk], [], glossary_terms=glossary)
        assert "design working life" in prompt


class TestParseLlmResponse:
    def test_parse_valid_json(self):
        raw = json.dumps({
            "answer": "100年",
            "sources": [{"file": "EN 1990", "title": "Basis", "section": "2.3",
                         "page": 28, "clause": "Table 2.1", "original_text": "bridges",
                         "translation": "桥梁"}],
            "related_refs": ["Annex A"],
            "confidence": "high"
        })
        result = parse_llm_response(raw)
        assert result.answer == "100年"
        assert result.confidence == Confidence.HIGH
        assert len(result.sources) == 1

    def test_parse_json_in_code_block(self):
        raw = '```json\n{"answer": "test", "sources": [], "related_refs": [], "confidence": "low"}\n```'
        result = parse_llm_response(raw)
        assert result.answer == "test"
        assert result.confidence == Confidence.LOW

    def test_fallback_on_invalid_json(self):
        raw = "这是一个非 JSON 的回答"
        result = parse_llm_response(raw)
        assert result.answer == raw
        assert result.confidence == Confidence.LOW
