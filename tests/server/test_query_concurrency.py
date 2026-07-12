"""Concurrency tests for POST /api/v1/query/stream."""

from __future__ import annotations

import asyncio
import json
import time
from types import SimpleNamespace

import httpx
import pytest

from server import deps
from server.agents.evidence import EvidenceBundle
from server.agents.orchestrator import AgentResult
from server.config import ServerConfig
from server.core.retrieval import RetrievalResult
from server.models.schemas import Chunk, ChunkMetadata, ElementType
from server.main import app


SINGLE_REQUEST_DELAY_SECONDS = 0.5


def _server_config(**overrides) -> ServerConfig:
    overrides.setdefault("access_password", "")
    return ServerConfig(**overrides)


def _make_chunk() -> Chunk:
    return Chunk(
        chunk_id="chunk-1",
        content="Eurocode evidence.",
        embedding_text="Eurocode evidence",
        metadata=ChunkMetadata(
            source="EN 1990:2002",
            source_title="Basis of structural design",
            section_path=["1"],
            page_numbers=[1],
            page_file_index=[0],
            clause_ids=["1"],
            element_type=ElementType.TEXT,
        ),
    )


class _FakeRetriever:
    async def prefetch_vectors(self, query, filters=None):
        return []

    async def retrieve(self, **kwargs):
        return RetrievalResult(chunks=[_make_chunk()], parent_chunks=[], scores=[0.9])


class _FakeConversationManager:
    def get_or_create(self, conversation_id):
        return SimpleNamespace(conversation_id=conversation_id or "conv-1", history=[])

    def add_turn(self, conversation_id, question, answer):
        return None


def _analysis_stub(question: str):
    return SimpleNamespace(
        expanded_queries=[question],
        original_question=question,
        filters={},
        matched_terms={},
        intent_label=None,
        question_type=None,
        engineering_context=None,
        guide_hint=None,
        target_hint=None,
        requested_objects=[],
        preferred_element_type=None,
    )


def _event_data_by_type(response_text: str) -> dict[str, list[dict]]:
    events: dict[str, list[dict]] = {}
    current_event: str | None = None
    for line in response_text.splitlines():
        if line.startswith("event: "):
            current_event = line.removeprefix("event: ").strip()
            events.setdefault(current_event, [])
        elif line.startswith("data: ") and current_event:
            events[current_event].append(json.loads(line.removeprefix("data: ")))
    return events


@pytest.mark.asyncio
async def test_query_stream_handles_ten_concurrent_requests(monkeypatch):
    async def _fake_dispatch_agent(
        question,
        req,
        config,
        retriever,
        glossary,
        conv_mgr,
        tool_progress=None,
    ):
        conv = conv_mgr.get_or_create(req.session_id or req.conversation_id)
        bundle = EvidenceBundle()
        bundle.add_retrieval(await retriever.retrieve())
        bundle.tool_trace.append({"tool": "prefetch_retrieve", "chunk_count": 1})
        return AgentResult(
            agent_reply="ok [Ref-1]",
            bundle=bundle,
            conv=conv,
            deps=None,
        )

    async def _fake_dispatch_agent_streamed(*args, **kwargs):
        yield await _fake_dispatch_agent(*args, **kwargs)

    app.dependency_overrides = {
        deps.get_config: lambda: _server_config(access_password=""),
        deps.get_retriever: lambda: _FakeRetriever(),
        deps.get_conversation_manager: lambda: _FakeConversationManager(),
        deps.get_glossary: lambda: {},
    }
    monkeypatch.setattr(
        "server.api.v1.query.dispatch_agent_streamed",
        _fake_dispatch_agent_streamed,
    )

    async def _post_stream(client: httpx.AsyncClient) -> httpx.Response:
        return await client.post(
            "/api/v1/query/stream",
            json={"question": "欧标的截面计算的基本假设前提是什么", "stream": True},
        )

    transport = httpx.ASGITransport(app=app)
    try:
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as client:
            started_at = time.perf_counter()
            responses = await asyncio.gather(*(_post_stream(client) for _ in range(10)))
            elapsed = time.perf_counter() - started_at
    finally:
        app.dependency_overrides = {}

    assert elapsed <= SINGLE_REQUEST_DELAY_SECONDS * 1.5
    assert all(response.status_code == 200 for response in responses)

    for response in responses:
        events = _event_data_by_type(response.text)
        assert "done" in events
        done = events["done"][-1]
        assert done["code"] == 200
        assert done["sources"]
        assert done["answerMode"] == "fallback"
