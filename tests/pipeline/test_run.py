"""Tests for Stage 3.5 wiring in pipeline.run."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from pipeline import run as pipeline_run
from pipeline.config import PipelineConfig
from server.models.schemas import Chunk


@pytest.mark.asyncio
async def test_stage_3_5_calls_enrich_chunks_with_tree_and_all_chunk_progress(tmp_path: Path, monkeypatch):
    parsed_dir = tmp_path / "parsed"
    debug_dir = tmp_path / "debug"
    doc_dir = parsed_dir / "EN1992"
    doc_dir.mkdir(parents=True)
    md_path = doc_dir / "EN1992.md"
    md_path.write_text(
        "# Section 3 Materials\n\n"
        "## 3.2 Concrete\n\n"
        "Concrete text.\n\n"
        "| Class | fck |\n"
        "|---|---|\n"
        "| C30/37 | 30 |\n",
        encoding="utf-8",
    )
    (doc_dir / "EN1992_meta.json").write_text("{}", encoding="utf-8")

    config = PipelineConfig(
        parsed_dir=str(parsed_dir),
        debug_pipeline_dir=str(debug_dir),
        tree_pruning_enabled=False,
    )
    calls: list[dict] = []

    async def fake_enrich_chunks(chunks: list[Chunk], cfg: PipelineConfig, *, tree=None, progress_callback=None):
        assert cfg is config
        assert tree is not None
        if progress_callback is not None:
            progress_callback(
                {
                    "completed": len(chunks),
                    "total": len(chunks),
                    "chunk_id": chunks[-1].chunk_id,
                    "element_type": chunks[-1].metadata.element_type.value,
                    "section_path": chunks[-1].metadata.section_path,
                }
            )
        calls.append({"chunks": chunks, "tree": tree})
        return chunks

    async def fake_index_to_milvus(chunks: list[Chunk], cfg: PipelineConfig) -> int:
        return len(chunks)

    async def fake_index_to_elasticsearch(chunks: list[Chunk], cfg: PipelineConfig) -> int:
        return len(chunks)

    monkeypatch.setattr(pipeline_run, "enrich_chunks", fake_enrich_chunks)
    monkeypatch.setattr(pipeline_run, "index_to_milvus", fake_index_to_milvus)
    monkeypatch.setattr(pipeline_run, "index_to_elasticsearch", fake_index_to_elasticsearch)

    await pipeline_run._run_pipeline(config, start_stage=2)

    assert len(calls) == 1
    chunks = calls[0]["chunks"]
    run_dirs = sorted(debug_dir.iterdir())
    stage_file = run_dirs[-1] / "manifest.json"
    payload = json.loads(stage_file.read_text(encoding="utf-8"))
    assert payload["documents"]["EN1992"]["stages"]["stage_3_5"]["summary"]["total_all_chunks"] == len(chunks)


@pytest.mark.asyncio
async def test_start_stage_3_5_resumes_stage3_chunks_and_runs_enrichment(
    tmp_path: Path,
    monkeypatch,
):
    parsed_dir = tmp_path / "parsed"
    debug_dir = tmp_path / "debug"
    doc_dir = parsed_dir / "EN1992"
    doc_dir.mkdir(parents=True)
    (doc_dir / "EN1992.md").write_text(
        "# Section 3 Materials\n\n"
        "# 3.2 Concrete\n\n"
        "Concrete text.\n",
        encoding="utf-8",
    )
    (doc_dir / "EN1992_meta.json").write_text("{}", encoding="utf-8")

    config = PipelineConfig(
        parsed_dir=str(parsed_dir),
        debug_pipeline_dir=str(debug_dir),
        tree_pruning_enabled=False,
    )

    async def fake_index_to_milvus(chunks: list[Chunk], cfg: PipelineConfig) -> int:
        return len(chunks)

    async def fake_index_to_elasticsearch(chunks: list[Chunk], cfg: PipelineConfig) -> int:
        return len(chunks)

    monkeypatch.setattr(pipeline_run, "index_to_milvus", fake_index_to_milvus)
    monkeypatch.setattr(pipeline_run, "index_to_elasticsearch", fake_index_to_elasticsearch)

    await pipeline_run._run_pipeline(config, start_stage=2)

    source_runs = sorted(debug_dir.iterdir())
    source_run_id = source_runs[-1].name
    calls: list[dict] = []

    async def fake_enrich_chunks(
        chunks: list[Chunk],
        cfg: PipelineConfig,
        *,
        tree=None,
        progress_callback=None,
    ):
        assert cfg is config
        assert tree is not None
        calls.append({"chunks": chunks, "tree": tree})
        for chunk in chunks:
            chunk.embedding_text = f"[CTX] resumed\n\n{chunk.content}"
        return chunks

    monkeypatch.setattr(pipeline_run, "enrich_chunks", fake_enrich_chunks)

    await pipeline_run._run_pipeline(
        config,
        start_stage=3.5,
        resume_run=source_run_id,
    )

    assert len(calls) == 1
    resumed_chunks = calls[0]["chunks"]
    assert resumed_chunks
    target_runs = sorted(debug_dir.iterdir())
    target_run_dir = target_runs[-1]
    stage35_path = target_run_dir / "artifacts" / "EN1992" / "stage35_chunks.json"
    payload = json.loads(stage35_path.read_text(encoding="utf-8"))
    assert payload["total"] == len(resumed_chunks)
    assert all(
        chunk["embedding_text"].startswith("[CTX] resumed")
        for chunk in payload["chunks"]
    )
