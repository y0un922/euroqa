"""Pipeline CLI: orchestrate Stage 1-4."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import click
import structlog

from pipeline.config import PipelineConfig
from pipeline.parse import parse_all_pdfs
from pipeline.structure import parse_markdown_to_tree
from pipeline.chunk import create_chunks
from pipeline.summarize import enrich_chunk_summaries
from pipeline.index import index_to_milvus, index_to_elasticsearch

logger = structlog.get_logger()


async def _run_pipeline(config: PipelineConfig) -> None:
    """Execute full pipeline."""

    # Stage 1: MinerU PDF parsing
    logger.info("stage_1_start", msg="PDF -> Markdown")
    md_paths = await parse_all_pdfs(config)
    logger.info("stage_1_done", count=len(md_paths))

    all_chunks = []

    for md_path in md_paths:
        source_name = md_path.stem.replace("_", " ")
        markdown = md_path.read_text(encoding="utf-8")

        # Load metadata if available
        meta_path = md_path.parent / f"{md_path.stem}_meta.json"
        meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
        source_title = meta.get("title", source_name)

        # Stage 2: Structure parsing
        tree = parse_markdown_to_tree(markdown, source=source_name)

        # Stage 3: Chunking
        chunks = create_chunks(tree, source_title=source_title)
        logger.info("stage_3_done", source=source_name, chunks=len(chunks))

        # Stage 3.5: LLM summaries
        chunks = await enrich_chunk_summaries(chunks, config)

        all_chunks.extend(chunks)

    logger.info("total_chunks", count=len(all_chunks))

    # Stage 4: Embedding + indexing
    milvus_count = await index_to_milvus(all_chunks, config)
    es_count = await index_to_elasticsearch(all_chunks, config)
    logger.info("stage_4_done", milvus=milvus_count, es=es_count)


@click.command()
@click.option("--pdf-dir", default=None, help="PDF directory (overrides .env)")
def main(pdf_dir: str | None) -> None:
    """Eurocode document processing pipeline."""
    config = PipelineConfig()
    if pdf_dir:
        config.pdf_dir = pdf_dir
    asyncio.run(_run_pipeline(config))


if __name__ == "__main__":
    main()
