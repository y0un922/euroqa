"""Regression tests for the dispatch-layer guard in server/api/v1/query.py."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from server.agents.deps import QADeps
from server.agents.evidence import EvidenceBundle
from server.agents.qa_agent import AgentDecision
from server.api.v1.query import _ensure_retrieve_called_for_compose_rag
from server.config import ServerConfig
from server.models.schemas import Chunk, ChunkMetadata, ElementType


def _make_chunk(chunk_id: str = "chunk-recover") -> Chunk:
    return Chunk(
        chunk_id=chunk_id,
        content="Partial safety factors are specified in EN 1990 Annex A.",
        embedding_text="partial safety factor EN 1990",
        metadata=ChunkMetadata(
            source="EN 1990:2002",
            source_title="Basis of structural design",
            section_path=["Annex A"],
            page_numbers=[60],
            page_file_index=[59],
            clause_ids=["A.1"],
            element_type=ElementType.TEXT,
        ),
    )


def _make_deps(bundle: EvidenceBundle | None = None) -> QADeps:
    return QADeps(
        config=ServerConfig(),
        retriever=SimpleNamespace(),  # not used directly; _retrieve_impl is patched
        glossary={},
        bundle=bundle or EvidenceBundle(),
    )


@pytest.mark.asyncio
async def test_guard_noop_when_action_is_not_compose_rag():
    deps = _make_deps()
    decision = AgentDecision(action="chat", direct_reply="hello")

    result = await _ensure_retrieve_called_for_compose_rag(
        decision=decision,
        bundle=deps.bundle,
        deps=deps,
        question="hi",
        conversation_id="conv-1",
    )

    assert result is decision


@pytest.mark.asyncio
async def test_guard_noop_when_retrieve_was_called():
    deps = _make_deps()
    deps.bundle.tool_trace.append({"tool": "retrieve", "query": "x", "chunk_count": 2})
    decision = AgentDecision(action="compose_rag")

    result = await _ensure_retrieve_called_for_compose_rag(
        decision=decision,
        bundle=deps.bundle,
        deps=deps,
        question="混凝土分项系数",
        conversation_id="conv-2",
    )

    assert result is decision


@pytest.mark.asyncio
async def test_guard_forces_retrieve_and_recovers_when_chunks_found():
    deps = _make_deps()
    decision = AgentDecision(action="compose_rag")

    async def fake_retrieve_impl(ctx, query):
        ctx.context.bundle.chunks.append(_make_chunk())
        ctx.context.bundle.tool_trace.append(
            {"tool": "retrieve", "query": query, "chunk_count": 1}
        )
        return "ok"

    with patch(
        "server.agents.tools.retrieve._retrieve_impl",
        side_effect=fake_retrieve_impl,
    ):
        result = await _ensure_retrieve_called_for_compose_rag(
            decision=decision,
            bundle=deps.bundle,
            deps=deps,
            question="混凝土分项系数",
            conversation_id="conv-3",
        )

    assert result.action == "compose_rag"
    assert not deps.bundle.is_empty


@pytest.mark.asyncio
async def test_guard_downgrades_to_clarify_when_retrieve_still_empty():
    deps = _make_deps()
    decision = AgentDecision(action="compose_rag")

    async def fake_retrieve_impl(ctx, query):
        ctx.context.bundle.tool_trace.append(
            {"tool": "retrieve", "query": query, "chunk_count": 0}
        )
        return "no hits"

    with patch(
        "server.agents.tools.retrieve._retrieve_impl",
        side_effect=fake_retrieve_impl,
    ):
        result = await _ensure_retrieve_called_for_compose_rag(
            decision=decision,
            bundle=deps.bundle,
            deps=deps,
            question="混凝土分项系数",
            conversation_id="conv-4",
        )

    assert result.action == "clarify"
    assert result.direct_reply is not None
    assert "未检索到" in result.direct_reply
