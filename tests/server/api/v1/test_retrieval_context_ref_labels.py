from __future__ import annotations

from server.agents.evidence import EvidenceBundle
from server.api.v1._response import _retrieval_context_from_bundle
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


def test_ref_labels_export_preserves_exposure_order():
    # Round 1: chunk A and parent P get exposed -> Ref-1, Ref-2.
    bundle = EvidenceBundle(
        chunks=[_make_chunk("A")],
        parent_chunks=[_make_chunk("P")],
    )
    bundle.ensure_ref_ids(bundle.citable_chunks())
    # Round 2: chunk B arrives after P was already labeled -> Ref-3, even though
    # category order (chunks -> parent) would place B before P.
    bundle.chunks.append(_make_chunk("B"))
    bundle.ensure_ref_ids(bundle.citable_chunks())

    ctx = _retrieval_context_from_bundle(bundle)

    assert ctx.ref_labels == {"A": "Ref-1", "P": "Ref-2", "B": "Ref-3"}
    category_order = [item["chunk_id"] for item in ctx.chunks] + [
        item["chunk_id"] for item in ctx.parent_chunks
    ]
    assert category_order == ["A", "B", "P"]  # differs from ref order by design


def test_ref_labels_assigned_even_without_prior_sources_call():
    bundle = EvidenceBundle(chunks=[_make_chunk("A"), _make_chunk("B")])

    ctx = _retrieval_context_from_bundle(bundle)

    assert ctx.ref_labels == {"A": "Ref-1", "B": "Ref-2"}
