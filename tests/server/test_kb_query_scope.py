from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from server import deps
from server.api.v1 import query as query_module
from server.config import ServerConfig
from server.main import app


def _server_config(**overrides) -> ServerConfig:
    overrides.setdefault("access_password", "")
    return ServerConfig(**overrides)


class _FakeKBDatabase:
    def __init__(self, docs_by_kb: dict[str, list[str]]) -> None:
        self.docs_by_kb = docs_by_kb

    async def get_kb(self, kb_id: str):
        if kb_id not in self.docs_by_kb:
            return None
        return {"id": kb_id, "name": kb_id}

    async def get_kb_doc_ids(self, kb_id: str) -> list[str]:
        return list(self.docs_by_kb[kb_id])


def _client(kb_db: _FakeKBDatabase):
    app.dependency_overrides = {
        deps.get_config: lambda: _server_config(access_password=""),
        deps.get_kb_database: lambda: kb_db,
        deps.get_retriever: lambda: object(),
        deps.get_glossary: lambda: {},
        deps.get_conversation_manager: lambda: SimpleNamespace(),
    }
    client = TestClient(app)
    return client


def test_query_empty_kb_short_circuits_agent(monkeypatch):
    dispatch = AsyncMock()
    monkeypatch.setattr(query_module, "dispatch_agent", dispatch)
    client = _client(_FakeKBDatabase({"kb-empty": []}))
    try:
        response = client.post(
            "/api/v1/query",
            json={"question": "cover?", "kbIds": ["kb-empty"]},
        )
    finally:
        app.dependency_overrides = {}

    assert response.status_code == 200
    payload = response.json()
    assert payload["confidence"] == "none"
    assert payload["sources"] == []
    assert "还没有可检索文档" in payload["answer"]
    dispatch.assert_not_awaited()


def test_query_invalid_kb_short_circuits_agent(monkeypatch):
    dispatch = AsyncMock()
    monkeypatch.setattr(query_module, "dispatch_agent", dispatch)
    client = _client(_FakeKBDatabase({}))
    try:
        response = client.post(
            "/api/v1/query",
            json={"question": "cover?", "kbIds": ["missing-kb"]},
        )
    finally:
        app.dependency_overrides = {}

    payload = response.json()
    assert payload["confidence"] == "none"
    assert payload["degraded"] is True
    assert "不存在或已被删除" in payload["answer"]
    dispatch.assert_not_awaited()


def test_query_valid_kb_passes_sources_filter(monkeypatch):
    async def _dispatch_agent(**kwargs):
        return SimpleNamespace(
            agent_reply="direct answer",
            bundle=SimpleNamespace(has_rag_evidence=False, tool_trace=[]),
            conv=SimpleNamespace(conversation_id="session-1"),
        )

    dispatch = AsyncMock(side_effect=_dispatch_agent)
    monkeypatch.setattr(query_module, "dispatch_agent", dispatch)
    client = _client(_FakeKBDatabase({"kb-1": ["EN_1992"]}))
    try:
        response = client.post(
            "/api/v1/query",
            json={"question": "cover?", "kbIds": ["kb-1"]},
        )
    finally:
        app.dependency_overrides = {}

    assert response.status_code == 200
    assert response.json()["answer"] == "direct answer"
    assert dispatch.await_args.kwargs["sources_filter"] == ["EN_1992", "EN 1992"]
