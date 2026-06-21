"""Tests for index administration API."""

from __future__ import annotations

from fastapi.testclient import TestClient

from server import deps
from server.config import ServerConfig
from server.main import app


def _server_config(**overrides) -> ServerConfig:
    overrides.setdefault("access_password", "")
    return ServerConfig(**overrides)


def test_index_admin_overview_returns_service_payload(monkeypatch):
    async def _fake_overview():
        return {
            "milvus": {"exists": True, "entity_count": 3},
            "elasticsearch": {"exists": True, "document_count": 3},
            "sources": [{"source": "EN1990_2002", "elasticsearch_count": 3}],
        }

    monkeypatch.setattr(
        "server.services.index_admin.index_overview",
        _fake_overview,
    )
    app.dependency_overrides = {
        deps.get_config: lambda: _server_config(access_password=""),
    }
    try:
        client = TestClient(app)
        response = client.get("/api/v1/index-admin/overview")
    finally:
        app.dependency_overrides = {}

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 200
    assert body["data"]["milvus"]["entity_count"] == 3


def test_index_admin_inspect_passes_doc_id_and_sample_size(monkeypatch):
    calls = {}

    async def _fake_inspect(doc_id, *, sample_size):
        calls["doc_id"] = doc_id
        calls["sample_size"] = sample_size
        return {
            "doc_id": doc_id,
            "milvus_count": 1,
            "elasticsearch_count": 1,
            "samples": [],
        }

    monkeypatch.setattr(
        "server.services.index_admin.inspect_document_index",
        _fake_inspect,
    )
    app.dependency_overrides = {
        deps.get_config: lambda: _server_config(access_password=""),
    }
    try:
        client = TestClient(app)
        response = client.get("/api/v1/index-admin/documents/EN1990_2002?sample_size=2")
    finally:
        app.dependency_overrides = {}

    assert response.status_code == 200
    assert calls == {"doc_id": "EN1990_2002", "sample_size": 2}
    assert response.json()["data"]["doc_id"] == "EN1990_2002"


def test_index_admin_delete_returns_deleted_counts(monkeypatch):
    async def _fake_delete(doc_id):
        return {
            "doc_id": doc_id,
            "deleted": {"milvus": 2, "elasticsearch": 3},
        }

    monkeypatch.setattr(
        "server.services.index_admin.delete_document_index",
        _fake_delete,
    )
    app.dependency_overrides = {
        deps.get_config: lambda: _server_config(access_password=""),
    }
    try:
        client = TestClient(app)
        response = client.delete("/api/v1/index-admin/documents/EN1990_2002")
    finally:
        app.dependency_overrides = {}

    assert response.status_code == 200
    assert response.json()["message"] == "deleted"
    assert response.json()["data"]["deleted"] == {"milvus": 2, "elasticsearch": 3}


def test_index_admin_rebuild_threads_delete_first(monkeypatch):
    calls = {}

    async def _fake_rebuild(doc_id, *, delete_first):
        calls["doc_id"] = doc_id
        calls["delete_first"] = delete_first
        return {
            "doc_id": doc_id,
            "chunks": 4,
            "indexed": {"milvus": 4, "elasticsearch": 4},
        }

    monkeypatch.setattr(
        "server.services.index_admin.rebuild_document_index",
        _fake_rebuild,
    )
    app.dependency_overrides = {
        deps.get_config: lambda: _server_config(access_password=""),
    }
    try:
        client = TestClient(app)
        response = client.post(
            "/api/v1/index-admin/documents/EN1990_2002/rebuild",
            json={"delete_first": False},
        )
    finally:
        app.dependency_overrides = {}

    assert response.status_code == 200
    assert response.json()["message"] == "rebuilt"
    assert calls == {"doc_id": "EN1990_2002", "delete_first": False}
