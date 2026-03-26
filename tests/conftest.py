"""Shared test fixtures."""
import pytest

from server.models.schemas import Chunk, ChunkMetadata, ElementType


@pytest.fixture
def sample_text_chunk() -> Chunk:
    return Chunk(
        chunk_id="chunk_023",
        content=(
            "2.3 Design working life\n"
            "(1) The design working life should be specified.\n"
            "NOTE Indicative categories are given in Table 2.1.\n"
            "[-> Table 2.1 - Indicative design working life]"
        ),
        embedding_text=(
            "2.3 Design working life. The design working life should be specified. "
            "Indicative categories are given in Table 2.1."
        ),
        metadata=ChunkMetadata(
            source="EN 1990:2002",
            source_title="Eurocode - Basis of structural design",
            section_path=["Section 2 Requirements", "2.3 Design working life"],
            page_numbers=[28],
            page_file_index=[27],
            clause_ids=["2.3(1)"],
            element_type=ElementType.TEXT,
            cross_refs=["Annex A"],
            parent_chunk_id="chunk_section_2",
        ),
    )


@pytest.fixture
def sample_table_chunk() -> Chunk:
    return Chunk(
        chunk_id="chunk_t_2_1",
        content=(
            "Table 2.1 - Indicative design working life\n"
            "| Category | Years | Examples |\n"
            "|1|10|Temporary structures|\n"
            "|2|10-25|Replaceable structural parts|\n"
            "|3|15-30|Agricultural and similar structures|\n"
            "|4|50|Building structures and other common structures|\n"
            "|5|100|Monumental building structures, bridges, "
            "and other civil engineering structures|"
        ),
        embedding_text=(
            "Table 2.1 design working life categories: "
            "temporary 10y, replaceable 10-25y, agricultural 15-30y, "
            "building 50y, monumental/bridges 100y. "
            "Section: 2.3 Design working life"
        ),
        metadata=ChunkMetadata(
            source="EN 1990:2002",
            source_title="Eurocode - Basis of structural design",
            section_path=["Section 2 Requirements", "2.3 Design working life"],
            page_numbers=[28],
            page_file_index=[27],
            clause_ids=["Table 2.1"],
            element_type=ElementType.TABLE,
            cross_refs=[],
            parent_text_chunk_id="chunk_023",
        ),
    )
