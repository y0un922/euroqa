"""Test LLM summary generation (mock LLM calls)."""
from unittest.mock import AsyncMock, patch

import pytest

from pipeline.summarize import generate_table_summary, generate_formula_description
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


@pytest.mark.asyncio
async def test_generate_table_summary(table_chunk):
    mock_response = "设计使用年限分类表，临时结构10年。"
    with patch("pipeline.summarize._call_llm", new_callable=AsyncMock, return_value=mock_response):
        result = await generate_table_summary(table_chunk)
        assert result == mock_response


@pytest.mark.asyncio
async def test_generate_formula_description(formula_chunk):
    mock_response = "设计抗力Rd的计算公式，考虑分项系数。"
    with patch("pipeline.summarize._call_llm", new_callable=AsyncMock, return_value=mock_response):
        result = await generate_formula_description(formula_chunk)
        assert result == mock_response
