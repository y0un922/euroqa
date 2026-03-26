"""End-to-end smoke tests.

Requires running services (docker-compose up).
Run: pytest tests/test_e2e.py -v -m e2e
"""
import pytest
import httpx

E2E_BASE_URL = "http://localhost:8080"


def pytest_configure(config):
    config.addinivalue_line("markers", "e2e: end-to-end tests (need running services)")


@pytest.mark.e2e
class TestE2E:
    @pytest.fixture
    def client(self):
        return httpx.Client(base_url=E2E_BASE_URL, timeout=30.0)

    def test_health(self, client):
        resp = client.get("/api/v1/suggest")
        assert resp.status_code == 200

    def test_documents_list(self, client):
        resp = client.get("/api/v1/documents")
        assert resp.status_code == 200

    def test_query_basic(self, client):
        resp = client.post("/api/v1/query", json={
            "question": "设计使用年限怎么确定？",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["answer"]
        assert data["confidence"] in ["high", "medium", "low", "none"]
        assert data["conversation_id"]

    def test_query_with_domain(self, client):
        resp = client.post("/api/v1/query", json={
            "question": "荷载组合的基本原则",
            "domain": "EN 1990",
        })
        assert resp.status_code == 200

    def test_query_conversation(self, client):
        resp1 = client.post("/api/v1/query", json={"question": "设计使用年限怎么确定？"})
        cid = resp1.json()["conversation_id"]

        resp2 = client.post("/api/v1/query", json={
            "question": "那对应的荷载组合怎么取？",
            "conversation_id": cid,
        })
        assert resp2.status_code == 200
        assert resp2.json()["conversation_id"] == cid

    def test_glossary(self, client):
        resp = client.get("/api/v1/glossary")
        assert resp.status_code == 200
        assert len(resp.json()) > 0
