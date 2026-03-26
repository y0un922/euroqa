"""Stage 3.5: Generate natural language summaries for special element chunks.

Uses LLM to create embedding-friendly text for tables, formulas, and images.
"""
from __future__ import annotations

from openai import AsyncOpenAI

from pipeline.config import PipelineConfig
from server.models.schemas import Chunk, ElementType

_client: AsyncOpenAI | None = None


def _get_client(config: PipelineConfig | None = None) -> AsyncOpenAI:
    global _client
    if _client is None:
        cfg = config or PipelineConfig()
        _client = AsyncOpenAI(api_key=cfg.llm_api_key, base_url=cfg.llm_base_url)
    return _client


async def _call_llm(prompt: str, config: PipelineConfig | None = None) -> str:
    client = _get_client(config)
    cfg = config or PipelineConfig()
    resp = await client.chat.completions.create(
        model=cfg.llm_model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
        max_tokens=300,
    )
    return resp.choices[0].message.content.strip()


async def generate_table_summary(chunk: Chunk, config: PipelineConfig | None = None) -> str:
    section_context = " > ".join(chunk.metadata.section_path)
    prompt = (
        f"以下是欧洲建筑规范 {chunk.metadata.source} 中 {section_context} 的一个表格。\n"
        f"请用简洁的中文描述表格的内容和关键数据点（100字以内）。\n\n"
        f"表格内容：\n{chunk.content}"
    )
    return await _call_llm(prompt, config)


async def generate_formula_description(chunk: Chunk, config: PipelineConfig | None = None) -> str:
    section_context = " > ".join(chunk.metadata.section_path)
    prompt = (
        f"以下是欧洲建筑规范 {chunk.metadata.source} 中 {section_context} 的一个公式。\n"
        f"请用简洁的中文描述公式的含义和用途（100字以内）。\n\n"
        f"公式内容：\n{chunk.content}"
    )
    return await _call_llm(prompt, config)


async def enrich_chunk_summaries(
    chunks: list[Chunk],
    config: PipelineConfig | None = None,
) -> list[Chunk]:
    """Fill embedding_text for all special element chunks."""
    for chunk in chunks:
        if chunk.metadata.element_type == ElementType.TABLE:
            summary = await generate_table_summary(chunk, config)
            chunk.embedding_text = f"{summary} Section: {' > '.join(chunk.metadata.section_path)}"
        elif chunk.metadata.element_type == ElementType.FORMULA:
            desc = await generate_formula_description(chunk, config)
            chunk.embedding_text = f"{desc} Section: {' > '.join(chunk.metadata.section_path)}"
        elif chunk.metadata.element_type == ElementType.IMAGE:
            chunk.embedding_text = f"{chunk.content} Section: {' > '.join(chunk.metadata.section_path)}"
    return chunks
