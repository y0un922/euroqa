"""Tests for debug pipeline API endpoints."""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from server.deps import get_config, get_retriever
from server.main import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    run_dir = tmp_path / "debug_runs" / "run-1"
    artifact_dir = run_dir / "artifacts" / "EN1990_2002"
    artifact_dir.mkdir(parents=True)
    (artifact_dir / "stage1.md").write_text("# Demo", encoding="utf-8")
    (artifact_dir / "tree.json").write_text(
        json.dumps({"title": "root", "children": []}),
        encoding="utf-8",
    )
    (run_dir / "manifest.json").write_text(
        json.dumps(
            {
                "run_id": "run-1",
                "status": "completed",
                "started_at": "2026-03-26T12:00:00+00:00",
                "updated_at": "2026-03-26T12:00:10+00:00",
                "current_stage": "stage_4",
                "stages": {"stage_4": {"status": "completed"}},
                "documents": {
                    "EN1990_2002": {
                        "title": "EN1990_2002",
                        "stages": {
                            "stage_1": {
                                "status": "completed",
                                "artifacts": [
                                    {
                                        "label": "Markdown",
                                        "path": "artifacts/EN1990_2002/stage1.md",
                                        "content_type": "text/markdown",
                                    }
                                ],
                            },
                            "stage_2": {
                                "status": "completed",
                                "artifacts": [
                                    {
                                        "label": "Tree",
                                        "path": "artifacts/EN1990_2002/tree.json",
                                        "content_type": "application/json",
                                    }
                                ],
                            },
                        },
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "events.jsonl").write_text("", encoding="utf-8")

    monkeypatch.setenv("DEBUG_PIPELINE_DIR", str(tmp_path / "debug_runs"))
    get_config.cache_clear()
    get_retriever.cache_clear()
    try:
        yield TestClient(app)
    finally:
        get_config.cache_clear()
        get_retriever.cache_clear()


class TestDebugPipelinePage:
    def test_debug_page_exists(self, client):
        resp = client.get("/debug/pipeline")
        assert resp.status_code == 200
        assert "Pipeline Debug" in resp.text

    def test_list_runs(self, client):
        resp = client.get("/api/debug/pipeline/runs")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["run_id"] == "run-1"

    def test_get_run_detail(self, client):
        resp = client.get("/api/debug/pipeline/runs/run-1")
        assert resp.status_code == 200
        assert resp.json()["documents"]["EN1990_2002"]["stages"]["stage_1"]["status"] == "completed"

    def test_get_artifact(self, client):
        resp = client.get("/api/debug/pipeline/runs/run-1/artifacts/artifacts/EN1990_2002/tree.json")
        assert resp.status_code == 200
        assert resp.json()["title"] == "root"
