"""API integration tests."""

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import fitz
import pytest
from fastapi.testclient import TestClient

from server import deps
from server.agents.evidence import EvidenceBundle
from server.agents.orchestrator import AgentProgress, AgentResult
from server.agents.qa_agent import AgentStreamEvent
from server.agents.tool_progress import ToolSubStep
from server.api.v1._response import _add_conversation_turn
from server.config import ServerConfig
from server.core.conversation import RedisConversationManager
from server.core import query_understanding
from server.core.retrieval import RetrievalResult
from server.errors import LLMUnavailableError
from server.main import app
from server.models.schemas import (
    Chunk,
    ChunkMetadata,
    ElementType,
    QueryResponse,
    RetrievalContext,
)


def _server_config(**overrides) -> ServerConfig:
    overrides.setdefault("access_password", "")
    return ServerConfig(**overrides)


def _analysis_stub(
    question: str,
    *,
    expanded_queries: list[str] | None = None,
    intent_label: str | None = None,
    target_hint: object = None,
    requested_objects: list[str] | None = None,
    question_type: object = None,
    engineering_context: object = None,
    guide_hint: object = None,
):
    return SimpleNamespace(
        expanded_queries=expanded_queries or [question],
        rewritten_query=question,
        original_question=question,
        filters={},
        matched_terms={},
        intent_label=intent_label,
        target_hint=target_hint,
        requested_objects=requested_objects or [],
        question_type=question_type,
        engineering_context=engineering_context,
        guide_hint=guide_hint,
        preferred_element_type=None,
    )


def _value(payload: object) -> object:
    return getattr(payload, "value", payload)


def _make_test_chunk() -> Chunk:
    return Chunk(
        chunk_id="test-chunk-1",
        content="Test Eurocode evidence.",
        embedding_text="Test Eurocode evidence",
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


async def _legacy_pipeline_dispatch_agent(
    question,
    req,
    config,
    retriever,
    glossary,
    conv_mgr,
):
    """Drive API tests through the new dispatch seam without real LLM calls."""
    getter = getattr(conv_mgr, "get_or_create_async", None)
    conv = (
        await getter(req.session_id or req.conversation_id)
        if getter is not None
        else conv_mgr.get_or_create(req.session_id or req.conversation_id)
    )
    analysis = await query_understanding.analyze_query(question, glossary, config)
    result = await retriever.retrieve(
        queries=analysis.expanded_queries,
        original_query=question,
        filters=analysis.filters,
        intent_label=analysis.intent_label,
        question_type=_value(analysis.question_type),
        guide_hint=analysis.guide_hint,
        target_hint=analysis.target_hint,
        requested_objects=analysis.requested_objects,
        preferred_element_type=analysis.preferred_element_type,
    )
    bundle = EvidenceBundle()
    bundle.add_retrieval(result)
    if not bundle.has_rag_evidence:
        bundle.chunks.append(_make_test_chunk())
    bundle.tool_trace.append(
        {
            "tool": "retrieve",
            "chunk_count": len(result.chunks),
        }
    )
    bundle.question_type = _value(analysis.question_type)
    bundle.engineering_context = analysis.engineering_context
    bundle.intent_label = analysis.intent_label
    return AgentResult(
        agent_reply="已检索到相关规范证据。",
        bundle=bundle,
        conv=conv,
        deps=None,
    )


async def _legacy_pipeline_dispatch_agent_streamed(*args, **kwargs):
    kwargs.pop("tool_progress", None)
    yield await _legacy_pipeline_dispatch_agent(*args, **kwargs)


@pytest.fixture
def client(monkeypatch):
    from server.api.v1 import query as query_module

    monkeypatch.setattr(
        query_module,
        "dispatch_agent",
        _legacy_pipeline_dispatch_agent,
    )
    monkeypatch.setattr(
        query_module,
        "dispatch_agent_streamed",
        _legacy_pipeline_dispatch_agent_streamed,
    )
    app.dependency_overrides = {
        deps.get_config: lambda: _server_config(access_password=""),
    }
    test_client = TestClient(app)
    yield test_client
    app.dependency_overrides = {}


class _FakeRedis:
    def __init__(self):
        self.lists: dict[str, list[str]] = {}
        self.hashes: dict[str, dict[str, str]] = {}
        self.expire_calls: list[tuple[str, int]] = []

    async def lrange(self, key, start, end):
        items = self.lists.get(key, [])
        return items[start:] if end == -1 else items[start : end + 1]

    async def rpush(self, key, *values):
        self.lists.setdefault(key, []).extend(values)

    async def expire(self, key, ttl_seconds):
        self.expire_calls.append((key, ttl_seconds))

    async def hget(self, key, field):
        return self.hashes.get(key, {}).get(field)

    async def hgetall(self, key):
        return self.hashes.get(key, {})

    async def hset(self, key, field, value):
        self.hashes.setdefault(key, {})[field] = value


class _FakeTaskManagerBase:
    def get_status_or_persisted(self, doc_id, parsed_dir):
        return self.get_status(doc_id)

    def subscribe(self, doc_id, parsed_dir=None):
        return self.subscribe(doc_id)


class TestRedisConversationManager:
    @pytest.mark.anyio
    async def test_reads_mixed_legacy_and_role_messages_as_history(self):
        manager = RedisConversationManager.__new__(RedisConversationManager)
        fake_redis = _FakeRedis()
        manager._redis = fake_redis
        fake_redis.lists["context:1001_abc123"] = [
            json.dumps({"question": "旧问题", "answer": "旧回答"}, ensure_ascii=False),
            json.dumps({"role": "user", "content": "新问题"}, ensure_ascii=False),
            json.dumps({"role": "assistant", "content": "新回答"}, ensure_ascii=False),
            json.dumps({"role": "user", "content": "孤立问题"}, ensure_ascii=False),
        ]

        state = await manager.get_or_create_async("1001_abc123")

        assert state.history == [
            {"question": "旧问题", "answer": "旧回答"},
            {"question": "新问题", "answer": "新回答"},
            {"question": "孤立问题", "answer": ""},
        ]

    @pytest.mark.anyio
    async def test_add_turn_writes_role_messages_and_returns_title_only_once(self):
        manager = RedisConversationManager.__new__(RedisConversationManager)
        fake_redis = _FakeRedis()
        manager._redis = fake_redis
        fake_redis.hashes["user:1001:sessions"] = {
            "1001_abc123": json.dumps(
                {"title": None, "createdAt": "2026-05-14T10:00:00Z"},
                ensure_ascii=False,
            )
        }

        first_title = await manager.add_turn_async(
            "1001_abc123",
            "EN 1992 中混凝土保护层最小厚度是多少？",
            "根据 EN 1992-1-1 ...",
        )
        second_title = await manager.add_turn_async(
            "1001_abc123",
            "第二轮问题",
            "第二轮回答",
        )

        messages = [json.loads(raw) for raw in fake_redis.lists["context:1001_abc123"]]
        assert [message["role"] for message in messages] == [
            "user",
            "assistant",
            "user",
            "assistant",
        ]
        assert messages[0]["content"] == "EN 1992 中混凝土保护层最小厚度是多少？"
        assert messages[1]["content"] == "根据 EN 1992-1-1 ..."
        assert all("timestamp" in message for message in messages)
        assert first_title == "EN 1992 中混凝土保护层最小厚度是多少？"
        assert second_title is None
        stored_meta = json.loads(fake_redis.hashes["user:1001:sessions"]["1001_abc123"])
        assert stored_meta["title"] == first_title
        assert fake_redis.expire_calls == []

    @pytest.mark.anyio
    async def test_add_turn_persists_assistant_reference_metadata(self):
        manager = RedisConversationManager.__new__(RedisConversationManager)
        fake_redis = _FakeRedis()
        manager._redis = fake_redis

        await manager.add_turn_async(
            "1001_refs",
            "设计使用年限是什么？",
            "应规定设计使用年限。[Ref-1]",
            sources=[
                {
                    "file": "EN 1990:2002",
                    "docId": "EN_1990_2002",
                    "title": "Basis of structural design",
                    "section": "2.3",
                    "page": "28",
                    "clause": "2.3",
                    "originalText": "The design working life should be specified.",
                    "locatorText": "2.3 Design working life",
                    "highlightText": "design working life",
                    "translation": "",
                    "elementType": "text",
                    "bbox": [],
                }
            ],
            related_refs=["Table 2.1"],
            retrieval_context={
                "chunks": [{"chunk_id": "c1", "source": "EN 1990:2002"}]
            },
            question_type="rule",
            engineering_context={"country": "EU"},
            answer_mode="standard",
            groundedness="grounded",
            thinking="先检索 EN 1990，再组织回答。",
            response_payload={
                "code": 200,
                "answer": "应规定设计使用年限。[Ref-1]",
                "normalized_answer": "应规定设计使用年限。[Ref-1]",
                "sources": [
                    {
                        "file": "EN 1990:2002",
                        "docId": "EN_1990_2002",
                    }
                ],
                "relatedRefs": ["Table 2.1"],
                "thinking": "先检索 EN 1990，再组织回答。",
                "questionType": "rule",
                "answerMode": "standard",
                "groundedness": "grounded",
                "title": None,
            },
        )

        messages = [json.loads(raw) for raw in fake_redis.lists["context:1001_refs"]]
        assistant_message = messages[1]
        assert assistant_message["role"] == "assistant"
        assert assistant_message["sources"][0]["file"] == "EN 1990:2002"
        assert assistant_message["sources"][0]["docId"] == "EN_1990_2002"
        assert assistant_message["sources"][0]["originalText"] == (
            "The design working life should be specified."
        )
        assert assistant_message["sources"][0]["elementType"] == "text"
        assert (
            assistant_message["retrievalContext"]["chunks"][0]["source"]
            == "EN 1990:2002"
        )
        assert assistant_message["relatedRefs"] == ["Table 2.1"]
        assert assistant_message["questionType"] == "rule"
        assert assistant_message["engineeringContext"] == {"country": "EU"}
        assert assistant_message["answerMode"] == "standard"
        assert assistant_message["groundedness"] == "grounded"
        assert assistant_message["thinking"] == "先检索 EN 1990，再组织回答。"
        assert assistant_message["response"]["code"] == 200
        assert (
            assistant_message["response"]["thinking"] == "先检索 EN 1990，再组织回答。"
        )
        assert assistant_message["response"]["sources"][0]["docId"] == "EN_1990_2002"
        assert assistant_message["response"]["title"] == ("设计使用年限是什么？")

    @pytest.mark.anyio
    async def test_get_session_restores_frontend_turns_from_redis_messages(self):
        manager = RedisConversationManager.__new__(RedisConversationManager)
        fake_redis = _FakeRedis()
        manager._redis = fake_redis
        fake_redis.hashes["user:1001:sessions"] = {
            "1001_restore": json.dumps(
                {
                    "title": "设计使用年限",
                    "updatedAt": "2026-05-31T10:00:00Z",
                },
                ensure_ascii=False,
            )
        }
        fake_redis.lists["context:1001_restore"] = [
            json.dumps(
                {
                    "role": "user",
                    "content": "设计使用年限是什么？",
                    "timestamp": "2026-05-31T09:59:00Z",
                },
                ensure_ascii=False,
            ),
            json.dumps(
                {
                    "role": "assistant",
                    "content": "应规定设计使用年限。[Ref-1]",
                    "timestamp": "2026-05-31T10:00:00Z",
                    "sources": [{"file": "EN 1990:2002", "docId": "EN_1990_2002"}],
                    "relatedRefs": ["Table 2.1"],
                    "retrievalContext": {"chunks": [{"chunk_id": "c1"}]},
                    "thinking": "先检索。",
                    "questionType": "rule",
                    "engineeringContext": {"country": "EU"},
                    "response": {
                        "answer": "应规定设计使用年限。[Ref-1]",
                        "normalized_answer": "应规定设计使用年限。[Ref-1]",
                        "confidence": "high",
                    },
                },
                ensure_ascii=False,
            ),
        ]

        session = await manager.get_session_async("1001_restore")

        assert session["session_id"] == "1001_restore"
        assert session["title"] == "设计使用年限"
        assert session["updated_at"] == "2026-05-31T10:00:00Z"
        assert len(session["messages"]) == 1
        turn = session["messages"][0]
        assert turn["question"] == "设计使用年限是什么？"
        assert turn["answer"] == "应规定设计使用年限。[Ref-1]"
        assert turn["reasoning"] == "先检索。"
        assert turn["confidence"] == "high"
        assert turn["sources"][0]["docId"] == "EN_1990_2002"
        assert turn["related_refs"] == ["Table 2.1"]
        assert turn["retrieval_context"]["chunks"][0]["chunk_id"] == "c1"
        assert turn["question_type"] == "rule"
        assert turn["engineering_context"] == {"country": "EU"}

    @pytest.mark.anyio
    async def test_get_sessions_returns_redis_metadata_summaries(self):
        manager = RedisConversationManager.__new__(RedisConversationManager)
        fake_redis = _FakeRedis()
        manager._redis = fake_redis
        fake_redis.hashes["user:1001:sessions"] = {
            "1001_old": json.dumps(
                {
                    "title": "旧会话",
                    "updatedAt": "2026-05-30T10:00:00Z",
                },
                ensure_ascii=False,
            ),
            "1001_new": json.dumps(
                {
                    "title": "新会话",
                    "updatedAt": "2026-05-31T10:00:00Z",
                },
                ensure_ascii=False,
            ),
        }
        fake_redis.lists["context:1001_new"] = [
            json.dumps({"role": "user", "content": "新问题"}, ensure_ascii=False),
            json.dumps({"role": "assistant", "content": "新回答"}, ensure_ascii=False),
            json.dumps({"role": "user", "content": "第二问"}, ensure_ascii=False),
            json.dumps({"role": "assistant", "content": "第二答"}, ensure_ascii=False),
        ]
        fake_redis.lists["context:1001_old"] = [
            json.dumps({"role": "user", "content": "旧问题"}, ensure_ascii=False),
            json.dumps({"role": "assistant", "content": "旧回答"}, ensure_ascii=False),
        ]

        payload = await manager.get_sessions_async("1001")

        assert [session["session_id"] for session in payload["sessions"]] == [
            "1001_new",
            "1001_old",
        ]
        assert payload["sessions"][0]["title"] == "新会话"
        assert payload["sessions"][0]["message_count"] == 2


class TestConversationTurnPersistence:
    @pytest.mark.anyio
    async def test_add_conversation_turn_passes_reference_metadata_to_async_manager(
        self,
    ):
        class _FakeConversationManager:
            def __init__(self):
                self.kwargs = None

            async def add_turn_async(self, conversation_id, question, answer, **kwargs):
                self.kwargs = kwargs
                return None

        manager = _FakeConversationManager()
        retrieval_context = RetrievalContext(
            chunks=[
                {
                    "chunk_id": "chunk_023",
                    "source": "EN 1990:2002",
                    "score": 0.91,
                }
            ]
        )

        await _add_conversation_turn(
            manager,
            "1001_refs",
            "设计使用年限是什么？",
            "应规定设计使用年限。[Ref-1]",
            sources=[
                {
                    "file": "EN 1990:2002",
                    "document_id": "EN_1990_2002",
                    "source": "EN 1990:2002",
                }
            ],
            related_refs=["Table 2.1"],
            retrieval_context=retrieval_context,
            question_type="rule",
            engineering_context={"country": "EU"},
            answer_mode="standard",
            groundedness="grounded",
            thinking="先检索 EN 1990。",
            response_payload={"code": 200, "thinking": "先检索 EN 1990。"},
        )

        assert manager.kwargs is not None
        assert manager.kwargs["sources"][0]["source"] == "EN 1990:2002"
        assert manager.kwargs["sources"][0]["docId"] == "EN_1990_2002"
        assert manager.kwargs["related_refs"] == ["Table 2.1"]
        assert (
            manager.kwargs["retrieval_context"]["chunks"][0]["source"] == "EN 1990:2002"
        )
        assert manager.kwargs["question_type"] == "rule"
        assert manager.kwargs["engineering_context"] == {"country": "EU"}
        assert manager.kwargs["answer_mode"] == "standard"
        assert manager.kwargs["groundedness"] == "grounded"
        assert manager.kwargs["thinking"] == "先检索 EN 1990。"
        assert manager.kwargs["response_payload"] == {
            "code": 200,
            "thinking": "先检索 EN 1990。",
        }

    @pytest.mark.anyio
    async def test_add_conversation_turn_keeps_legacy_async_manager_compatible(self):
        class _LegacyConversationManager:
            def __init__(self):
                self.turn = None

            async def add_turn_async(self, conversation_id, question, answer):
                self.turn = (conversation_id, question, answer)
                return None

        manager = _LegacyConversationManager()

        await _add_conversation_turn(
            manager,
            "1001_legacy",
            "问题",
            "回答",
            sources=[{"source": "EN 1990:2002"}],
        )

        assert manager.turn == ("1001_legacy", "问题", "回答")


class TestQueryEndpoint:
    def test_session_restore_endpoint_returns_frontend_contract(self, client):
        class _FakeConversationManager:
            def get_session(self, session_id):
                return {
                    "session_id": session_id,
                    "conversation_id": session_id,
                    "title": "恢复会话",
                    "updated_at": "2026-05-31T10:00:00Z",
                    "messages": [
                        {
                            "id": f"{session_id}-1",
                            "question": "问题",
                            "answer": "回答",
                            "reasoning": "",
                            "status": "done",
                            "confidence": "high",
                            "sources": [],
                            "related_refs": [],
                            "degraded": False,
                            "conversation_id": session_id,
                            "retrieval_context": None,
                            "question_type": None,
                            "engineering_context": None,
                            "progress_events": [],
                            "commentaries": [],
                        }
                    ],
                }

        app.dependency_overrides[deps.get_conversation_manager] = lambda: (
            _FakeConversationManager()
        )

        resp = client.get("/api/v1/sessions/1001_restore")

        assert resp.status_code == 200
        payload = resp.json()
        assert payload["sessionId"] == "1001_restore"
        assert payload["conversationId"] == "1001_restore"
        assert payload["messages"][0]["relatedRefs"] == []
        assert payload["messages"][0]["conversationId"] == "1001_restore"

    def test_session_list_endpoint_returns_frontend_contract(self, client):
        class _FakeConversationManager:
            def get_sessions(self, user_id):
                assert user_id == "1001"
                return {
                    "sessions": [
                        {
                            "session_id": "1001_restore",
                            "conversation_id": "1001_restore",
                            "title": "恢复会话",
                            "updated_at": "2026-05-31T10:00:00Z",
                            "message_count": 2,
                        }
                    ]
                }

        app.dependency_overrides[deps.get_conversation_manager] = lambda: (
            _FakeConversationManager()
        )

        resp = client.get("/api/v1/sessions?userId=1001")

        assert resp.status_code == 200
        payload = resp.json()
        assert payload["sessions"][0]["sessionId"] == "1001_restore"
        assert payload["sessions"][0]["conversationId"] == "1001_restore"
        assert payload["sessions"][0]["messageCount"] == 2

    def test_session_list_requires_auth_when_password_enabled(self, client):
        app.dependency_overrides[deps.get_config] = lambda: _server_config(
            access_password="required"
        )

        resp = client.get("/api/v1/sessions?userId=1001")

        assert resp.status_code == 200
        assert resp.json()["code"] == 401

    def test_public_query_stream_contract_bypasses_auth_when_password_enabled(
        self,
        client,
    ):
        class _FakeRetriever:
            async def prefetch_vectors(self, query, filters=None):
                return []

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

        async def _fake_generate_answer_stream(**kwargs):
            yield ("done", {"sources": [], "related_refs": [], "confidence": "low"})

        app.dependency_overrides[deps.get_config] = lambda: _server_config(
            access_password="required"
        )
        app.dependency_overrides[deps.get_retriever] = lambda: _FakeRetriever()
        app.dependency_overrides[deps.get_conversation_manager] = lambda: (
            _FakeConversationManager()
        )
        app.dependency_overrides[deps.get_glossary] = lambda: {}

        async def _fake_analyze_query(question, glossary, config, history=None):
            return _analysis_stub(question)

        with (
            patch("server.core.query_understanding.analyze_query", _fake_analyze_query),
            patch(
                "server.api.v1._response.generate_answer_stream",
                _fake_generate_answer_stream,
            ),
        ):
            resp = client.post(
                "/api/v1/query/stream",
                json={"question": "设计使用年限是什么？", "stream": True},
            )

        assert resp.status_code == 200
        assert "event: done" in resp.text

    def test_non_contract_query_endpoint_still_requires_auth_when_password_enabled(
        self,
        client,
    ):
        app.dependency_overrides[deps.get_config] = lambda: _server_config(
            access_password="required"
        )

        resp = client.post("/api/v1/query", json={"question": "设计使用年限是什么？"})

        assert resp.status_code == 200
        assert resp.json()["code"] == 401

    def test_query_validation_missing_question(self, client):
        resp = client.post("/api/v1/query", json={})
        assert resp.status_code == 200
        assert resp.json()["code"] == 400
        assert resp.json()["message"] == "参数错误"

    def test_question_max_length(self, client):
        resp = client.post("/api/v1/query", json={"question": "x" * 501})
        assert resp.status_code == 200
        assert resp.json()["code"] == 400
        assert resp.json()["message"] == "参数错误"

    def test_stream_query_does_not_500_when_query_rewrite_llm_fails(self, client):
        class _FakeRetriever:
            async def prefetch_vectors(self, query, filters=None):
                return []

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
        app.dependency_overrides[deps.get_conversation_manager] = lambda: (
            _FakeConversationManager()
        )
        app.dependency_overrides[deps.get_glossary] = lambda: {}

        with (
            patch(
                "server.core.query_understanding._call_llm",
                AsyncMock(side_effect=RuntimeError("llm unavailable")),
            ),
            patch("server.api.v1._response.generate_answer_stream", _fake_stream),
        ):
            resp = client.post(
                "/api/v1/query/stream",
                json={"question": "巴黎的地铁的使用期限有多久？", "stream": True},
            )

        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")

    def test_query_endpoint_applies_request_scoped_llm_overrides(self, client):
        class _FakeRetriever:
            async def prefetch_vectors(self, query, filters=None):
                return []

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
        app.dependency_overrides[deps.get_conversation_manager] = lambda: (
            _FakeConversationManager()
        )
        app.dependency_overrides[deps.get_glossary] = lambda: {}
        app.dependency_overrides[deps.get_config] = lambda: _server_config(
            llm_api_key="default-key",
            llm_base_url="https://default.example/v1",
            llm_model="default-model",
            llm_enable_thinking=False,
        )

        seen_configs: list[tuple[str, str, str, bool]] = []

        async def _fake_analyze_query(question, glossary, config, history=None):
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
            patch("server.core.query_understanding.analyze_query", _fake_analyze_query),
            patch("server.api.v1._response.generate_answer", _fake_generate_answer),
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

    def test_query_endpoint_returns_degraded_response_for_agent_error(
        self,
        client,
        monkeypatch,
    ):
        async def _fake_dispatch_agent(*_args, **_kwargs):
            raise LLMUnavailableError("agent 决策超时")

        from server.api.v1 import query as query_module

        monkeypatch.setattr(query_module, "dispatch_agent", _fake_dispatch_agent)

        resp = client.post(
            "/api/v1/query",
            json={"question": "钢筋的主要特性有哪些？", "sessionId": "session-1"},
        )

        assert resp.status_code == 200
        payload = resp.json()
        assert payload["degraded"] is True
        assert payload["confidence"] == "low"
        assert payload["conversation_id"] == "session-1"
        assert "语言模型暂时不可用" in payload["answer"]

    def test_query_endpoint_does_not_forward_or_store_conversation_history(
        self, client
    ):
        class _FakeRetriever:
            async def prefetch_vectors(self, query, filters=None):
                return []

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
        app.dependency_overrides[deps.get_conversation_manager] = lambda: (
            conversation_manager
        )
        app.dependency_overrides[deps.get_glossary] = lambda: {}

        seen_histories: list[list[dict[str, str]]] = []

        async def _fake_analyze_query(question, glossary, config, history=None):
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
            patch("server.core.query_understanding.analyze_query", _fake_analyze_query),
            patch("server.api.v1._response.generate_answer", _fake_generate_answer),
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
            async def prefetch_vectors(self, query, filters=None):
                return []

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
        app.dependency_overrides[deps.get_conversation_manager] = lambda: (
            conversation_manager
        )
        app.dependency_overrides[deps.get_glossary] = lambda: {}

        seen_histories: list[list[dict[str, str]]] = []

        async def _fake_analyze_query(question, glossary, config, history=None):
            return _analysis_stub(question)

        async def _fake_generate_answer_stream(**kwargs):
            seen_histories.append(kwargs["conversation_history"])
            yield ("done", {"sources": [], "related_refs": [], "confidence": "low"})

        with (
            patch("server.core.query_understanding.analyze_query", _fake_analyze_query),
            patch(
                "server.api.v1._response.generate_answer_stream",
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

    def test_query_endpoint_uses_redis_style_conversation_history_when_available(
        self, client
    ):
        class _FakeRetriever:
            async def prefetch_vectors(self, query, filters=None):
                return []

            async def retrieve(self, **kwargs):
                return RetrievalResult(chunks=[], parent_chunks=[], scores=[])

        class _FakeConversationManager:
            def __init__(self):
                self.add_turn_calls: list[tuple[str, str, str]] = []

            async def get_or_create_async(self, conversation_id):
                return SimpleNamespace(
                    conversation_id=conversation_id,
                    history=[{"question": "上一轮问题", "answer": "上一轮回答"}],
                )

            async def add_turn_async(self, conversation_id, question, answer):
                self.add_turn_calls.append((conversation_id, question, answer))
                return "设计使用年限"

        conversation_manager = _FakeConversationManager()
        app.dependency_overrides[deps.get_retriever] = lambda: _FakeRetriever()
        app.dependency_overrides[deps.get_conversation_manager] = lambda: (
            conversation_manager
        )
        app.dependency_overrides[deps.get_glossary] = lambda: {}

        seen_histories: list[list[dict[str, str]]] = []

        async def _fake_analyze_query(question, glossary, config, history=None):
            return _analysis_stub(question)

        async def _fake_generate_answer(**kwargs):
            seen_histories.append(kwargs["conversation_history"])
            return QueryResponse(
                answer="本轮回答",
                sources=[],
                related_refs=[],
                confidence="low",
                degraded=False,
                conversation_id="1001_abc123",
            )

        with (
            patch("server.core.query_understanding.analyze_query", _fake_analyze_query),
            patch("server.api.v1._response.generate_answer", _fake_generate_answer),
        ):
            resp = client.post(
                "/api/v1/query",
                json={"sessionId": "1001_abc123", "question": "本轮问题"},
            )

        assert resp.status_code == 200
        assert seen_histories == [[{"question": "上一轮问题", "answer": "上一轮回答"}]]
        assert conversation_manager.add_turn_calls == [
            ("1001_abc123", "本轮问题", "本轮回答")
        ]

    def test_query_stream_persists_answer_and_title_with_async_manager(self, client):
        class _FakeRetriever:
            async def prefetch_vectors(self, query, filters=None):
                return []

            async def retrieve(self, **kwargs):
                return RetrievalResult(chunks=[], parent_chunks=[], scores=[])

        class _FakeConversationManager:
            def __init__(self):
                self.add_turn_calls: list[tuple[str, str, str]] = []

            async def get_or_create_async(self, conversation_id):
                return SimpleNamespace(conversation_id=conversation_id, history=[])

            async def add_turn_async(self, conversation_id, question, answer):
                self.add_turn_calls.append((conversation_id, question, answer))
                return "自动标题"

        conversation_manager = _FakeConversationManager()
        app.dependency_overrides[deps.get_retriever] = lambda: _FakeRetriever()
        app.dependency_overrides[deps.get_conversation_manager] = lambda: (
            conversation_manager
        )
        app.dependency_overrides[deps.get_glossary] = lambda: {}

        async def _fake_analyze_query(question, glossary, config, history=None):
            return _analysis_stub(question, question_type=SimpleNamespace(value="rule"))

        async def _fake_generate_answer_stream(**kwargs):
            yield ("chunk", {"text": "回答"})
            yield ("chunk", {"text": "正文"})
            yield ("done", {"sources": [], "related_refs": [], "confidence": "low"})

        with (
            patch("server.core.query_understanding.analyze_query", _fake_analyze_query),
            patch(
                "server.api.v1._response.generate_answer_stream",
                _fake_generate_answer_stream,
            ),
        ):
            resp = client.post(
                "/api/v1/query/stream",
                json={
                    "sessionId": "1001_abc123",
                    "question": "本轮问题",
                    "stream": True,
                },
            )

        assert resp.status_code == 200
        done_event = next(
            segment
            for segment in resp.text.split("\r\n\r\n")
            if "event: done" in segment
        )
        done_payload = json.loads(done_event.split("data: ", 1)[1].strip())
        assert done_payload["title"] == "自动标题"
        assert conversation_manager.add_turn_calls == [
            ("1001_abc123", "本轮问题", "回答正文")
        ]

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
        app.dependency_overrides[deps.get_conversation_manager] = lambda: (
            _FakeConversationManager()
        )

        seen_retrieve_calls: list[dict[str, object]] = []

        class _FakeRetriever:
            async def prefetch_vectors(self, query, filters=None):
                return []

            async def retrieve(self, **kwargs):
                seen_retrieve_calls.append(kwargs)
                return RetrievalResult(chunks=[], parent_chunks=[], scores=[])

        async def _fake_analyze_query(question, glossary, config, history=None):
            return _analysis_stub(
                question,
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
            patch("server.core.query_understanding.analyze_query", _fake_analyze_query),
            patch("server.api.v1._response.generate_answer", _fake_generate_answer),
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

    def test_query_endpoint_passes_expanded_queries_to_retriever(self, client):
        class _FakeConversationManager:
            def get_or_create(self, conversation_id):
                return SimpleNamespace(
                    conversation_id=conversation_id or "conv-1",
                    history=[],
                )

            def add_turn(self, conversation_id, question, answer):
                return None

        app.dependency_overrides[deps.get_glossary] = lambda: {}
        app.dependency_overrides[deps.get_conversation_manager] = lambda: (
            _FakeConversationManager()
        )

        seen_queries: list[list[str]] = []

        class _FakeRetriever:
            async def prefetch_vectors(self, query, filters=None):
                return []

            async def retrieve(self, **kwargs):
                seen_queries.append(kwargs["queries"])
                return RetrievalResult(chunks=[], parent_chunks=[], scores=[])

        async def _fake_analyze_query(question, glossary, config, history=None):
            return _analysis_stub(
                question,
                expanded_queries=[
                    "design working life metro",
                    "design working life concept",
                    "design working life terms",
                ],
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
            patch("server.core.query_understanding.analyze_query", _fake_analyze_query),
            patch("server.api.v1._response.generate_answer", _fake_generate_answer),
        ):
            resp = client.post(
                "/api/v1/query",
                json={"question": "地铁的设计使用年限是多久？"},
            )

        assert resp.status_code == 200
        assert seen_queries == [
            [
                "design working life metro",
                "design working life concept",
                "design working life terms",
            ]
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
        app.dependency_overrides[deps.get_conversation_manager] = lambda: (
            _FakeConversationManager()
        )

        class _FakeRetriever:
            async def prefetch_vectors(self, query, filters=None):
                return []

            async def retrieve(self, **kwargs):
                return RetrievalResult(
                    chunks=[],
                    parent_chunks=[],
                    scores=[0.91],
                    groundedness="grounded",
                )

        async def _fake_analyze_query(question, glossary, config, history=None):
            return _analysis_stub(
                question,
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
            patch("server.core.query_understanding.analyze_query", _fake_analyze_query),
            patch("server.api.v1._response.generate_answer", _fake_generate_answer),
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
        assert (
            resp.json()["retrieval_context"]["guide_example_chunks"][0]["chunk_id"]
            == "guide-example-1"
        )
        assert resp.json()["groundedness"] == "grounded"

    def test_query_stream_endpoint_ignores_blank_llm_override_values(self, client):
        class _FakeRetriever:
            async def prefetch_vectors(self, query, filters=None):
                return []

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
        app.dependency_overrides[deps.get_conversation_manager] = lambda: (
            _FakeConversationManager()
        )
        app.dependency_overrides[deps.get_glossary] = lambda: {}
        app.dependency_overrides[deps.get_config] = lambda: _server_config(
            llm_api_key="default-key",
            llm_base_url="https://default.example/v1",
            llm_model="default-model",
            llm_enable_thinking=True,
        )

        seen_configs: list[tuple[str, str, str, bool]] = []

        async def _fake_analyze_query(question, glossary, config, history=None):
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
            patch("server.core.query_understanding.analyze_query", _fake_analyze_query),
            patch(
                "server.api.v1._response.generate_answer_stream",
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
            async def prefetch_vectors(self, query, filters=None):
                return []

            async def retrieve(self, **kwargs):
                return RetrievalResult(
                    chunks=[], parent_chunks=[], scores=[0.91], groundedness="grounded"
                )

        class _FakeConversationManager:
            def get_or_create(self, conversation_id):
                return SimpleNamespace(
                    conversation_id=conversation_id or "conv-1",
                    history=[],
                )

            def add_turn(self, conversation_id, question, answer):
                return None

        async def _fake_analyze_query(question, glossary, config, history=None):
            return _analysis_stub(
                question,
                intent_label="assumption",
            )

        async def _fake_generate_answer_stream(**kwargs):
            yield (
                "done",
                {
                    "sources": [],
                    "related_refs": [],
                    "confidence": "low",
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
        app.dependency_overrides[deps.get_conversation_manager] = lambda: (
            _FakeConversationManager()
        )
        app.dependency_overrides[deps.get_glossary] = lambda: {}

        with (
            patch("server.core.query_understanding.analyze_query", _fake_analyze_query),
            patch(
                "server.api.v1._response.generate_answer_stream",
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
        assert '"groundedness": "grounded"' in resp.text
        assert '"answerMode": "standard"' in resp.text
        assert '"confidence": "low"' in resp.text

    def test_query_stream_emits_user_friendly_progress_events(self, client):
        class _FakeRetriever:
            async def prefetch_vectors(self, query, filters=None):
                return []

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
                return SimpleNamespace(
                    conversation_id=conversation_id or "conv-1", history=[]
                )

            def add_turn(self, conversation_id, question, answer):
                return None

        async def _fake_analyze_query(question, glossary, config, history=None):
            return _analysis_stub(
                question,
                intent_label="limit",
                question_type=SimpleNamespace(value="parameter"),
                target_hint=SimpleNamespace(
                    document="EN 1990", clause="2.3", object=None
                ),
            )

        async def _fake_generate_answer_stream(**kwargs):
            yield ("done", {"sources": [], "related_refs": []})

        app.dependency_overrides[deps.get_retriever] = lambda: _FakeRetriever()
        app.dependency_overrides[deps.get_conversation_manager] = lambda: (
            _FakeConversationManager()
        )
        app.dependency_overrides[deps.get_glossary] = lambda: {}

        with (
            patch("server.core.query_understanding.analyze_query", _fake_analyze_query),
            patch(
                "server.api.v1._response.generate_answer_stream",
                _fake_generate_answer_stream,
            ),
        ):
            resp = client.post(
                "/api/v1/query/stream",
                json={"question": "设计使用年限怎么确定？", "stream": True},
            )

        assert resp.status_code == 200
        assert "event: progress" in resp.text
        assert '"title": "分析问题"' in resp.text
        assert '"stage": "agent_thinking"' in resp.text
        assert '"title": "检索规范条文"' in resp.text
        assert "找到 0 条相关规范证据" not in resp.text
        assert '"title": "生成回答"' in resp.text

    def test_query_stream_forwards_agent_tool_progress_and_commentary(
        self,
        client,
        monkeypatch,
    ):
        class _FakeConversationManager:
            def get_or_create(self, conversation_id):
                return SimpleNamespace(
                    conversation_id=conversation_id or "conv-1",
                    history=[],
                )

            def add_turn(self, conversation_id, question, answer):
                return None

        async def _fake_dispatch_agent_streamed(
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
            bundle.chunks.append(_make_test_chunk())
            bundle.tool_trace.append({"tool": "retrieve", "chunk_count": 1})
            if tool_progress is not None:
                await tool_progress.on_tool_sub_step(
                    ToolSubStep(
                        tool_name="retrieve",
                        step_id="query_understanding",
                        status="completed",
                        title="理解问题",
                        summary="识别为parameter问题，扩展 3 条查询",
                        metadata={
                            "was_rewritten": False,
                            "expanded_queries": ["design working life"],
                        },
                        elapsed_ms=12,
                    )
                )
            yield AgentProgress(
                event=AgentStreamEvent(
                    kind="tool_calling",
                    tool_name="retrieve",
                    tool_args={
                        "call_id": "call-1",
                        "arguments": '{"query": "design working life", "top_k": 6}',
                    },
                    summary="正在搜索规范知识库：「设计使用年限」...",
                )
            )
            yield AgentProgress(
                event=AgentStreamEvent(
                    kind="tool_result",
                    tool_name="retrieve",
                    tool_args={
                        "call_id": "call-1",
                        "arguments": '{"query": "design working life", "top_k": 6}',
                    },
                    tool_result="检索到 1 个片段，groundedness=grounded。",
                    tool_trace={
                        "tool": "retrieve",
                        "query": "design working life",
                        "expanded_queries": ["design working life", "设计使用年限"],
                        "chunk_count": 1,
                        "groundedness": "grounded",
                    },
                    summary="检索到 1 个片段。",
                )
            )
            yield AgentResult(
                agent_reply="已检索到相关规范证据。",
                bundle=bundle,
                conv=conv,
                deps=None,
            )

        async def _fake_generate_answer_stream(**kwargs):
            yield ("done", {"sources": [], "related_refs": []})

        from server.api.v1 import query as query_module

        app.dependency_overrides[deps.get_conversation_manager] = lambda: (
            _FakeConversationManager()
        )
        monkeypatch.setattr(
            query_module,
            "dispatch_agent_streamed",
            _fake_dispatch_agent_streamed,
        )

        with patch(
            "server.api.v1._response.generate_answer_stream",
            _fake_generate_answer_stream,
        ):
            resp = client.post(
                "/api/v1/query/stream",
                json={"question": "设计使用年限怎么确定？", "stream": True},
            )

        assert resp.status_code == 200
        assert '"stage": "tool:retrieve"' in resp.text
        assert '"title": "检索规范知识库"' in resp.text
        assert '"tool_args": {"query": "design working life", "top_k": 6}' in resp.text
        assert '"tool_result": "检索到 1 个片段，groundedness=grounded。"' in resp.text
        assert (
            '"expanded_queries": ["design working life", "设计使用年限"]' in resp.text
        )
        assert "event: tool_progress" in resp.text
        assert '"step_id": "query_understanding"' in resp.text
        assert '"was_rewritten": false' in resp.text
        assert "event: commentary" in resp.text
        assert "正在搜索规范知识库" in resp.text

    def test_query_endpoint_threads_question_type_to_retriever(self, client):
        seen_retrieval_kwargs = {}

        class _FakeRetriever:
            async def prefetch_vectors(self, query, filters=None):
                return []

            async def retrieve(self, **kwargs):
                seen_retrieval_kwargs.update(kwargs)
                return RetrievalResult(chunks=[], parent_chunks=[], scores=[])

        class _FakeConversationManager:
            def get_or_create(self, conversation_id):
                return SimpleNamespace(
                    conversation_id=conversation_id or "conv-1", history=[]
                )

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
        app.dependency_overrides[deps.get_conversation_manager] = lambda: (
            _FakeConversationManager()
        )
        app.dependency_overrides[deps.get_glossary] = lambda: {}

        async def _fake_analyze_query(question, glossary, config, history=None):
            return _analysis_stub(
                question,
                intent_label="calculation",
                question_type=SimpleNamespace(value="calculation"),
                guide_hint=SimpleNamespace(
                    need_example=True,
                    example_query="design value worked example",
                    example_kind="worked_example",
                ),
            )

        with (
            patch("server.core.query_understanding.analyze_query", _fake_analyze_query),
            patch("server.api.v1._response.generate_answer", _fake_generate_answer),
        ):
            resp = client.post("/api/v1/query", json={"question": "怎么计算组合值？"})

        assert resp.status_code == 200
        assert seen_retrieval_kwargs["question_type"] == "calculation"
        assert seen_retrieval_kwargs["guide_hint"].need_example is True

    def test_query_endpoint_returns_groundedness(self, client):
        class _FakeRetriever:
            async def prefetch_vectors(self, query, filters=None):
                return []

            async def retrieve(self, **kwargs):
                return RetrievalResult(
                    chunks=[],
                    parent_chunks=[],
                    scores=[],
                    groundedness="not_grounded",
                )

        class _FakeConversationManager:
            def get_or_create(self, conversation_id):
                return SimpleNamespace(
                    conversation_id=conversation_id or "conv-1", history=[]
                )

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
        app.dependency_overrides[deps.get_conversation_manager] = lambda: (
            _FakeConversationManager()
        )
        app.dependency_overrides[deps.get_glossary] = lambda: {}

        async def _fake_analyze_query(question, glossary, config, history=None):
            return _analysis_stub(question, intent_label="assumption")

        with (
            patch("server.core.query_understanding.analyze_query", _fake_analyze_query),
            patch("server.api.v1._response.generate_answer", _fake_generate_answer),
        ):
            resp = client.post(
                "/api/v1/query", json={"question": "欧标的截面计算的基本假设前提是什么"}
            )

        assert resp.status_code == 200
        assert resp.json()["groundedness"] == "not_grounded"

    def test_query_stream_done_event_includes_groundedness(self, client):
        class _FakeRetriever:
            async def prefetch_vectors(self, query, filters=None):
                return []

            async def retrieve(self, **kwargs):
                return RetrievalResult(
                    chunks=[], parent_chunks=[], scores=[], groundedness="grounded"
                )

        class _FakeConversationManager:
            def get_or_create(self, conversation_id):
                return SimpleNamespace(
                    conversation_id=conversation_id or "conv-1", history=[]
                )

            def add_turn(self, conversation_id, question, answer):
                return None

        async def _fake_generate_answer_stream(**kwargs):
            yield ("done", {"sources": [], "related_refs": []})

        app.dependency_overrides[deps.get_retriever] = lambda: _FakeRetriever()
        app.dependency_overrides[deps.get_conversation_manager] = lambda: (
            _FakeConversationManager()
        )
        app.dependency_overrides[deps.get_glossary] = lambda: {}

        async def _fake_analyze_query(question, glossary, config, history=None):
            return _analysis_stub(question, intent_label="assumption")

        with (
            patch("server.core.query_understanding.analyze_query", _fake_analyze_query),
            patch(
                "server.api.v1._response.generate_answer_stream",
                _fake_generate_answer_stream,
            ),
        ):
            resp = client.post(
                "/api/v1/query/stream",
                json={"question": "欧标的截面计算的基本假设前提是什么", "stream": True},
            )

        assert resp.status_code == 200
        done_event = next(
            segment
            for segment in resp.text.split("\r\n\r\n")
            if "event: done" in segment
        )
        done_payload = json.loads(done_event.split("data: ", 1)[1].strip())
        assert done_payload["groundedness"] == "grounded"
        assert done_payload["answerMode"] == "standard"
        assert done_payload["confidence"] == "high"

    def test_query_stream_accepts_session_id_and_emits_external_done_aliases(
        self, client
    ):
        seen_conversation_ids: list[str | None] = []
        persisted_turn: dict[str, object] = {}

        class _FakeRetriever:
            async def prefetch_vectors(self, query, filters=None):
                return []

            async def retrieve(self, **kwargs):
                return RetrievalResult(
                    chunks=[], parent_chunks=[], scores=[], groundedness="grounded"
                )

        class _FakeConversationManager:
            def get_or_create(self, conversation_id):
                seen_conversation_ids.append(conversation_id)
                return SimpleNamespace(
                    conversation_id=conversation_id or "conv-1", history=[]
                )

            def add_turn(self, conversation_id, question, answer, **kwargs):
                persisted_turn.update(
                    {
                        "conversation_id": conversation_id,
                        "question": question,
                        "answer": answer,
                        **kwargs,
                    }
                )
                return None

        async def _fake_generate_answer_stream(**kwargs):
            yield ("reasoning", {"text": "先找 EN 1990。"})
            yield ("reasoning", {"text": "再整理引用。"})
            yield (
                "done",
                {
                    "answer": "应规定设计使用年限。[Ref-1]",
                    "sources": [
                        {
                            "file": "EN 1990:2002",
                            "document_id": "EN_1990_2002",
                            "element_type": "image",
                            "title": "Eurocode - Basis of structural design",
                            "section": "Section 2",
                            "page": "28",
                            "clause": "2.3(1)",
                            "original_text": "The design working life should be specified.",
                            "locator_text": "2.3 Design working life",
                            "highlight_text": "design working life",
                            "translation": "应规定设计使用年限。",
                        }
                    ],
                    "related_refs": ["Table 2.1"],
                    "confidence": "high",
                },
            )

        app.dependency_overrides[deps.get_retriever] = lambda: _FakeRetriever()
        app.dependency_overrides[deps.get_conversation_manager] = lambda: (
            _FakeConversationManager()
        )
        app.dependency_overrides[deps.get_glossary] = lambda: {}

        async def _fake_analyze_query(question, glossary, config, history=None):
            return _analysis_stub(
                question,
                intent_label="parameter",
                question_type=SimpleNamespace(value="parameter"),
            )

        with (
            patch("server.core.query_understanding.analyze_query", _fake_analyze_query),
            patch(
                "server.api.v1._response.generate_answer_stream",
                _fake_generate_answer_stream,
            ),
        ):
            resp = client.post(
                "/api/v1/query/stream",
                json={
                    "sessionId": "1001_abc123",
                    "question": "设计使用年限是什么？",
                    "stream": True,
                },
            )

        assert resp.status_code == 200
        done_event = next(
            segment
            for segment in resp.text.split("\r\n\r\n")
            if "event: done" in segment
        )
        done_payload = json.loads(done_event.split("data: ", 1)[1].strip())
        assert seen_conversation_ids == ["1001_abc123"]
        assert done_payload["code"] == 200
        assert done_payload["questionType"] == "parameter"
        assert done_payload["answerMode"] == "standard"
        assert done_payload["confidence"] == "high"
        assert done_payload["relatedRefs"] == ["Table 2.1"]
        assert done_payload["title"] is None
        assert done_payload["sources"][0]["docId"] == "EN_1990_2002"
        assert done_payload["sources"][0]["elementType"] == "figure"
        assert done_payload["sources"][0]["originalText"] == (
            "The design working life should be specified."
        )
        assert done_payload["sources"][0]["locatorText"] == "2.3 Design working life"
        assert done_payload["thinking"] == "先找 EN 1990。再整理引用。"
        assert persisted_turn["thinking"] == "先找 EN 1990。再整理引用。"
        assert persisted_turn["response_payload"]["code"] == 200
        assert (
            persisted_turn["response_payload"]["thinking"]
            == "先找 EN 1990。再整理引用。"
        )
        assert (
            persisted_turn["response_payload"]["sources"][0]["docId"] == "EN_1990_2002"
        )
        assert persisted_turn["response_payload"]["title"] is None

    def test_query_endpoint_threads_intent_label_to_generate_answer(self, client):
        class _FakeRetriever:
            async def prefetch_vectors(self, query, filters=None):
                return []

            async def retrieve(self, **kwargs):
                return RetrievalResult(
                    chunks=[], parent_chunks=[], scores=[], groundedness="grounded"
                )

        class _FakeConversationManager:
            def get_or_create(self, conversation_id):
                return SimpleNamespace(
                    conversation_id=conversation_id or "conv-1", history=[]
                )

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
        app.dependency_overrides[deps.get_conversation_manager] = lambda: (
            _FakeConversationManager()
        )
        app.dependency_overrides[deps.get_glossary] = lambda: {}

        async def _fake_analyze_query(question, glossary, config, history=None):
            return _analysis_stub(question, intent_label="assumption")

        with (
            patch("server.core.query_understanding.analyze_query", _fake_analyze_query),
            patch("server.api.v1._response.generate_answer", _fake_generate_answer),
        ):
            resp = client.post(
                "/api/v1/query", json={"question": "欧标的截面计算的基本假设前提是什么"}
            )

        assert resp.status_code == 200
        assert seen_kwargs["intent_label"] == "assumption"

    def test_query_stream_threads_intent_label_to_generate_answer_stream(self, client):
        class _FakeRetriever:
            async def prefetch_vectors(self, query, filters=None):
                return []

            async def retrieve(self, **kwargs):
                return RetrievalResult(
                    chunks=[], parent_chunks=[], scores=[], groundedness="grounded"
                )

        class _FakeConversationManager:
            def get_or_create(self, conversation_id):
                return SimpleNamespace(
                    conversation_id=conversation_id or "conv-1", history=[]
                )

            def add_turn(self, conversation_id, question, answer):
                return None

        seen_kwargs = {}

        async def _fake_generate_answer_stream(**kwargs):
            seen_kwargs.update(kwargs)
            yield ("done", {"sources": [], "related_refs": [], "confidence": "low"})

        app.dependency_overrides[deps.get_retriever] = lambda: _FakeRetriever()
        app.dependency_overrides[deps.get_conversation_manager] = lambda: (
            _FakeConversationManager()
        )
        app.dependency_overrides[deps.get_glossary] = lambda: {}

        async def _fake_analyze_query(question, glossary, config, history=None):
            return _analysis_stub(question, intent_label="assumption")

        with (
            patch("server.core.query_understanding.analyze_query", _fake_analyze_query),
            patch(
                "server.api.v1._response.generate_answer_stream",
                _fake_generate_answer_stream,
            ),
        ):
            resp = client.post(
                "/api/v1/query/stream",
                json={"question": "欧标的截面计算的基本假设前提是什么", "stream": True},
            )

        assert resp.status_code == 200
        assert seen_kwargs["intent_label"] == "assumption"

    def test_query_stream_error_event_uses_external_contract(self, client):
        class _FakeRetriever:
            async def prefetch_vectors(self, query, filters=None):
                return []

            async def retrieve(self, **kwargs):
                raise RuntimeError("retrieval unavailable")

        class _FakeConversationManager:
            def get_or_create(self, conversation_id):
                return SimpleNamespace(
                    conversation_id=conversation_id or "conv-1", history=[]
                )

        async def _fake_analyze_query(question, glossary, config, history=None):
            return _analysis_stub(question, intent_label="assumption")

        app.dependency_overrides[deps.get_retriever] = lambda: _FakeRetriever()
        app.dependency_overrides[deps.get_conversation_manager] = lambda: (
            _FakeConversationManager()
        )
        app.dependency_overrides[deps.get_glossary] = lambda: {}

        with patch(
            "server.core.query_understanding.analyze_query", _fake_analyze_query
        ):
            resp = client.post(
                "/api/v1/query/stream",
                json={"question": "欧标的截面计算的基本假设前提是什么", "stream": True},
            )

        assert resp.status_code == 200
        error_event = next(
            segment
            for segment in resp.text.split("\r\n\r\n")
            if "event: error" in segment
        )
        error_payload = json.loads(error_event.split("data: ", 1)[1].strip())
        assert error_payload == {
            "code": 503,
            "message": "处理请求时发生内部错误，请重试",
        }


class TestLlmSettingsEndpoint:
    def test_get_llm_settings_masks_api_key(self, client):
        app.dependency_overrides[deps.get_config] = lambda: _server_config(
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
    def test_public_document_parse_contract_bypasses_auth_when_password_enabled(
        self,
        client,
        tmp_path: Path,
    ):
        pdf_dir = tmp_path / "pdfs"
        source_pdf = tmp_path / "uploads" / "EN 1992-1-1.pdf"
        source_pdf.parent.mkdir()
        source_pdf.write_bytes(b"%PDF-1.4 demo")
        app.dependency_overrides[deps.get_config] = lambda: _server_config(
            access_password="required",
            pdf_dir=str(pdf_dir),
            parsed_dir=str(tmp_path / "parsed"),
        )

        class _FakeTaskManager(_FakeTaskManagerBase):
            def get_status(self, doc_id):
                return None

            def enqueue(self, doc_id):
                return None

        with patch(
            "server.api.v1.documents.get_task_manager",
            return_value=_FakeTaskManager(),
        ):
            resp = client.post(
                "/api/v1/documents/parse",
                json={
                    "docId": "EN_1992_1_1",
                    "fileName": "EN 1992-1-1.pdf",
                    "minioPath": str(source_pdf),
                },
            )

        assert resp.status_code == 200

    def test_internal_document_upload_still_requires_auth_when_password_enabled(
        self,
        client,
    ):
        app.dependency_overrides[deps.get_config] = lambda: _server_config(
            access_password="required"
        )

        resp = client.post(
            "/api/v1/documents/upload",
            files={"file": ("demo.pdf", b"%PDF-1.4 demo", "application/pdf")},
        )

        assert resp.status_code == 200
        assert resp.json()["code"] == 401

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

        app.dependency_overrides[deps.get_config] = lambda: _server_config(
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

        app.dependency_overrides[deps.get_config] = lambda: _server_config(
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

        app.dependency_overrides[deps.get_config] = lambda: _server_config(
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

        app.dependency_overrides[deps.get_config] = lambda: _server_config(
            pdf_dir=str(tmp_path)
        )

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

        app.dependency_overrides[deps.get_config] = lambda: _server_config(
            pdf_dir=str(tmp_path)
        )

        resp = client.get("/api/v1/documents/DG_EN1992-1-1__-1-2/file")

        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/pdf"
        assert resp.content.startswith(b"%PDF")

    def test_get_document_file_resolves_pdf_name_aliases(self, client, tmp_path: Path):
        pdf_path = tmp_path / "EN1992-1-1_2004.pdf"
        doc = fitz.open()
        doc.new_page()
        doc.save(pdf_path)
        doc.close()

        app.dependency_overrides[deps.get_config] = lambda: _server_config(
            pdf_dir=str(tmp_path)
        )

        for doc_id in ("EN1992-1-1_2004.pdf", "EN1992-1-1_2004_pdf"):
            resp = client.get(f"/api/v1/documents/{doc_id}/file")

            assert resp.status_code == 200
            assert resp.headers["content-type"] == "application/pdf"
            assert resp.content.startswith(b"%PDF")

    def test_get_document_file_returns_404_code_when_missing(
        self, client, tmp_path: Path
    ):
        app.dependency_overrides[deps.get_config] = lambda: _server_config(
            pdf_dir=str(tmp_path)
        )

        resp = client.get("/api/v1/documents/EN1990_2002/file")

        assert resp.status_code == 200
        assert resp.json()["code"] == 404
        assert resp.json()["message"] == "Document EN1990_2002 not found"

    def test_get_document_file_returns_404_code_when_path_is_directory(
        self, client, tmp_path: Path
    ):
        (tmp_path / "EN1990_2002.pdf").mkdir()
        app.dependency_overrides[deps.get_config] = lambda: _server_config(
            pdf_dir=str(tmp_path)
        )

        resp = client.get("/api/v1/documents/EN1990_2002/file")

        assert resp.status_code == 200
        assert resp.json()["code"] == 404
        assert resp.json()["message"] == "Document EN1990_2002 not found"

    def test_delete_document_removes_current_and_legacy_index_sources(
        self, client, tmp_path: Path
    ):
        doc_id = "DG_EN1992-1-1__-1-2"
        pdf_dir = tmp_path / "pdfs"
        parsed_dir = tmp_path / "parsed"
        pdf_dir.mkdir()
        (parsed_dir / doc_id).mkdir(parents=True)
        (pdf_dir / f"{doc_id}.pdf").write_bytes(b"%PDF-1.4 demo")
        app.dependency_overrides[deps.get_config] = lambda: _server_config(
            pdf_dir=str(pdf_dir),
            parsed_dir=str(parsed_dir),
            access_password="",
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

    def test_parse_document_contract_enqueues_doc_with_camel_case_payload(
        self, client, tmp_path: Path
    ):
        pdf_dir = tmp_path / "pdfs"
        source_pdf = tmp_path / "uploads" / "EN 1992-1-1.pdf"
        source_pdf.parent.mkdir()
        source_pdf.write_bytes(b"%PDF-1.4 demo")
        app.dependency_overrides[deps.get_config] = lambda: _server_config(
            pdf_dir=str(pdf_dir),
            parsed_dir=str(tmp_path / "parsed"),
        )

        enqueued: list[str] = []

        class _FakeTaskManager(_FakeTaskManagerBase):
            def get_status(self, doc_id):
                return None

            def enqueue(self, doc_id):
                enqueued.append(doc_id)

        with patch(
            "server.api.v1.documents.get_task_manager",
            return_value=_FakeTaskManager(),
        ):
            resp = client.post(
                "/api/v1/documents/parse",
                json={
                    "docId": "EN_1992_1_1",
                    "fileName": "EN 1992-1-1.pdf",
                    "minioPath": str(source_pdf),
                },
            )

        assert resp.status_code == 200
        assert resp.json() == {
            "code": 200,
            "docId": "EN_1992_1_1",
            "status": "processing",
            "message": "已加入解析队列",
        }
        assert enqueued == ["EN_1992_1_1"]
        assert (pdf_dir / "EN_1992_1_1.pdf").is_file()
        parse_options = json.loads(
            (tmp_path / "parsed" / "EN_1992_1_1" / "parse_options.json").read_text(
                encoding="utf-8"
            )
        )
        assert parse_options["context_summary_enabled"] is True
        assert parse_options["minio_path"] == str(source_pdf)

    def test_parse_document_contract_downloads_from_minio_path(
        self, client, tmp_path: Path
    ):
        pdf_dir = tmp_path / "pdfs"
        app.dependency_overrides[deps.get_config] = lambda: _server_config(
            pdf_dir=str(pdf_dir),
            parsed_dir=str(tmp_path / "parsed"),
            minio_endpoint="127.0.0.1:9000",
            minio_access_key="access",
            minio_secret_key="secret",
        )

        enqueued: list[str] = []

        class _FakeTaskManager(_FakeTaskManagerBase):
            def get_status(self, doc_id):
                return None

            def enqueue(self, doc_id):
                enqueued.append(doc_id)

        def fake_download_pdf_from_minio(*, minio_path, destination, config):
            assert minio_path == "eurocode/uploads/EN_1992_1_1.pdf"
            assert config.minio_endpoint == "127.0.0.1:9000"
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(b"%PDF-1.4 from minio")

        with (
            patch(
                "server.api.v1.documents.get_task_manager",
                return_value=_FakeTaskManager(),
            ),
            patch(
                "server.api.v1.documents.download_pdf_from_minio",
                fake_download_pdf_from_minio,
            ),
        ):
            resp = client.post(
                "/api/v1/documents/parse",
                json={
                    "docId": "EN_1992_1_1",
                    "fileName": "EN 1992-1-1.pdf",
                    "minioPath": "eurocode/uploads/EN_1992_1_1.pdf",
                    "contextSummaryEnabled": False,
                },
            )

        assert resp.status_code == 200
        assert resp.json()["status"] == "processing"
        assert enqueued == ["EN_1992_1_1"]
        assert (pdf_dir / "EN_1992_1_1.pdf").read_bytes().startswith(b"%PDF")
        parse_options = json.loads(
            (tmp_path / "parsed" / "EN_1992_1_1" / "parse_options.json").read_text(
                encoding="utf-8"
            )
        )
        assert parse_options["context_summary_enabled"] is False
        assert parse_options["file_name"] == "EN 1992-1-1.pdf"
        assert parse_options["minio_path"] == "eurocode/uploads/EN_1992_1_1.pdf"

    def test_get_document_file_downloads_missing_pdf_from_minio(
        self, client, tmp_path: Path
    ):
        pdf_dir = tmp_path / "pdfs"
        parsed_doc = tmp_path / "parsed" / "EN_1992_1_1"
        parsed_doc.mkdir(parents=True)
        (parsed_doc / "parse_options.json").write_text(
            json.dumps(
                {
                    "file_name": "EN 1992-1-1.pdf",
                    "minio_path": "eurocode/uploads/EN_1992_1_1.pdf",
                }
            ),
            encoding="utf-8",
        )
        app.dependency_overrides[deps.get_config] = lambda: _server_config(
            pdf_dir=str(pdf_dir),
            parsed_dir=str(tmp_path / "parsed"),
            minio_endpoint="127.0.0.1:9000",
        )
        downloaded: list[dict[str, object]] = []

        def fake_download_pdf_from_minio(*, minio_path, destination, config):
            downloaded.append(
                {
                    "minio_path": minio_path,
                    "destination": destination,
                    "endpoint": config.minio_endpoint,
                }
            )
            doc = fitz.open()
            doc.new_page()
            destination.parent.mkdir(parents=True, exist_ok=True)
            doc.save(destination)
            doc.close()

        with patch(
            "server.api.v1.documents.download_pdf_from_minio",
            fake_download_pdf_from_minio,
        ):
            resp = client.get("/api/v1/documents/EN_1992_1_1/file")

        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/pdf"
        assert resp.content.startswith(b"%PDF")
        assert downloaded == [
            {
                "minio_path": "eurocode/uploads/EN_1992_1_1.pdf",
                "destination": pdf_dir / "EN_1992_1_1.pdf",
                "endpoint": "127.0.0.1:9000",
            }
        ]
        assert (pdf_dir / "EN_1992_1_1.pdf").is_file()

    def test_upload_to_minio_uploads_pdf_and_triggers_parse(
        self, client, tmp_path: Path
    ):
        pdf_dir = tmp_path / "pdfs"
        app.dependency_overrides[deps.get_config] = lambda: _server_config(
            pdf_dir=str(pdf_dir),
            parsed_dir=str(tmp_path / "parsed"),
            minio_endpoint="127.0.0.1:9000",
            minio_access_key="access",
            minio_secret_key="secret",
        )

        enqueued: list[str] = []
        uploaded: list[dict[str, object]] = []

        class _FakeTaskManager(_FakeTaskManagerBase):
            def get_status(self, doc_id):
                return None

            def enqueue(self, doc_id):
                enqueued.append(doc_id)

        def fake_upload_pdf_to_minio(*, bucket, object_name, content, config):
            uploaded.append(
                {
                    "bucket": bucket,
                    "object_name": object_name,
                    "content": content,
                    "endpoint": config.minio_endpoint,
                }
            )
            return f"{bucket}/{object_name}"

        def fake_download_pdf_from_minio(*, minio_path, destination, config):
            assert minio_path == "eurocode/uploads/EN_1992-1-1.pdf"
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(b"%PDF-1.4 from minio")

        with (
            patch(
                "server.api.v1.documents.get_task_manager",
                return_value=_FakeTaskManager(),
            ),
            patch(
                "server.api.v1.documents.upload_pdf_to_minio",
                fake_upload_pdf_to_minio,
            ),
            patch(
                "server.api.v1.documents.download_pdf_from_minio",
                fake_download_pdf_from_minio,
            ),
        ):
            resp = client.post(
                "/api/v1/documents/upload-to-minio",
                data={"contextSummaryEnabled": "false"},
                files={
                    "file": (
                        "EN 1992-1-1.pdf",
                        b"%PDF-1.4 demo",
                        "application/pdf",
                    )
                },
            )

        assert resp.status_code == 200
        assert resp.json() == {
            "code": 200,
            "docId": "EN_1992-1-1",
            "fileName": "EN 1992-1-1.pdf",
            "minioPath": "eurocode/uploads/EN_1992-1-1.pdf",
            "status": "processing",
            "message": "已加入解析队列",
        }
        assert uploaded == [
            {
                "bucket": "eurocode",
                "object_name": "uploads/EN_1992-1-1.pdf",
                "content": b"%PDF-1.4 demo",
                "endpoint": "127.0.0.1:9000",
            }
        ]
        assert enqueued == ["EN_1992-1-1"]
        assert (pdf_dir / "EN_1992-1-1.pdf").read_bytes().startswith(b"%PDF")
        parse_options = json.loads(
            (tmp_path / "parsed" / "EN_1992-1-1" / "parse_options.json").read_text(
                encoding="utf-8"
            )
        )
        assert parse_options["context_summary_enabled"] is False

    def test_upload_to_minio_rejects_non_pdf(self, client):
        resp = client.post(
            "/api/v1/documents/upload-to-minio",
            files={"file": ("readme.txt", b"hello", "text/plain")},
        )

        assert resp.status_code == 200
        assert resp.json() == {
            "code": 400,
            "message": "只接受 PDF 文件",
            "detail": None,
        }

    def test_batch_document_status_contract_returns_camel_case_fields(
        self, client, tmp_path: Path
    ):
        parsed_doc_dir = tmp_path / "parsed" / "EN_1990_2002"
        parsed_doc_dir.mkdir(parents=True)
        (parsed_doc_dir / ".indexed").write_text(
            json.dumps({"milvus": 1542, "elasticsearch": 1542}),
            encoding="utf-8",
        )
        app.dependency_overrides[deps.get_config] = lambda: _server_config(
            parsed_dir=str(tmp_path / "parsed"),
            pdf_dir=str(tmp_path / "pdfs"),
            es_url="http://127.0.0.1:1",
        )

        resp = client.post(
            "/api/v1/documents/status",
            json={"docIds": ["EN_1990_2002"]},
        )

        assert resp.status_code == 200
        assert resp.json() == {
            "code": 200,
            "results": [
                {
                    "docId": "EN_1990_2002",
                    "status": "success",
                    "progress": 1.0,
                    "stage": "ready",
                    "message": "解析完成",
                    "chunkCount": 1542,
                    "error": None,
                }
            ],
        }

    def test_batch_document_status_returns_not_found_for_missing_document(
        self, client, tmp_path: Path
    ):
        app.dependency_overrides[deps.get_config] = lambda: _server_config(
            parsed_dir=str(tmp_path / "parsed"),
            pdf_dir=str(tmp_path / "pdfs"),
            es_url="http://127.0.0.1:1",
        )

        resp = client.post(
            "/api/v1/documents/status",
            json={"docIds": ["MISSING_DOC"]},
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 200
        result = body["results"][0]
        assert result["docId"] == "MISSING_DOC"
        assert result["status"] == "not_found"
        assert result["progress"] == 0.0
        assert result["stage"] == "not_found"
        assert result["message"] == "文档不存在或尚未上传"
        assert result["chunkCount"] is None
        assert result["error"]["type"] == "NOT_FOUND"
        assert result["error"]["detail"] == "文档不存在或尚未上传"
        assert result["error"]["stage"] == "not_found"

    def test_batch_document_status_reads_persisted_error_state(
        self, client, tmp_path: Path
    ):
        doc_id = "DOC_STALE"
        parsed_doc_dir = tmp_path / "parsed" / doc_id
        parsed_doc_dir.mkdir(parents=True)
        (parsed_doc_dir / "status.json").write_text(
            json.dumps(
                {
                    "doc_id": doc_id,
                    "stage": "error",
                    "progress": 1.0,
                    "message": "服务重启导致解析中断,请重试",
                    "error": "服务重启导致解析中断,请重试",
                    "attempts": 2,
                    "created_at": "2026-05-29T00:00:00Z",
                    "updated_at": "2026-05-29T00:01:00Z",
                    "heartbeat_at": "2026-05-29T00:01:00Z",
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        app.dependency_overrides[deps.get_config] = lambda: _server_config(
            parsed_dir=str(tmp_path / "parsed"),
            pdf_dir=str(tmp_path / "pdfs"),
            es_url="http://127.0.0.1:1",
        )

        resp = client.post(
            "/api/v1/documents/status",
            json={"docIds": [doc_id]},
        )

        assert resp.status_code == 200
        result = resp.json()["results"][0]
        assert result["status"] == "failed"
        assert result["stage"] == "error"
        assert result["message"] == "服务重启导致解析中断,请重试"
        assert result["error"]["detail"] == "服务重启导致解析中断,请重试"

    def test_batch_document_status_prefers_index_marker_over_stale_status_json(
        self, client, tmp_path: Path
    ):
        doc_id = "DOC_READY"
        parsed_doc_dir = tmp_path / "parsed" / doc_id
        parsed_doc_dir.mkdir(parents=True)
        (parsed_doc_dir / "status.json").write_text(
            json.dumps(
                {
                    "doc_id": doc_id,
                    "stage": "indexing",
                    "progress": 0.88,
                    "message": "正在写入索引",
                    "error": None,
                    "attempts": 1,
                    "created_at": "2026-05-29T00:00:00Z",
                    "updated_at": "2026-05-29T00:01:00Z",
                    "heartbeat_at": "2026-05-29T00:01:00Z",
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        (parsed_doc_dir / ".indexed").write_text(
            json.dumps({"milvus": 7, "elasticsearch": 7}),
            encoding="utf-8",
        )
        app.dependency_overrides[deps.get_config] = lambda: _server_config(
            parsed_dir=str(tmp_path / "parsed"),
            pdf_dir=str(tmp_path / "pdfs"),
            es_url="http://127.0.0.1:1",
        )

        resp = client.post(
            "/api/v1/documents/status",
            json={"docIds": [doc_id]},
        )

        assert resp.status_code == 200
        result = resp.json()["results"][0]
        assert result["status"] == "success"
        assert result["stage"] == "ready"
        assert result["progress"] == 1.0
        assert result["chunkCount"] == 7

    def test_batch_delete_documents_contract_is_summary_and_mocked(
        self, client, tmp_path: Path
    ):
        doc_id = "EN_1992_1_1"
        pdf_dir = tmp_path / "pdfs"
        parsed_dir = tmp_path / "parsed"
        pdf_dir.mkdir()
        (parsed_dir / doc_id).mkdir(parents=True)
        (pdf_dir / f"{doc_id}.pdf").write_bytes(b"%PDF-1.4 demo")
        app.dependency_overrides[deps.get_config] = lambda: _server_config(
            pdf_dir=str(pdf_dir),
            parsed_dir=str(parsed_dir),
            access_password="",
        )

        deleted_source_batches: list[list[str]] = []

        async def fake_delete_document_sources(source_names, _config):
            deleted_source_batches.append(list(source_names))
            return {"milvus": 3, "elasticsearch": 4}

        with (
            patch(
                "pipeline.index.delete_document_sources",
                fake_delete_document_sources,
            ),
            patch(
                "server.api.v1.documents.invalidate_retriever_cache",
                AsyncMock(),
            ),
        ):
            resp = client.post(
                "/api/v1/documents/delete",
                json={"docIds": [doc_id, "MISSING_DOC"]},
            )

        assert resp.status_code == 200
        assert resp.json() == {
            "code": 200,
            "deleted": True,
            "deletedChunks": {"milvus": 3, "elasticsearch": 4},
        }
        assert deleted_source_batches == [
            [
                doc_id,
                doc_id.replace("_", " "),
                "MISSING_DOC",
                "MISSING DOC",
            ],
        ]

    def test_batch_delete_documents_returns_500_code_when_bulk_delete_fails(
        self, client, tmp_path: Path
    ):
        app.dependency_overrides[deps.get_config] = lambda: _server_config(
            pdf_dir=str(tmp_path / "pdfs"),
            parsed_dir=str(tmp_path / "parsed"),
            access_password="",
        )

        async def fake_delete_document_sources(source_names, _config):
            raise RuntimeError("backend exploded")

        with (
            patch(
                "pipeline.index.delete_document_sources",
                fake_delete_document_sources,
            ),
            patch(
                "server.api.v1.documents.invalidate_retriever_cache",
                AsyncMock(),
            ),
        ):
            resp = client.post(
                "/api/v1/documents/delete",
                json={"docIds": ["OK_DOC", "BROKEN_DOC", "OK_DOC_2"]},
            )

        assert resp.status_code == 200
        assert resp.json() == {
            "code": 500,
            "message": "文档删除失败",
            "detail": None,
        }

    def test_batch_delete_documents_returns_404_code_when_no_chunks_deleted(
        self, client, tmp_path: Path
    ):
        app.dependency_overrides[deps.get_config] = lambda: _server_config(
            pdf_dir=str(tmp_path / "pdfs"),
            parsed_dir=str(tmp_path / "parsed"),
            access_password="",
        )

        async def fake_delete_document_sources(source_names, _config):
            return {"milvus": 0, "elasticsearch": 0}

        with (
            patch(
                "pipeline.index.delete_document_sources",
                fake_delete_document_sources,
            ),
            patch(
                "server.api.v1.documents.invalidate_retriever_cache",
                AsyncMock(),
            ),
        ):
            resp = client.post(
                "/api/v1/documents/delete",
                json={"docIds": ["MISSING_DOC"]},
            )

        assert resp.status_code == 200
        assert resp.json() == {
            "code": 404,
            "message": "文档不存在",
            "detail": None,
        }

    def test_batch_delete_documents_rejects_active_document_before_delete(
        self, client, tmp_path: Path
    ):
        app.dependency_overrides[deps.get_config] = lambda: _server_config(
            pdf_dir=str(tmp_path / "pdfs"),
            parsed_dir=str(tmp_path / "parsed"),
            access_password="",
        )

        delete_call = AsyncMock(return_value={"milvus": 3, "elasticsearch": 4})

        class _FakeTaskManager(_FakeTaskManagerBase):
            def get_status(self, doc_id):
                if doc_id == "ACTIVE_DOC":
                    return SimpleNamespace(stage="indexing")
                return None

        with (
            patch(
                "server.api.v1.documents.get_task_manager",
                return_value=_FakeTaskManager(),
            ),
            patch("pipeline.index.delete_document_sources", delete_call),
        ):
            resp = client.post(
                "/api/v1/documents/delete",
                json={"docIds": ["OK_DOC", "ACTIVE_DOC"]},
            )

        assert resp.status_code == 200
        assert resp.json() == {
            "code": 409,
            "message": "文档正在解析中，无法删除: ACTIVE_DOC",
            "detail": None,
        }
        delete_call.assert_not_awaited()


class TestSourcesEndpoint:
    def test_public_translate_contract_bypasses_auth_when_password_enabled(
        self, client
    ):
        translated_source = SimpleNamespace(translation="应规定设计使用年限。")
        app.dependency_overrides[deps.get_config] = lambda: _server_config(
            access_password="required"
        )

        with patch(
            "server.api.v1.sources._fill_missing_source_translations",
            AsyncMock(return_value=[translated_source]),
        ):
            resp = client.post(
                "/api/v1/translate",
                json={"text": "The design working life should be specified."},
            )

        assert resp.status_code == 200
        assert resp.json()["translation"] == "应规定设计使用年限。"

    def test_internal_source_translate_still_requires_auth_when_password_enabled(
        self,
        client,
    ):
        app.dependency_overrides[deps.get_config] = lambda: _server_config(
            access_password="required"
        )
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

        resp = client.post("/api/v1/sources/translate", json=payload)

        assert resp.status_code == 200
        assert resp.json()["code"] == 401

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

        assert resp.status_code == 200
        assert resp.json()["code"] == 400
        assert resp.json()["message"] == "参数错误"

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

        assert resp.status_code == 200
        assert resp.json() == {
            "code": 502,
            "message": "Source translation unavailable",
            "detail": None,
        }

    def test_translate_source_returns_http_error_when_translation_empty(self, client):
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

        assert resp.status_code == 200
        assert resp.json() == {
            "code": 502,
            "message": "Source translation unavailable",
            "detail": None,
        }

    def test_translate_text_contract_returns_code_and_translation(self, client):
        translated_source = SimpleNamespace(translation="应规定设计使用年限。")

        with patch(
            "server.api.v1.sources._fill_missing_source_translations",
            AsyncMock(return_value=[translated_source]),
        ) as mock_translate:
            resp = client.post(
                "/api/v1/translate",
                json={
                    "text": "The design working life should be specified.",
                    "context": {
                        "documentId": "EN_1990_2002",
                        "title": "Eurocode - Basis of structural design",
                        "section": "Section 2 Requirements > 2.3 Design working life",
                        "clause": "2.3(1)",
                    },
                },
            )

        assert resp.status_code == 200
        assert resp.json() == {"code": 200, "translation": "应规定设计使用年限。"}
        [sent_sources, _sent_config] = mock_translate.await_args.args
        assert sent_sources[0].document_id == "EN_1990_2002"
        assert (
            sent_sources[0].original_text
            == "The design working life should be specified."
        )


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
