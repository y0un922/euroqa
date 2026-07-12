from __future__ import annotations

from types import SimpleNamespace

from server.agents.deps import QADeps
from server.agents.evidence import EvidenceBundle
from server.agents.qa_agent import (
    _QA_AGENT_INSTRUCTIONS,
    _agent_model_extra_body,
    _build_input_items,
    _drop_empty_messages_between_tool_call_and_output,
    _raw_response_text_delta,
    build_qa_agent,
)
from server.config import ServerConfig
from server.core.conversation import ConversationState
from server.core.retrieval import RetrievalResult
from server.models.schemas import Chunk, ChunkMetadata, ElementType


def _make_chunk(chunk_id: str, content: str = "Design evidence") -> Chunk:
    return Chunk(
        chunk_id=chunk_id,
        content=content,
        embedding_text=content,
        metadata=ChunkMetadata(
            source="EN 1992-1-1",
            document_id="EN1992",
            source_title="EN 1992-1-1",
            display_title="EN 1992-1-1",
            section_path=["1", "1.1"],
            page_numbers=[1],
            page_file_index=[0],
            clause_ids=["1.1"],
            element_type=ElementType.TEXT,
        ),
    )


def test_qa_agent_exposes_only_lookup_tools():
    agent = build_qa_agent(ServerConfig())
    tool_names = {getattr(tool, "name", "") for tool in agent.tools}

    assert tool_names == {"search", "lookup_object"}


def test_agent_model_extra_body_uses_provider_specific_thinking_switch():
    deepseek_config = ServerConfig(
        agent_llm_base_url="https://api.deepseek.com/v1",
        agent_llm_model="deepseek-v4-pro",
        llm_enable_thinking=False,
    )
    qwen_config = ServerConfig(
        agent_llm_base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        agent_llm_model="qwen3.6-flash",
        llm_enable_thinking=False,
    )

    assert _agent_model_extra_body(deepseek_config) == {
        "thinking": {"type": "disabled"}
    }
    assert _agent_model_extra_body(qwen_config) == {"enable_thinking": False}


def test_qa_agent_instructions_use_prefetched_evidence_contract():
    assert "【预检索证据】" in _QA_AGENT_INSTRUCTIONS
    assert "【回答大纲】" in _QA_AGENT_INSTRUCTIONS
    assert "只能引用已出现的 [Ref-N]" in _QA_AGENT_INSTRUCTIONS
    assert "不做泛化检索" in _QA_AGENT_INSTRUCTIONS
    assert "calculation_steps" in _QA_AGENT_INSTRUCTIONS
    assert "self_check" in _QA_AGENT_INSTRUCTIONS
    assert "retrieve_agentic" not in _QA_AGENT_INSTRUCTIONS
    assert "generate_answer" not in _QA_AGENT_INSTRUCTIONS


def test_build_input_items_includes_outline_after_prefetched_evidence():
    bundle = EvidenceBundle()
    chunk = _make_chunk("chunk-1", "fck is characteristic cylinder strength")
    bundle.add_retrieval(
        RetrievalResult(
            chunks=[chunk],
            parent_chunks=[],
            scores=[0.9],
            groundedness="partial",
        ),
        query="concrete strength definitions",
    )
    bundle.outline = {
        "narrative_angle": "基于 EN 1992-1-1 解释强度定义",
        "sections": [{"title": "强度定义", "bullets": ["说明 fck"], "ref_ids": ["Ref-1"]}],
        "calculation_steps": [],
        "self_check": ["只能使用已有引用"],
    }
    deps = QADeps(
        config=ServerConfig(),
        retriever=object(),
        glossary={},
        bundle=bundle,
        conversation_state=ConversationState(conversation_id="conv-1", history=[]),
    )

    input_items = _build_input_items("混凝土强度定义？", deps)

    assert input_items[-2]["content"].startswith("【预检索证据】")
    assert "[Ref-1]" in input_items[-2]["content"]
    assert input_items[-1]["content"].startswith("【回答大纲】")
    assert "强度定义" in input_items[-1]["content"]


def test_raw_response_text_delta_only_allows_final_output_text():
    output_event = SimpleNamespace(
        data=SimpleNamespace(type="response.output_text.delta", delta="最终答案")
    )
    reasoning_event = SimpleNamespace(
        data=SimpleNamespace(type="response.reasoning_summary_text.delta", delta="分析")
    )
    other_event = SimpleNamespace(
        data=SimpleNamespace(type="response.refusal.delta", delta="拒绝")
    )
    mapping_event = SimpleNamespace(
        data={"type": "response.output_text.delta", "delta": "流式答案"}
    )

    assert _raw_response_text_delta(output_event) == "最终答案"
    assert _raw_response_text_delta(mapping_event) == "流式答案"
    assert _raw_response_text_delta(reasoning_event) == ""
    assert _raw_response_text_delta(other_event) == ""


def test_drop_empty_message_between_tool_call_and_tool_output():
    tool_call = {"type": "function_call", "call_id": "call-1"}
    empty_message = {
        "type": "message",
        "role": "assistant",
        "content": [{"type": "output_text", "text": ""}],
    }
    tool_output = {
        "type": "function_call_output",
        "call_id": "call-1",
        "output": "result",
    }

    filtered = _drop_empty_messages_between_tool_call_and_output(
        ["question", tool_call, empty_message, tool_output]
    )

    assert filtered == ["question", tool_call, tool_output]


def test_drop_empty_message_keeps_real_or_unrelated_assistant_messages():
    tool_call = {"type": "function_call", "call_id": "call-1"}
    real_message = {
        "type": "message",
        "role": "assistant",
        "content": [{"type": "output_text", "text": "visible"}],
    }
    empty_message = {
        "type": "message",
        "role": "assistant",
        "content": [{"type": "output_text", "text": ""}],
    }
    tool_output = {
        "type": "function_call_output",
        "call_id": "call-1",
        "output": "result",
    }

    assert _drop_empty_messages_between_tool_call_and_output(
        [tool_call, real_message, tool_output]
    ) == [tool_call, real_message, tool_output]
    assert _drop_empty_messages_between_tool_call_and_output(
        [empty_message, tool_call, tool_output]
    ) == [empty_message, tool_call, tool_output]


def test_evidence_bundle_keeps_scores_aligned_and_assigns_refs():
    first = _make_chunk("chunk-1", "first")
    duplicate = _make_chunk("chunk-1", "duplicate")
    second = _make_chunk("chunk-2", "second")
    bundle = EvidenceBundle()

    bundle.add_retrieval(
        RetrievalResult(
            chunks=[first],
            parent_chunks=[],
            scores=[0.9],
            groundedness="partial",
        ),
        query="first query",
    )
    bundle.add_retrieval(
        RetrievalResult(
            chunks=[duplicate, second],
            parent_chunks=[],
            scores=[0.1, 0.8],
            groundedness="partial",
        ),
        query="second query",
    )

    assert [chunk.chunk_id for chunk in bundle.chunks] == ["chunk-1", "chunk-2"]
    assert bundle.scores == [0.9, 0.8]
    assert bundle.ref_label_for(first) == "Ref-1"
    assert bundle.ref_label_for(second) == "Ref-2"
    assert bundle.retrieval_attempts[-1]["query"] == "second query"
