from __future__ import annotations

from server.config import ServerConfig
from server.core.evidence_guard import EvidenceMatcher, EvidenceRequirement
from server.core.generation.evidence_selection import select_generation_evidence
from server.models.schemas import Chunk, ChunkMetadata, ElementType


def _chunk(
    chunk_id: str,
    content: str,
    *,
    element_type: ElementType = ElementType.TEXT,
    object_label: str = "",
    clause_ids: list[str] | None = None,
) -> Chunk:
    return Chunk(
        chunk_id=chunk_id,
        content=content,
        embedding_text=content,
        metadata=ChunkMetadata(
            source="EN 1992-1-1",
            source_title="Eurocode 2",
            section_path=["Section"],
            page_numbers=[1],
            page_file_index=[0],
            clause_ids=clause_ids or [],
            element_type=element_type,
            object_label=object_label,
        ),
    )


def test_select_generation_evidence_preserves_required_chunk_over_budget():
    required = _chunk(
        "required-table",
        "Table 2.1N: concrete 1.5 steel 1.15 " * 200,
        element_type=ElementType.TABLE,
        object_label="Table 2.1N",
    )
    filler = _chunk("filler", "irrelevant filler " * 200)
    selected = select_generation_evidence(
        chunks=[filler],
        parent_chunks=[],
        ref_chunks=[required],
        scores=[0.1],
        required_evidence=[
            EvidenceRequirement(
                id="material_factor",
                label="material factors",
                any_of=[EvidenceMatcher(object_label_contains=["Table 2.1N"])],
            )
        ],
        config=ServerConfig(generation_context_token_budget=1),
    )

    assert [chunk.chunk_id for chunk in selected.ref_chunks] == ["required-table"]
    assert selected.chunks == []


def test_select_generation_evidence_trims_low_priority_context():
    main = _chunk("main", "short main evidence", clause_ids=["6.1"])
    parent = _chunk("parent", "parent context " * 1000)
    guide = _chunk("guide", "guide context " * 1000)
    selected = select_generation_evidence(
        chunks=[main],
        parent_chunks=[parent],
        guide_chunks=[guide],
        scores=[0.9],
        config=ServerConfig(generation_context_token_budget=20),
    )

    assert [chunk.chunk_id for chunk in selected.chunks] == ["main"]
    assert selected.parent_chunks == []
    assert selected.guide_chunks == []
    assert selected.scores == [0.9]


def test_select_generation_evidence_keeps_scores_aligned_with_selected_chunks():
    first = _chunk("first", "first evidence")
    second = _chunk("second", "second evidence " * 500)
    selected = select_generation_evidence(
        chunks=[first, second],
        parent_chunks=[],
        scores=[0.8, 0.7],
        config=ServerConfig(generation_context_token_budget=20),
    )

    assert [chunk.chunk_id for chunk in selected.chunks] == ["first"]
    assert selected.scores == [0.8]


def test_select_generation_evidence_protects_one_best_chunk_per_requirement():
    table = _chunk(
        "table",
        "Table 2.1N concrete 1.5",
        element_type=ElementType.TABLE,
        object_label="Table 2.1N",
    )
    text = _chunk(
        "text",
        "Concrete partial factor 1.5 " * 500,
        clause_ids=["2.4.2.4"],
    )
    selected = select_generation_evidence(
        chunks=[text],
        parent_chunks=[],
        ref_chunks=[table],
        scores=[0.9],
        required_evidence=[
            EvidenceRequirement(
                id="material_factor",
                label="material factor",
                any_of=[EvidenceMatcher(content_contains=["concrete", "1.5"])],
            )
        ],
        config=ServerConfig(generation_context_token_budget=1),
    )

    assert [chunk.chunk_id for chunk in selected.ref_chunks] == ["table"]
    assert selected.chunks == []
