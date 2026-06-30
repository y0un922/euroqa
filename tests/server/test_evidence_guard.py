"""Tests for retrieval evidence guard matching."""

from server.core.evidence_guard import (
    EvidenceMatcher,
    EvidenceRequirement,
    evaluate_evidence_requirements,
)
from server.models.schemas import Chunk, ChunkMetadata, ElementType


def _make_chunk(
    chunk_id: str,
    content: str,
    *,
    source: str = "EN 1992-1-1:2004",
    source_title: str = "Eurocode 2",
    section_path: list[str] | None = None,
    clause_ids: list[str] | None = None,
    element_type: ElementType = ElementType.TEXT,
    object_label: str = "",
    object_type: str | None = None,
    object_aliases: list[str] | None = None,
) -> Chunk:
    return Chunk(
        chunk_id=chunk_id,
        content=content,
        embedding_text=content,
        metadata=ChunkMetadata(
            source=source,
            source_title=source_title,
            section_path=section_path or ["2", "Basis of design"],
            page_numbers=[20],
            page_file_index=[19],
            clause_ids=clause_ids or [],
            element_type=element_type,
            object_label=object_label,
            object_type=object_type,
            object_aliases=object_aliases or [],
        ),
    )


def test_contains_semantics_distinguish_metadata_any_and_content_all():
    chunk = _make_chunk(
        "mat-table",
        "Table 2.1N: γC for concrete is 1.5.",
        object_label="Table 2.1N",
    )
    requirement = EvidenceRequirement(
        id="material",
        label="material factors",
        any_of=[
            EvidenceMatcher(
                source_contains=["EN1992", "EN 1992"],
                object_label_contains=["Table 2.1N"],
                content_contains=["γC", "1.15"],
            )
        ],
    )

    result = evaluate_evidence_requirements([chunk], [requirement])

    assert result.passed is False
    assert result.matched_chunk_ids_by_requirement["material"] == []
    assert result.retry_note is not None


def test_requirement_any_of_allows_split_precise_matchers():
    chunk = _make_chunk(
        "mat-table",
        "Table 2.1N: γC for concrete is 1.5.",
        object_label="Table 2.1N",
    )
    requirement = EvidenceRequirement(
        id="material",
        label="material factors",
        any_of=[
            EvidenceMatcher(content_contains=["γS", "1.15"]),
            EvidenceMatcher(
                source_contains=["EN1992", "EN 1992"],
                object_label_contains=["Table 2.1N"],
            ),
        ],
    )

    result = evaluate_evidence_requirements([chunk], [requirement])

    assert result.passed is True
    assert result.matched_chunk_ids_by_requirement["material"] == ["mat-table"]
    assert result.retry_note is None


def test_source_contains_uses_any_variant_and_compact_matching():
    chunk = _make_chunk(
        "action-table",
        "Table A1.2(B): permanent actions γG = 1.35.",
        source="EN 1990:2002",
        source_title="Eurocode - Basis of structural design",
        object_label="Table A1.2(B)",
    )
    requirement = EvidenceRequirement(
        id="permanent_action",
        label="permanent action factor",
        any_of=[
            EvidenceMatcher(
                source_contains=["EN1990", "EN 1990"],
                object_label_contains=["Table A1.2(B)"],
            )
        ],
    )

    result = evaluate_evidence_requirements([chunk], [requirement])

    assert result.passed is True
    assert result.to_trace()["missing_required"] == []


def test_content_contains_accepts_decimal_comma_values():
    chunk = _make_chunk(
        "mat-table",
        "Table 2.1N: γC for concrete is 1,5 and γS is 1,15.",
    )
    requirement = EvidenceRequirement(
        id="concrete_factor",
        label="concrete factor",
        any_of=[EvidenceMatcher(content_contains=["γC", "1.5"])],
    )

    result = evaluate_evidence_requirements([chunk], [requirement])

    assert result.passed is True
    assert result.matched_chunk_ids_by_requirement["concrete_factor"] == ["mat-table"]


def test_optional_requirement_does_not_fail_guard():
    chunk = _make_chunk("text", "Unrelated evidence.")
    requirement = EvidenceRequirement(
        id="optional",
        label="optional evidence",
        required=False,
        any_of=[EvidenceMatcher(content_contains=["not present"])],
    )

    result = evaluate_evidence_requirements([chunk], [requirement])

    assert result.passed is True
    assert result.matched_chunk_ids_by_requirement["optional"] == []
