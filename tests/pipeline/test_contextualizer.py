"""Tests for contextual retrieval helper primitives."""
from __future__ import annotations

from dataclasses import FrozenInstanceError
from typing import get_args, get_type_hints

import pytest

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
