"""Regression tests for answer confidence normalization."""
import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from server.core.generation import _infer_answer_confidence, generate_answer
from server.models.schemas import Confidence


class TestInferAnswerConfidence:
    def test_grounded_high_score_is_high(self):
        assert _infer_answer_confidence([0.91], True, "grounded") == Confidence.HIGH

    def test_partial_caps_high_score_at_medium(self):
        assert _infer_answer_confidence([0.91], True, "partial") == Confidence.MEDIUM

    def test_not_grounded_forces_low(self):
        assert _infer_answer_confidence([0.99], True, "not_grounded") == Confidence.LOW

    def test_missing_sources_forces_low(self):
        assert _infer_answer_confidence([0.99], False, "grounded") == Confidence.LOW


@pytest.mark.asyncio
async def test_generate_answer_overrides_llm_confidence_with_retrieval_signal(
    sample_text_chunk,
):
    raw = json.dumps(
        {
            "answer": "根据条文应予规定。",
            "sources": [],
            "related_refs": [],
            "confidence": "low",
        }
    )

    class _FakeClient:
        def __init__(self, *args, **kwargs):
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

        async def _create(self, **kwargs):
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=raw))]
            )

    with patch("server.core.generation.AsyncOpenAI", _FakeClient):
        result = await generate_answer(
            "设计使用年限怎么确定？",
            [sample_text_chunk],
            [],
            scores=[0.91],
            groundedness="grounded",
        )

    assert result.confidence == Confidence.HIGH
