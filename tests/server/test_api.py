"""API integration tests."""
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import fitz
import pytest
from fastapi.testclient import TestClient

from server import deps
from server.config import ServerConfig
from server.core.retrieval import RetrievalResult
from server.main import app
from server.models.schemas import QueryResponse, RetrievalContext


def _analysis_stub(
    question: str,
    *,
    answer_mode: str | None = None,
    intent_label: str | None = None,
    target_hint: object = None,
    requested_objects: list[str] | None = None,
    question_type: object = None,
    engineering_context: object = None,
    guide_hint: object = None,
):
    return SimpleNamespace(
        expanded_queries=[question],
        rewritten_query=question,
        original_question=question,
        filters={},
        matched_terms={},
        answer_mode=SimpleNamespace(value=answer_mode) if answer_mode else None,
        intent_label=intent_label,
        target_hint=target_hint,
        requested_objects=requested_objects or [],
        question_type=question_type,
        engineering_context=engineering_context,
        guide_hint=guide_hint,
        preferred_element_type=None,
    )


@pytest.fixture
def client():
    app.dependency_overrides = {}
    test_client = TestClient(app)
    yield test_client
    app.dependency_overrides = {}


class TestQueryEndpoint:
    def test_query_validation_missing_question(self, client):
        resp = client.post("/api/v1/query", json={})
        assert resp.status_code == 422

    def test_question_max_length(self, client):
        resp = client.post("/api/v1/query", json={"question": "x" * 501})
        assert resp.status_code == 422

    def test_stream_query_does_not_500_when_query_rewrite_llm_fails(self, client):
        class _FakeRetriever:
            async def retrieve(self, **kwargs):
                return RetrievalResult(chunks=[], parent_chunks=[], scores=[])

        class _FakeConversationManager:
            def get_or_create(self, conversation_id):
                return SimpleNamespace(
                    conversation_id=conversation_id or "conv-1",
                    history=[],
                )

            def add_turn(self, conversation_id, question, answer):
                return None

        async def _fake_stream(**kwargs):
            yield ("done", {"sources": [], "related_refs": [], "confidence": "low"})

        app.dependency_overrides[deps.get_retriever] = lambda: _FakeRetriever()
        app.dependency_overrides[deps.get_conversation_manager] = (
            lambda: _FakeConversationManager()
        )
        app.dependency_overrides[deps.get_glossary] = lambda: {}

        with (
            patch(
                "server.core.query_understanding._call_llm",
                AsyncMock(side_effect=RuntimeError("llm unavailable")),
            ),
            patch("server.api.v1.query.generate_answer_stream", _fake_stream),
        ):
            resp = client.post(
                "/api/v1/query/stream",
                json={"question": "巴黎的地铁的使用期限有多久？", "stream": True},
            )

        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")

    def test_query_endpoint_applies_request_scoped_llm_overrides(self, client):
        class _FakeRetriever:
            async def retrieve(self, **kwargs):
                return RetrievalResult(chunks=[], parent_chunks=[], scores=[])

        class _FakeConversationManager:
            def get_or_create(self, conversation_id):
                return SimpleNamespace(
                    conversation_id=conversation_id or "conv-1",
                    history=[],
                )

            def add_turn(self, conversation_id, question, answer):
                return None

        app.dependency_overrides[deps.get_retriever] = lambda: _FakeRetriever()
        app.dependency_overrides[deps.get_conversation_manager] = (
            lambda: _FakeConversationManager()
        )
        app.dependency_overrides[deps.get_glossary] = lambda: {}
        app.dependency_overrides[deps.get_config] = lambda: ServerConfig(
            llm_api_key="default-key",
            llm_base_url="https://default.example/v1",
            llm_model="default-model",
            llm_enable_thinking=False,
        )

        seen_configs: list[tuple[str, str, str, bool]] = []

        async def _fake_analyze_query(question, glossary, config):
            seen_configs.append(
                (
                    config.llm_api_key,
                    config.llm_base_url,
                    config.llm_model,
                    config.llm_enable_thinking,
                )
            )
            return _analysis_stub(question)

        async def _fake_generate_answer(**kwargs):
            config = kwargs["config"]
            seen_configs.append(
                (
                    config.llm_api_key,
                    config.llm_base_url,
                    config.llm_model,
                    config.llm_enable_thinking,
                )
            )
            return QueryResponse(
                answer="ok",
                sources=[],
                related_refs=[],
                confidence="low",
                degraded=False,
                conversation_id="conv-1",
            )

        with (
            patch("server.api.v1.query.analyze_query", _fake_analyze_query),
            patch("server.api.v1.query.generate_answer", _fake_generate_answer),
        ):
            resp = client.post(
                "/api/v1/query",
                json={
                    "question": "什么是设计使用年限？",
                    "llm": {
                        "api_key": "override-key",
                        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
                        "model": "qwen3.5-plus",
                        "enable_thinking": True,
                    },
                },
            )

        assert resp.status_code == 200
        assert seen_configs == [
            (
                "override-key",
                "https://dashscope.aliyuncs.com/compatible-mode/v1",
                "qwen3.5-plus",
                True,
            ),
            (
                "override-key",
                "https://dashscope.aliyuncs.com/compatible-mode/v1",
                "qwen3.5-plus",
                True,
            ),
        ]

    def test_query_endpoint_does_not_forward_or_store_conversation_history(self, client):
        class _FakeRetriever:
            async def retrieve(self, **kwargs):
                return RetrievalResult(chunks=[], parent_chunks=[], scores=[])

        class _FakeConversationManager:
            def __init__(self):
                self.add_turn_calls: list[tuple[str, str, str]] = []

            def get_or_create(self, conversation_id):
                return SimpleNamespace(
                    conversation_id=conversation_id or "conv-1",
                    history=[{"question": "上一轮问题", "answer": "上一轮回答"}],
                )

            def add_turn(self, conversation_id, question, answer):
                self.add_turn_calls.append((conversation_id, question, answer))

        conversation_manager = _FakeConversationManager()
        app.dependency_overrides[deps.get_retriever] = lambda: _FakeRetriever()
        app.dependency_overrides[deps.get_conversation_manager] = (
            lambda: conversation_manager
        )
        app.dependency_overrides[deps.get_glossary] = lambda: {}

        seen_histories: list[list[dict[str, str]]] = []

        async def _fake_analyze_query(question, glossary, config):
            return _analysis_stub(question)

        async def _fake_generate_answer(**kwargs):
            seen_histories.append(kwargs["conversation_history"])
            return QueryResponse(
                answer="ok",
                sources=[],
                related_refs=[],
                confidence="low",
                degraded=False,
                conversation_id="conv-1",
            )

        with (
            patch("server.api.v1.query.analyze_query", _fake_analyze_query),
            patch("server.api.v1.query.generate_answer", _fake_generate_answer),
        ):
            resp = client.post(
                "/api/v1/query",
                json={"question": "设计使用年限是多少？", "conversation_id": "conv-1"},
            )

        assert resp.status_code == 200
        assert seen_histories == [[]]
        assert conversation_manager.add_turn_calls == []

    def test_stream_query_does_not_forward_or_store_conversation_history(self, client):
        class _FakeRetriever:
            async def retrieve(self, **kwargs):
                return RetrievalResult(chunks=[], parent_chunks=[], scores=[])

        class _FakeConversationManager:
            def __init__(self):
                self.add_turn_calls: list[tuple[str, str, str]] = []

            def get_or_create(self, conversation_id):
                return SimpleNamespace(
                    conversation_id=conversation_id or "conv-1",
                    history=[{"question": "上一轮问题", "answer": "上一轮回答"}],
                )

            def add_turn(self, conversation_id, question, answer):
                self.add_turn_calls.append((conversation_id, question, answer))

        conversation_manager = _FakeConversationManager()
        app.dependency_overrides[deps.get_retriever] = lambda: _FakeRetriever()
        app.dependency_overrides[deps.get_conversation_manager] = (
            lambda: conversation_manager
        )
        app.dependency_overrides[deps.get_glossary] = lambda: {}

        seen_histories: list[list[dict[str, str]]] = []

        async def _fake_analyze_query(question, glossary, config):
            return _analysis_stub(question)

        async def _fake_generate_answer_stream(**kwargs):
            seen_histories.append(kwargs["conversation_history"])
            yield ("done", {"sources": [], "related_refs": [], "confidence": "low"})

        with (
            patch("server.api.v1.query.analyze_query", _fake_analyze_query),
            patch(
                "server.api.v1.query.generate_answer_stream",
                _fake_generate_answer_stream,
            ),
        ):
            resp = client.post(
                "/api/v1/query/stream",
                json={
                    "question": "设计使用年限是多少？",
                    "conversation_id": "conv-1",
                    "stream": True,
                },
            )

        assert resp.status_code == 200
        assert seen_histories == [[]]
        assert conversation_manager.add_turn_calls == []

    def test_query_endpoint_passes_original_question_for_dual_retrieval(self, client):
        class _FakeConversationManager:
            def get_or_create(self, conversation_id):
                return SimpleNamespace(
                    conversation_id=conversation_id or "conv-1",
                    history=[],
                )

            def add_turn(self, conversation_id, question, answer):
                return None

        app.dependency_overrides[deps.get_glossary] = lambda: {}
        app.dependency_overrides[deps.get_conversation_manager] = (
            lambda: _FakeConversationManager()
        )

        seen_retrieve_calls: list[dict[str, object]] = []

        class _FakeRetriever:
            async def retrieve(self, **kwargs):
                seen_retrieve_calls.append(kwargs)
                return RetrievalResult(chunks=[], parent_chunks=[], scores=[])

        async def _fake_analyze_query(question, glossary, config):
            return _analysis_stub(
                question,
                answer_mode="exact",
                intent_label="assumption",
                target_hint=SimpleNamespace(
                    document="EN 1992-1-1",
                    clause="6.1",
                    object="basic assumptions",
                ),
                requested_objects=["6.1"],
            )

        async def _fake_generate_answer(**kwargs):
            return QueryResponse(
                answer="ok",
                sources=[],
                related_refs=[],
                confidence="low",
                degraded=False,
                conversation_id="conv-1",
            )

        app.dependency_overrides[deps.get_retriever] = lambda: _FakeRetriever()

        with (
            patch("server.api.v1.query.analyze_query", _fake_analyze_query),
            patch("server.api.v1.query.generate_answer", _fake_generate_answer),
        ):
            resp = client.post(
                "/api/v1/query",
                json={"question": "地铁的设计使用年限是多久？"},
            )

        assert resp.status_code == 200
        assert seen_retrieve_calls == [
            {
                "queries": ["地铁的设计使用年限是多久？"],
                "original_query": "地铁的设计使用年限是多久？",
                "filters": {},
                "answer_mode": "exact",
                "intent_label": "assumption",
                "question_type": None,
                "guide_hint": None,
                "target_hint": SimpleNamespace(
                    document="EN 1992-1-1",
                    clause="6.1",
                    object="basic assumptions",
                ),
                "requested_objects": ["6.1"],
                "preferred_element_type": None,
            }
        ]

    def test_query_endpoint_returns_retrieval_context(self, client):
        class _FakeConversationManager:
            def get_or_create(self, conversation_id):
                return SimpleNamespace(
                    conversation_id=conversation_id or "conv-1",
                    history=[],
                )

            def add_turn(self, conversation_id, question, answer):
                return None

        app.dependency_overrides[deps.get_glossary] = lambda: {}
        app.dependency_overrides[deps.get_conversation_manager] = (
            lambda: _FakeConversationManager()
        )

        class _FakeRetriever:
            async def retrieve(self, **kwargs):
                return RetrievalResult(
                    chunks=[],
                    parent_chunks=[],
                    scores=[0.91],
                    groundedness="grounded",
                )

        async def _fake_analyze_query(question, glossary, config):
            return _analysis_stub(
                question,
                answer_mode="exact",
                intent_label="assumption",
            )

        seen_scores: list[list[float] | None] = []

        async def _fake_generate_answer(**kwargs):
            seen_scores.append(kwargs.get("scores"))
            return QueryResponse(
                answer="ok",
                sources=[],
                related_refs=[],
                confidence="low",
                degraded=False,
                conversation_id="conv-1",
                answer_mode=None,
                groundedness=None,
                retrieval_context=RetrievalContext(
                    chunks=[
                        {
                            "chunk_id": "chunk_023",
                            "document_id": "EN1990_2002",
                            "file": "EN 1990:2002",
                            "title": "Eurocode - Basis of structural design",
                            "section": "Section 2 Requirements > 2.3 Design working life",
                            "page": "28",
                            "clause": "2.3(1)",
                            "content": "The design working life should be specified.",
                            "score": 0.91,
                        }
                    ],
                    parent_chunks=[],
                    guide_chunks=[
                        {
                            "chunk_id": "guide-1",
                            "document_id": "Bridge_Designers_Guide2024",
                            "file": "Bridge Designers Guide 2024",
                            "title": "Designers Guide to Eurocode load combinations",
                            "section": "Example 2.1",
                            "page": "28",
                            "clause": "Example 2.1",
                            "content": "Guide example for load combinations.",
                        }
                    ],
                    guide_example_chunks=[
                        {
                            "chunk_id": "guide-example-1",
                            "document_id": "Bridge_Designers_Guide2024",
                            "file": "Bridge Designers Guide 2024",
                            "title": "Designers Guide to Eurocode load combinations",
                            "section": "Worked example 2.1",
                            "page": "28",
                            "clause": "Worked example 2.1",
                            "content": "Worked example for design value calculation.",
                        }
                    ],
                ),
            )

        app.dependency_overrides[deps.get_retriever] = lambda: _FakeRetriever()

        with (
            patch("server.api.v1.query.analyze_query", _fake_analyze_query),
            patch("server.api.v1.query.generate_answer", _fake_generate_answer),
        ):
            resp = client.post(
                "/api/v1/query",
                json={"question": "地铁的设计使用年限是多久？"},
            )

        assert resp.status_code == 200
        assert seen_scores == [[0.91]]
        assert resp.json()["retrieval_context"]["chunks"][0]["score"] == 0.91
        assert (
            resp.json()["retrieval_context"]["guide_chunks"][0]["document_id"]
            == "Bridge_Designers_Guide2024"
        )
        assert resp.json()["retrieval_context"]["guide_example_chunks"][0]["chunk_id"] == "guide-example-1"
        assert resp.json()["answer_mode"] == "exact"
        assert resp.json()["groundedness"] == "grounded"

    def test_query_stream_endpoint_ignores_blank_llm_override_values(self, client):
        class _FakeRetriever:
            async def retrieve(self, **kwargs):
                return RetrievalResult(chunks=[], parent_chunks=[], scores=[])

        class _FakeConversationManager:
            def get_or_create(self, conversation_id):
                return SimpleNamespace(
                    conversation_id=conversation_id or "conv-1",
                    history=[],
                )

            def add_turn(self, conversation_id, question, answer):
                return None

        app.dependency_overrides[deps.get_retriever] = lambda: _FakeRetriever()
        app.dependency_overrides[deps.get_conversation_manager] = (
            lambda: _FakeConversationManager()
        )
        app.dependency_overrides[deps.get_glossary] = lambda: {}
        app.dependency_overrides[deps.get_config] = lambda: ServerConfig(
            llm_api_key="default-key",
            llm_base_url="https://default.example/v1",
            llm_model="default-model",
            llm_enable_thinking=True,
        )

        seen_configs: list[tuple[str, str, str, bool]] = []

        async def _fake_analyze_query(question, glossary, config):
            seen_configs.append(
                (
                    config.llm_api_key,
                    config.llm_base_url,
                    config.llm_model,
                    config.llm_enable_thinking,
                )
            )
            return _analysis_stub(question)

        async def _fake_generate_answer_stream(**kwargs):
            config = kwargs["config"]
            seen_configs.append(
                (
                    config.llm_api_key,
                    config.llm_base_url,
                    config.llm_model,
                    config.llm_enable_thinking,
                )
            )
            yield ("done", {"sources": [], "related_refs": [], "confidence": "low"})

        with (
            patch("server.api.v1.query.analyze_query", _fake_analyze_query),
            patch(
                "server.api.v1.query.generate_answer_stream",
                _fake_generate_answer_stream,
            ),
        ):
            resp = client.post(
                "/api/v1/query/stream",
                json={
                    "question": "什么是设计使用年限？",
                    "stream": True,
                    "llm": {
                        "api_key": "",
                        "base_url": "   ",
                        "model": "",
                        "enable_thinking": False,
                    },
                },
            )

        assert resp.status_code == 200
        assert seen_configs == [
            ("default-key", "https://default.example/v1", "default-model", False),
            ("default-key", "https://default.example/v1", "default-model", False),
        ]

    def test_query_stream_endpoint_done_event_includes_retrieval_context(self, client):
        class _FakeRetriever:
            async def retrieve(self, **kwargs):
                return RetrievalResult(chunks=[], parent_chunks=[], scores=[0.91], groundedness="grounded")

        class _FakeConversationManager:
            def get_or_create(self, conversation_id):
                return SimpleNamespace(
                    conversation_id=conversation_id or "conv-1",
                    history=[],
                )

            def add_turn(self, conversation_id, question, answer):
                return None

        async def _fake_analyze_query(question, glossary, config):
            return _analysis_stub(
                question,
                answer_mode="exact",
                intent_label="assumption",
            )

        async def _fake_generate_answer_stream(**kwargs):
            yield (
                "done",
                {
                    "sources": [],
                    "related_refs": [],
                    "confidence": "low",
                    "answer_mode": "exact",
                    "groundedness": "grounded",
                    "retrieval_context": {
                        "chunks": [
                            {
                                "chunk_id": "chunk_023",
                                "document_id": "EN1990_2002",
                                "file": "EN 1990:2002",
                                "title": "Eurocode - Basis of structural design",
                                "section": "Section 2 Requirements > 2.3 Design working life",
                                "page": "28",
                                "clause": "2.3(1)",
                                "content": "The design working life should be specified.",
                                "score": 0.91,
                            }
                        ],
                        "parent_chunks": [],
                        "guide_chunks": [
                            {
                                "chunk_id": "guide-1",
                                "document_id": "Bridge_Designers_Guide2024",
                                "file": "Bridge Designers Guide 2024",
                                "title": "Designers Guide to Eurocode load combinations",
                                "section": "Example 2.1",
                                "page": "28",
                                "clause": "Example 2.1",
                                "content": "Guide example for load combinations.",
                            }
                        ],
                        "guide_example_chunks": [
                            {
                                "chunk_id": "guide-example-1",
                                "document_id": "Bridge_Designers_Guide2024",
                                "file": "Bridge Designers Guide 2024",
                                "title": "Designers Guide to Eurocode load combinations",
                                "section": "Worked example 2.1",
                                "page": "28",
                                "clause": "Worked example 2.1",
                                "content": "Worked example for design value calculation.",
                            }
                        ],
                    },
                },
            )

        app.dependency_overrides[deps.get_retriever] = lambda: _FakeRetriever()
        app.dependency_overrides[deps.get_conversation_manager] = (
            lambda: _FakeConversationManager()
        )
        app.dependency_overrides[deps.get_glossary] = lambda: {}

        with (
            patch("server.api.v1.query.analyze_query", _fake_analyze_query),
            patch(
                "server.api.v1.query.generate_answer_stream",
                _fake_generate_answer_stream,
            ),
        ):
            resp = client.post(
                "/api/v1/query/stream",
                json={"question": "地铁的设计使用年限是多久？", "stream": True},
            )

        assert resp.status_code == 200
        assert '"retrieval_context"' in resp.text
        assert '"score": 0.91' in resp.text
        assert '"guide_chunks"' in resp.text
        assert '"guide_example_chunks"' in resp.text
        assert '"answer_mode": "exact"' in resp.text
        assert '"groundedness": "grounded"' in resp.text

    def test_query_stream_emits_user_friendly_progress_events(self, client):
        class _FakeRetriever:
            async def retrieve(self, **kwargs):
                return RetrievalResult(
                    chunks=[],
                    parent_chunks=[],
                    scores=[],
                    resolved_refs=["Table 3.1"],
                    guide_chunks=[],
                    guide_example_chunks=[],
                )

        class _FakeConversationManager:
            def get_or_create(self, conversation_id):
                return SimpleNamespace(conversation_id=conversation_id or "conv-1", history=[])

            def add_turn(self, conversation_id, question, answer):
                return None

        async def _fake_analyze_query(question, glossary, config):
            return _analysis_stub(
                question,
                answer_mode="open",
                intent_label="limit",
                question_type=SimpleNamespace(value="parameter"),
                target_hint=SimpleNamespace(document="EN 1990", clause="2.3", object=None),
            )

        async def _fake_generate_answer_stream(**kwargs):
            yield ("done", {"sources": [], "related_refs": [], "confidence": "low"})

        app.dependency_overrides[deps.get_retriever] = lambda: _FakeRetriever()
        app.dependency_overrides[deps.get_conversation_manager] = lambda: _FakeConversationManager()
        app.dependency_overrides[deps.get_glossary] = lambda: {}

        with (
            patch("server.api.v1.query.analyze_query", _fake_analyze_query),
            patch(
                "server.api.v1.query.generate_answer_stream",
                _fake_generate_answer_stream,
            ),
        ):
            resp = client.post(
                "/api/v1/query/stream",
                json={"question": "设计使用年限怎么确定？", "stream": True},
            )

        assert resp.status_code == 200
        assert "event: progress" in resp.text
        assert '"title": "理解问题"' in resp.text
        assert "识别为参数/限值类问题" in resp.text
        assert '"title": "补齐引用"' in resp.text
        assert "已补齐 Table 3.1" in resp.text
        assert '"title": "生成回答"' in resp.text

    def test_query_endpoint_threads_question_type_to_retriever(self, client):
        seen_retrieval_kwargs = {}

        class _FakeRetriever:
            async def retrieve(self, **kwargs):
                seen_retrieval_kwargs.update(kwargs)
                return RetrievalResult(chunks=[], parent_chunks=[], scores=[])

        class _FakeConversationManager:
            def get_or_create(self, conversation_id):
                return SimpleNamespace(conversation_id=conversation_id or "conv-1", history=[])

            def add_turn(self, conversation_id, question, answer):
                return None

        async def _fake_generate_answer(**kwargs):
            return QueryResponse(
                answer="ok",
                sources=[],
                related_refs=[],
                confidence="low",
                degraded=False,
                conversation_id="conv-1",
            )

        app.dependency_overrides[deps.get_retriever] = lambda: _FakeRetriever()
        app.dependency_overrides[deps.get_conversation_manager] = lambda: _FakeConversationManager()
        app.dependency_overrides[deps.get_glossary] = lambda: {}

        async def _fake_analyze_query(question, glossary, config):
            return _analysis_stub(
                question,
                answer_mode="open",
                intent_label="calculation",
                question_type=SimpleNamespace(value="calculation"),
                guide_hint=SimpleNamespace(
                    need_example=True,
                    example_query="design value worked example",
                    example_kind="worked_example",
                ),
            )

        with (
            patch("server.api.v1.query.analyze_query", _fake_analyze_query),
            patch("server.api.v1.query.generate_answer", _fake_generate_answer),
        ):
            resp = client.post("/api/v1/query", json={"question": "怎么计算组合值？"})

        assert resp.status_code == 200
        assert seen_retrieval_kwargs["question_type"] == "calculation"
        assert seen_retrieval_kwargs["guide_hint"].need_example is True

    def test_query_endpoint_returns_answer_mode_and_groundedness(self, client):
        class _FakeRetriever:
            async def retrieve(self, **kwargs):
                return RetrievalResult(
                    chunks=[],
                    parent_chunks=[],
                    scores=[],
                    groundedness="exact_not_grounded",
                )

        class _FakeConversationManager:
            def get_or_create(self, conversation_id):
                return SimpleNamespace(conversation_id=conversation_id or "conv-1", history=[])

            def add_turn(self, conversation_id, question, answer):
                return None

        async def _fake_generate_answer(**kwargs):
            return QueryResponse(
                answer="ok",
                sources=[],
                related_refs=[],
                confidence="low",
                degraded=False,
                conversation_id="conv-1",
            )

        app.dependency_overrides[deps.get_retriever] = lambda: _FakeRetriever()
        app.dependency_overrides[deps.get_conversation_manager] = lambda: _FakeConversationManager()
        app.dependency_overrides[deps.get_glossary] = lambda: {}

        async def _fake_analyze_query(question, glossary, config):
            return _analysis_stub(question, answer_mode="exact", intent_label="assumption")

        with (
            patch("server.api.v1.query.analyze_query", _fake_analyze_query),
            patch("server.api.v1.query.generate_answer", _fake_generate_answer),
        ):
            resp = client.post("/api/v1/query", json={"question": "欧标的截面计算的基本假设前提是什么"})

        assert resp.status_code == 200
        assert resp.json()["answer_mode"] == "exact"
        assert resp.json()["groundedness"] == "exact_not_grounded"

    def test_query_stream_done_event_includes_answer_mode_and_groundedness(self, client):
        class _FakeRetriever:
            async def retrieve(self, **kwargs):
                return RetrievalResult(chunks=[], parent_chunks=[], scores=[], groundedness="grounded")

        class _FakeConversationManager:
            def get_or_create(self, conversation_id):
                return SimpleNamespace(conversation_id=conversation_id or "conv-1", history=[])

            def add_turn(self, conversation_id, question, answer):
                return None

        async def _fake_generate_answer_stream(**kwargs):
            yield ("done", {"sources": [], "related_refs": [], "confidence": "low"})

        app.dependency_overrides[deps.get_retriever] = lambda: _FakeRetriever()
        app.dependency_overrides[deps.get_conversation_manager] = lambda: _FakeConversationManager()
        app.dependency_overrides[deps.get_glossary] = lambda: {}

        async def _fake_analyze_query(question, glossary, config):
            return _analysis_stub(question, answer_mode="exact", intent_label="assumption")

        with (
            patch("server.api.v1.query.analyze_query", _fake_analyze_query),
            patch("server.api.v1.query.generate_answer_stream", _fake_generate_answer_stream),
        ):
            resp = client.post("/api/v1/query/stream", json={"question": "欧标的截面计算的基本假设前提是什么", "stream": True})

        assert resp.status_code == 200
        done_event = next(
            segment for segment in resp.text.split("\r\n\r\n") if "event: done" in segment
        )
        done_payload = json.loads(done_event.split("data: ", 1)[1].strip())
        assert done_payload["answer_mode"] == "exact"
        assert done_payload["groundedness"] == "grounded"

    def test_query_endpoint_threads_intent_label_to_generate_answer(self, client):
        class _FakeRetriever:
            async def retrieve(self, **kwargs):
                return RetrievalResult(chunks=[], parent_chunks=[], scores=[], groundedness="grounded")

        class _FakeConversationManager:
            def get_or_create(self, conversation_id):
                return SimpleNamespace(conversation_id=conversation_id or "conv-1", history=[])

            def add_turn(self, conversation_id, question, answer):
                return None

        seen_kwargs = {}

        async def _fake_generate_answer(**kwargs):
            seen_kwargs.update(kwargs)
            return QueryResponse(
                answer="ok",
                sources=[],
                related_refs=[],
                confidence="low",
                degraded=False,
                conversation_id="conv-1",
            )

        app.dependency_overrides[deps.get_retriever] = lambda: _FakeRetriever()
        app.dependency_overrides[deps.get_conversation_manager] = lambda: _FakeConversationManager()
        app.dependency_overrides[deps.get_glossary] = lambda: {}

        async def _fake_analyze_query(question, glossary, config):
            return _analysis_stub(question, answer_mode="exact", intent_label="assumption")

        with (
            patch("server.api.v1.query.analyze_query", _fake_analyze_query),
            patch("server.api.v1.query.generate_answer", _fake_generate_answer),
        ):
            resp = client.post("/api/v1/query", json={"question": "欧标的截面计算的基本假设前提是什么"})

        assert resp.status_code == 200
        assert seen_kwargs["intent_label"] == "assumption"

    def test_query_stream_threads_intent_label_to_generate_answer_stream(self, client):
        class _FakeRetriever:
            async def retrieve(self, **kwargs):
                return RetrievalResult(chunks=[], parent_chunks=[], scores=[], groundedness="grounded")

        class _FakeConversationManager:
            def get_or_create(self, conversation_id):
                return SimpleNamespace(conversation_id=conversation_id or "conv-1", history=[])

            def add_turn(self, conversation_id, question, answer):
                return None

        seen_kwargs = {}

        async def _fake_generate_answer_stream(**kwargs):
            seen_kwargs.update(kwargs)
            yield ("done", {"sources": [], "related_refs": [], "confidence": "low"})

        app.dependency_overrides[deps.get_retriever] = lambda: _FakeRetriever()
        app.dependency_overrides[deps.get_conversation_manager] = lambda: _FakeConversationManager()
        app.dependency_overrides[deps.get_glossary] = lambda: {}

        async def _fake_analyze_query(question, glossary, config):
            return _analysis_stub(question, answer_mode="exact", intent_label="assumption")

        with (
            patch("server.api.v1.query.analyze_query", _fake_analyze_query),
            patch("server.api.v1.query.generate_answer_stream", _fake_generate_answer_stream),
        ):
            resp = client.post("/api/v1/query/stream", json={"question": "欧标的截面计算的基本假设前提是什么", "stream": True})

        assert resp.status_code == 200
        assert seen_kwargs["intent_label"] == "assumption"


class TestLlmSettingsEndpoint:
    def test_get_llm_settings_masks_api_key(self, client):
        app.dependency_overrides[deps.get_config] = lambda: ServerConfig(
            llm_api_key="secret-key",
            llm_base_url="https://api.deepseek.com/v1",
            llm_model="deepseek-chat",
            llm_enable_thinking=True,
        )

        resp = client.get("/api/v1/settings/llm")

        assert resp.status_code == 200
        assert resp.json() == {
            "base_url": "https://api.deepseek.com/v1",
            "model": "deepseek-chat",
            "enable_thinking": True,
            "api_key_configured": True,
        }


class TestDocumentsEndpoint:
    def test_list_documents(self, client):
        resp = client.get("/api/v1/documents")
        assert resp.status_code == 200

    def test_list_documents_does_not_mark_parsed_but_unindexed_doc_as_ready(
        self, client, tmp_path: Path
    ):
        pdf_dir = tmp_path / "pdfs"
        parsed_dir = tmp_path / "parsed"
        pdf_dir.mkdir()
        (parsed_dir / "DG_EN1990").mkdir(parents=True)

        pdf_path = pdf_dir / "DG_EN1990.pdf"
        doc = fitz.open()
        doc.new_page()
        doc.save(pdf_path)
        doc.close()

        # Only parsed markdown exists; no completed indexing marker should mean not ready.
        (parsed_dir / "DG_EN1990" / "DG_EN1990.md").write_text("# DG", encoding="utf-8")

        app.dependency_overrides[deps.get_config] = lambda: ServerConfig(
            pdf_dir=str(pdf_dir),
            parsed_dir=str(parsed_dir),
            es_url="http://127.0.0.1:1",
        )

        resp = client.get("/api/v1/documents")

        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 1
        assert body[0]["id"] == "DG_EN1990"
        assert body[0]["status"] != "ready"

    def test_list_documents_marks_doc_ready_when_index_marker_exists(
        self, client, tmp_path: Path
    ):
        pdf_dir = tmp_path / "pdfs"
        parsed_dir = tmp_path / "parsed"
        parsed_doc_dir = parsed_dir / "DG_EN1990"
        pdf_dir.mkdir()
        parsed_doc_dir.mkdir(parents=True)

        pdf_path = pdf_dir / "DG_EN1990.pdf"
        doc = fitz.open()
        doc.new_page()
        doc.save(pdf_path)
        doc.close()

        (parsed_doc_dir / "DG_EN1990.md").write_text("# DG", encoding="utf-8")
        (parsed_doc_dir / ".indexed").write_text("{}", encoding="utf-8")

        app.dependency_overrides[deps.get_config] = lambda: ServerConfig(
            pdf_dir=str(pdf_dir),
            parsed_dir=str(parsed_dir),
            es_url="http://127.0.0.1:1",
        )

        resp = client.get("/api/v1/documents")

        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 1
        assert body[0]["id"] == "DG_EN1990"
        assert body[0]["status"] == "ready"

    def test_list_documents_marks_legacy_indexed_doc_ready_without_marker(
        self, client, tmp_path: Path
    ):
        pdf_dir = tmp_path / "pdfs"
        parsed_dir = tmp_path / "parsed"
        parsed_doc_dir = parsed_dir / "DG_EN1990"
        pdf_dir.mkdir()
        parsed_doc_dir.mkdir(parents=True)

        pdf_path = pdf_dir / "DG_EN1990.pdf"
        doc = fitz.open()
        doc.new_page()
        doc.save(pdf_path)
        doc.close()

        (parsed_doc_dir / "DG_EN1990.md").write_text("# DG", encoding="utf-8")

        app.dependency_overrides[deps.get_config] = lambda: ServerConfig(
            pdf_dir=str(pdf_dir),
            parsed_dir=str(parsed_dir),
            es_url="http://127.0.0.1:1",
        )

        checked_sources: list[str] = []

        async def fake_document_has_indexed_chunks(source_name, *_args):
            checked_sources.append(source_name)
            return source_name == "DG EN1990"

        with patch(
            "server.api.v1.documents._document_has_indexed_chunks",
            fake_document_has_indexed_chunks,
        ):
            resp = client.get("/api/v1/documents")

        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 1
        assert body[0]["id"] == "DG_EN1990"
        assert body[0]["status"] == "ready"
        assert checked_sources == ["DG_EN1990", "DG EN1990"]

    def test_get_document_file_returns_pdf_bytes(self, client, tmp_path: Path):
        pdf_path = tmp_path / "EN1990_2002.pdf"
        doc = fitz.open()
        doc.new_page()
        doc.save(pdf_path)
        doc.close()

        app.dependency_overrides[deps.get_config] = lambda: ServerConfig(pdf_dir=str(tmp_path))

        resp = client.get("/api/v1/documents/EN1990_2002/file")

        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/pdf"
        assert resp.content.startswith(b"%PDF")

    def test_get_document_file_preserves_repeated_underscore_doc_id(
        self, client, tmp_path: Path
    ):
        pdf_path = tmp_path / "DG_EN1992-1-1__-1-2.pdf"
        doc = fitz.open()
        doc.new_page()
        doc.save(pdf_path)
        doc.close()

        app.dependency_overrides[deps.get_config] = lambda: ServerConfig(pdf_dir=str(tmp_path))

        resp = client.get("/api/v1/documents/DG_EN1992-1-1__-1-2/file")

        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/pdf"
        assert resp.content.startswith(b"%PDF")

    def test_get_document_file_returns_404_when_missing(self, client, tmp_path: Path):
        app.dependency_overrides[deps.get_config] = lambda: ServerConfig(pdf_dir=str(tmp_path))

        resp = client.get("/api/v1/documents/EN1990_2002/file")

        assert resp.status_code == 404

    def test_get_document_file_returns_404_when_path_is_directory(
        self, client, tmp_path: Path
    ):
        (tmp_path / "EN1990_2002.pdf").mkdir()
        app.dependency_overrides[deps.get_config] = lambda: ServerConfig(pdf_dir=str(tmp_path))

        resp = client.get("/api/v1/documents/EN1990_2002/file")

        assert resp.status_code == 404

    def test_delete_document_removes_current_and_legacy_index_sources(
        self, client, tmp_path: Path
    ):
        doc_id = "DG_EN1992-1-1__-1-2"
        pdf_dir = tmp_path / "pdfs"
        parsed_dir = tmp_path / "parsed"
        pdf_dir.mkdir()
        (parsed_dir / doc_id).mkdir(parents=True)
        (pdf_dir / f"{doc_id}.pdf").write_bytes(b"%PDF-1.4 demo")
        app.dependency_overrides[deps.get_config] = lambda: ServerConfig(
            pdf_dir=str(pdf_dir),
            parsed_dir=str(parsed_dir),
        )

        deleted_sources: list[str] = []

        async def fake_delete_document_chunks(source_name, _config):
            deleted_sources.append(source_name)
            return {"milvus": 1, "elasticsearch": 2}

        with (
            patch("pipeline.index.delete_document_chunks", fake_delete_document_chunks),
            patch(
                "server.api.v1.documents.invalidate_retriever_cache",
                AsyncMock(),
            ),
        ):
            resp = client.delete(f"/api/v1/documents/{doc_id}")

        assert resp.status_code == 200
        assert resp.json()["deleted_milvus"] == 2
        assert resp.json()["deleted_elasticsearch"] == 4
        assert deleted_sources == [doc_id, doc_id.replace("_", " ")]
        assert not (pdf_dir / f"{doc_id}.pdf").exists()
        assert not (parsed_dir / doc_id).exists()


class TestSourcesEndpoint:
    def test_translate_source_returns_translation(self, client):
        translated_source = SimpleNamespace(translation="设计使用年限应予规定。")
        payload = {
            "document_id": "EN1990_2002",
            "file": "EN 1990:2002",
            "title": "Eurocode - Basis of structural design",
            "section": "Section 2 Requirements > 2.3 Design working life",
            "page": "28",
            "clause": "2.3(1)",
            "original_text": "The design working life should be specified.",
            "locator_text": "2.3 Design working life (1) The design working life should be specified.",
        }

        with patch(
            "server.api.v1.sources._fill_missing_source_translations",
            AsyncMock(return_value=[translated_source]),
        ) as mock_translate:
            resp = client.post("/api/v1/sources/translate", json=payload)

        assert resp.status_code == 200
        assert resp.json() == {"translation": "设计使用年限应予规定。"}
        [sent_sources, sent_config] = mock_translate.await_args.args
        assert sent_config is not None
        assert len(sent_sources) == 1
        assert sent_sources[0].file == payload["file"]
        assert sent_sources[0].document_id == payload["document_id"]
        assert sent_sources[0].title == payload["title"]
        assert sent_sources[0].section == payload["section"]
        assert sent_sources[0].page == payload["page"]
        assert sent_sources[0].clause == payload["clause"]
        assert sent_sources[0].original_text == payload["original_text"]
        assert sent_sources[0].locator_text == payload["locator_text"]
        assert sent_sources[0].translation == ""

    def test_translate_source_request_does_not_accept_translation_field(self, client):
        payload = {
            "document_id": "EN1990_2002",
            "file": "EN 1990:2002",
            "title": "Eurocode - Basis of structural design",
            "section": "Section 2 Requirements > 2.3 Design working life",
            "page": "28",
            "clause": "2.3(1)",
            "original_text": "The design working life should be specified.",
            "locator_text": "2.3 Design working life (1) The design working life should be specified.",
            "translation": "should be rejected",
        }

        resp = client.post("/api/v1/sources/translate", json=payload)

        assert resp.status_code == 422

    def test_translate_source_returns_http_error_when_helper_returns_empty_list(
        self, client
    ):
        payload = {
            "document_id": "EN1990_2002",
            "file": "EN 1990:2002",
            "title": "Eurocode - Basis of structural design",
            "section": "Section 2 Requirements > 2.3 Design working life",
            "page": "28",
            "clause": "2.3(1)",
            "original_text": "The design working life should be specified.",
            "locator_text": "2.3 Design working life (1) The design working life should be specified.",
        }

        with patch(
            "server.api.v1.sources._fill_missing_source_translations",
            AsyncMock(return_value=[]),
        ):
            resp = client.post("/api/v1/sources/translate", json=payload)

        assert resp.status_code == 502

    def test_translate_source_returns_http_error_when_translation_empty(
        self, client
    ):
        payload = {
            "document_id": "EN1990_2002",
            "file": "EN 1990:2002",
            "title": "Eurocode - Basis of structural design",
            "section": "Section 2 Requirements > 2.3 Design working life",
            "page": "28",
            "clause": "2.3(1)",
            "original_text": "The design working life should be specified.",
            "locator_text": "2.3 Design working life (1) The design working life should be specified.",
        }

        with patch(
            "server.api.v1.sources._fill_missing_source_translations",
            AsyncMock(return_value=[SimpleNamespace(translation="")]),
        ):
            resp = client.post("/api/v1/sources/translate", json=payload)

        assert resp.status_code == 502


class TestGlossaryEndpoint:
    def test_suggest(self, client):
        resp = client.get("/api/v1/suggest")
        assert resp.status_code == 200
        data = resp.json()
        assert "hot_questions" in data
        assert "domains" in data
        assert data["hot_questions"] == [
            "请给出混凝土结构设计中相关作用荷载和材料的分项系数。",
            "请给出混凝土材料的强度与变形的相关定义、相互关系及如何计算。",
            "有哪些因素会对混凝土的徐变与收缩产生影响?",
            "钢筋的主要特性有哪些?并给出相应总结。",
            "请问都有那些环境暴露等级?",
            "保护层都与什么因素相关，该怎么计算?",
            "结构分析的目的是什么?",
            "在哪些部位当线性应变分布的假设不成立时，可能需要进行局部分析?",
            "根据性质和功能，结构构件包括哪些类型?",
            "什么是单向板?",
            "欧标的截面计算的基本假设前提是什么？",
            "混凝土受压区应变-应力分布假设是什么？",
            "混凝土压碎应变限值是多少？",
            "极限受力状态下混凝土受压区高度限值为多少？",
            "弯矩重分布限值为多少？",
            "fcd 如何计算",
            "截面计算中材料分项安全系数为多少？",
            "混凝土抗压强度标准值、设计值与平均强度之间是什么关系？",
            "钢筋的锚固长度与搭接长度受哪些因素影响？",
            "什么情况下需要考虑二阶效应？",
            "受弯构件正截面承载力计算的一般步骤是什么？",
        ]
        assert data["domains"] == [
            {"id": "EN 1992-1-1", "name": "混凝土结构设计"},
        ]

    def test_glossary_list(self, client):
        resp = client.get("/api/v1/glossary")
        assert resp.status_code == 200
