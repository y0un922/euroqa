"""API integration tests."""
import pytest
from fastapi.testclient import TestClient

from server.main import app


@pytest.fixture
def client():
    return TestClient(app)


class TestQueryEndpoint:
    def test_query_validation_missing_question(self, client):
        resp = client.post("/api/v1/query", json={})
        assert resp.status_code == 422

    def test_question_max_length(self, client):
        resp = client.post("/api/v1/query", json={"question": "x" * 501})
        assert resp.status_code == 422


class TestDocumentsEndpoint:
    def test_list_documents(self, client):
        resp = client.get("/api/v1/documents")
        assert resp.status_code == 200


class TestGlossaryEndpoint:
    def test_suggest(self, client):
        resp = client.get("/api/v1/suggest")
        assert resp.status_code == 200
        data = resp.json()
        assert "hot_questions" in data
        assert "domains" in data
        assert "query_types" in data

    def test_glossary_list(self, client):
        resp = client.get("/api/v1/glossary")
        assert resp.status_code == 200
