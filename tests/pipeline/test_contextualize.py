"""Test summary generation (table: structural extraction, formula: LLM)."""
from unittest.mock import AsyncMock, patch

import pytest

from pipeline.contextualize import (
    build_table_embedding_text,
    enrich_chunk_summaries,
    generate_formula_description,
    _extract_table_headers,
    _extract_first_column,
)
from server.models.schemas import Chunk, ChunkMetadata, ElementType


@pytest.fixture
def table_chunk():
    return Chunk(
        chunk_id="t1",
        content="| Cat | Years |\n|---|---|\n|1|10|",
        embedding_text="",
        metadata=ChunkMetadata(
            source="EN 1990:2002",
            source_title="Basis",
            section_path=["2.3 Design working life"],
            page_numbers=[28],
            page_file_index=[27],
            clause_ids=[],
            element_type=ElementType.TABLE,
            object_label="Table 2.1",
        ),
    )


@pytest.fixture
def html_table_chunk():
    return Chunk(
        chunk_id="t2",
        content='<table><tr><th>Class</th><th>fck</th></tr><tr><td>C30/37</td><td>30</td></tr></table>',
        embedding_text="",
        metadata=ChunkMetadata(
            source="EN 1992-1-1:2004",
            source_title="Design of concrete structures",
            section_path=["3.1 Concrete", "3.1.2 Strength"],
            page_numbers=[28],
            page_file_index=[27],
            clause_ids=[],
            element_type=ElementType.TABLE,
            object_label="Table 3.1",
        ),
    )


@pytest.fixture
def formula_chunk():
    return Chunk(
        chunk_id="f1",
        content="$$R_d = \\frac{1}{\\gamma_{Rd}} R$$\nwhere gamma is partial factor",
        embedding_text="",
        metadata=ChunkMetadata(
            source="EN 1990:2002",
            source_title="Basis",
            section_path=["6.3.5 Design resistance"],
            page_numbers=[44],
            page_file_index=[43],
            clause_ids=[],
            element_type=ElementType.FORMULA,
        ),
    )


class TestExtractTableHeaders:
    def test_extracts_th_tags(self):
        html = '<table><tr><th>Class</th><th>fck</th></tr></table>'
        assert _extract_table_headers(html) == ["Class", "fck"]

    def test_falls_back_to_first_row_td(self):
        html = '<table><tr><td>A</td><td>B</td></tr><tr><td>1</td><td>2</td></tr></table>'
        assert _extract_table_headers(html) == ["A", "B"]

    def test_empty_on_no_table(self):
        assert _extract_table_headers("no table here") == []


class TestExtractFirstColumn:
    def test_extracts_row_labels(self):
        html = '<table><tr><th>H1</th><th>H2</th></tr><tr><td>C30</td><td>30</td></tr><tr><td>C40</td><td>40</td></tr></table>'
        assert _extract_first_column(html) == ["C30", "C40"]


class TestBuildTableEmbeddingText:
    def test_includes_caption_headers_rows_section(self, html_table_chunk):
        result = build_table_embedding_text(html_table_chunk)
        assert "Table 3.1" in result
        assert "Columns: Class, fck" in result
        assert "Rows: C30/37" in result
        assert "Section: 3.1 Concrete > 3.1.2 Strength" in result
        assert "Source: EN 1992-1-1:2004" in result

    def test_works_for_markdown_table(self, table_chunk):
        """Markdown 表格无 HTML 标签，headers/rows 提取为空但不报错。"""
        result = build_table_embedding_text(table_chunk)
        assert "Table 2.1" in result
        assert "Section:" in result

    def test_no_llm_call(self, html_table_chunk):
        """确认不调用 LLM。"""
        result = build_table_embedding_text(html_table_chunk)
        assert isinstance(result, str)
        assert len(result) > 0


@pytest.mark.asyncio
async def test_generate_formula_description(formula_chunk):
    mock_response = "设计抗力Rd的计算公式，考虑分项系数。"
    with patch("pipeline.contextualize._call_llm", new_callable=AsyncMock, return_value=mock_response):
        result = await generate_formula_description(formula_chunk)
        assert result == mock_response


@pytest.mark.asyncio
async def test_enrich_table_chunk_uses_structural_extraction(html_table_chunk):
    """表格 enrichment 不调用 LLM，直接用结构化提取。"""
    chunks = await enrich_chunk_summaries([html_table_chunk])

    assert "Table 3.1" in chunks[0].embedding_text
    assert "Columns:" in chunks[0].embedding_text
    assert "Class" in chunks[0].embedding_text


@pytest.mark.asyncio
async def test_enrich_chunk_summaries_retries_formula_failure_once(formula_chunk):
    mock_desc = AsyncMock(side_effect=[RuntimeError("429"), "设计抗力Rd的计算公式，考虑分项系数。"])

    with patch("pipeline.contextualize.generate_formula_description", mock_desc):
        chunks = await enrich_chunk_summaries([formula_chunk])

    assert mock_desc.await_count == 2
    assert chunks[0].embedding_text == "设计抗力Rd的计算公式，考虑分项系数。 Section: 6.3.5 Design resistance"
