from __future__ import annotations

from types import SimpleNamespace

from server.agents.evidence import EvidenceBundle
from server.agents.orchestrator import AgentResult
from server.models.schemas import Chunk, ChunkMetadata, ElementType


def _make_chunk(chunk_id: str = "chunk-1") -> Chunk:
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


def test_agent_result_needs_rag_when_bundle_has_chunks():
    bundle = EvidenceBundle(chunks=[_make_chunk()])
    result = AgentResult(
        agent_reply="已检索到相关规范证据。",
        bundle=bundle,
        conv=SimpleNamespace(conversation_id="conv-1"),
        deps=None,
    )

    assert bundle.has_rag_evidence
    assert result.needs_rag


def test_agent_result_uses_direct_reply_when_bundle_has_no_rag_evidence():
    bundle = EvidenceBundle()
    bundle.tool_trace.append({"tool": "retrieve", "chunk_count": 0})
    result = AgentResult(
        agent_reply="暂未找到相关规范条文，请补充规范号或构件类型。",
        bundle=bundle,
        conv=SimpleNamespace(conversation_id="conv-1"),
        deps=None,
    )

    assert not bundle.has_rag_evidence
    assert not result.needs_rag
