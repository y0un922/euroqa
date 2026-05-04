"""Tests for contextual retrieval helper primitives."""
from __future__ import annotations

from dataclasses import FrozenInstanceError
from types import SimpleNamespace
from typing import get_args, get_type_hints
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from pipeline.config import PipelineConfig
from pipeline.contextualizer import Contextualizer
from pipeline.contextualizer import ContextualizeRequest, ContextualizeResult


def test_contextualize_request_is_frozen_and_defaults_chunk_alt():
    request = ContextualizeRequest(
        doc_summary="doc summary",
        parent_section_text="parent text",
        chunk_content="chunk text",
        chunk_kind="text",
        section_path=["Section 3", "3.2 Concrete"],
    )

    assert request.chunk_alt == ""

    with pytest.raises(FrozenInstanceError):
        request.chunk_content = "changed"


def test_contextualize_request_chunk_kind_literal_values():
    hints = get_type_hints(ContextualizeRequest)

    assert set(get_args(hints["chunk_kind"])) == {"text", "table", "formula", "image"}


def test_contextualize_result_is_frozen_and_defaults_description_empty():
    result = ContextualizeResult(context_blurb="context")

    assert result.semantic_description == ""

    with pytest.raises(FrozenInstanceError):
        result.context_blurb = "changed"


def _chat_response(content: str) -> SimpleNamespace:
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
    )


@pytest.mark.asyncio
async def test_generate_doc_summary_prompt_contains_title_and_outline():
    create = AsyncMock(return_value=_chat_response("Summary text."))
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))

    with patch("pipeline.contextualizer.AsyncOpenAI", return_value=client):
        contextualizer = Contextualizer(
            PipelineConfig(
                llm_api_key="key",
                llm_base_url="https://llm.test/v1",
                llm_model="demo-model",
                contextualize_retry_attempts=2,
            )
        )
        result = await contextualizer.generate_doc_summary(
            source_title="Design of concrete structures",
            doc_outline_text="1 General\n  Scope paragraph.",
        )

    assert result == "Summary text."
    kwargs = create.await_args.kwargs
    assert kwargs["model"] == "demo-model"
    assert kwargs["temperature"] == 0.1
    assert kwargs["max_tokens"] == 800
    prompt = kwargs["messages"][0]["content"]
    assert "Design of concrete structures" in prompt
    assert "1 General" in prompt


@pytest.mark.asyncio
async def test_generate_doc_summary_retries_timeout_then_succeeds():
    create = AsyncMock(
        side_effect=[
            httpx.ReadTimeout("timeout-1"),
            _chat_response("Recovered summary."),
        ]
    )
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))

    with patch("pipeline.contextualizer.AsyncOpenAI", return_value=client):
        contextualizer = Contextualizer(PipelineConfig(contextualize_retry_attempts=2))
        result = await contextualizer.generate_doc_summary("Title", "Outline")

    assert result == "Recovered summary."
    assert create.await_count == 2


@pytest.mark.asyncio
async def test_generate_doc_summary_retry_exhaustion_raises():
    create = AsyncMock(
        side_effect=[
            httpx.ReadTimeout("timeout-1"),
            httpx.ReadTimeout("timeout-2"),
            httpx.ReadTimeout("timeout-3"),
        ]
    )
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))

    with patch("pipeline.contextualizer.AsyncOpenAI", return_value=client):
        contextualizer = Contextualizer(PipelineConfig(contextualize_retry_attempts=3))
        with pytest.raises(httpx.ReadTimeout, match="timeout-3"):
            await contextualizer.generate_doc_summary("Title", "Outline")

    assert create.await_count == 3
