"""Tests for the server-side single-document pipeline runner."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from pipeline.config import PipelineConfig
from server.services import pipeline_runner


@pytest.mark.asyncio
async def test_run_single_document_indexes_chunks_with_uploaded_doc_id(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    doc_id = "DG_EN1992-1-1__-1-2"
    pdf_dir = tmp_path / "pdfs"
    parsed_dir = tmp_path / "parsed"
    pdf_dir.mkdir()
    (pdf_dir / f"{doc_id}.pdf").write_bytes(b"%PDF-1.4 demo")
    config = PipelineConfig(
        pdf_dir=str(pdf_dir),
        parsed_dir=str(parsed_dir),
        mineru_poll_interval_seconds=0,
        tree_pruning_enabled=False,
    )

    async def fake_parse_pdf(
        pdf_path: Path,
        output_dir: Path,
        _config: PipelineConfig,
        *,
        context_summary_enabled: bool = True,
    ):
        assert pdf_path.name == f"{doc_id}.pdf"
        assert context_summary_enabled is True
        output_dir.mkdir(parents=True, exist_ok=True)
        md_path = output_dir / f"{doc_id}.md"
        md_path.write_text(
            "# Section 1\n\nConcrete design requirements.",
            encoding="utf-8",
        )
        (output_dir / f"{doc_id}_meta.json").write_text(
            '{"context_summary_enabled": true}',
            encoding="utf-8",
        )
        return md_path

    async def fake_enrich(chunks, _config, *, tree=None, progress_callback=None):
        assert tree is not None
        return chunks

    indexed_sources: list[str] = []

    async def fake_index_to_milvus(chunks, _config):
        indexed_sources.extend(chunk.metadata.source for chunk in chunks)
        return len(chunks)

    async def fake_index_to_elasticsearch(chunks, _config):
        indexed_sources.extend(chunk.metadata.source for chunk in chunks)
        return len(chunks)

    delete_sources: list[str] = []

    async def fake_delete_document_chunks(source_name: str, _config):
        delete_sources.append(source_name)
        return {"milvus": 0, "elasticsearch": 0}

    async def fake_invalidate_retriever_cache():
        return None

    monkeypatch.setattr(pipeline_runner, "parse_pdf", fake_parse_pdf)
    monkeypatch.setattr(pipeline_runner, "enrich_chunks", fake_enrich)
    monkeypatch.setattr(pipeline_runner, "index_to_milvus", fake_index_to_milvus)
    monkeypatch.setattr(
        pipeline_runner,
        "index_to_elasticsearch",
        fake_index_to_elasticsearch,
    )
    monkeypatch.setattr(
        pipeline_runner,
        "delete_document_chunks",
        fake_delete_document_chunks,
    )
    monkeypatch.setattr(
        pipeline_runner,
        "invalidate_retriever_cache",
        fake_invalidate_retriever_cache,
    )

    result = await pipeline_runner.run_single_document(doc_id, config)

    assert result["chunks"] > 0
    assert indexed_sources
    assert set(indexed_sources) == {doc_id}
    assert delete_sources == [doc_id, doc_id.replace("_", " ")]


@pytest.mark.asyncio
async def test_run_single_document_uses_requested_file_name_for_source_title(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    doc_id = "huake_opaque_doc_123"
    requested_file_name = "Eurocode 2 - Concrete Design.pdf"
    pdf_dir = tmp_path / "pdfs"
    parsed_dir = tmp_path / "parsed"
    output_dir = parsed_dir / doc_id
    pdf_dir.mkdir()
    output_dir.mkdir(parents=True)
    (pdf_dir / f"{doc_id}.pdf").write_bytes(b"%PDF-1.4 demo")
    (output_dir / "parse_options.json").write_text(
        json.dumps(
            {
                "context_summary_enabled": False,
                "file_name": requested_file_name,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    config = PipelineConfig(
        pdf_dir=str(pdf_dir),
        parsed_dir=str(parsed_dir),
        mineru_poll_interval_seconds=0,
        tree_pruning_enabled=False,
    )

    async def fake_parse_pdf(
        pdf_path: Path,
        output_dir: Path,
        _config: PipelineConfig,
        *,
        context_summary_enabled: bool = True,
    ):
        assert pdf_path.name == f"{doc_id}.pdf"
        assert context_summary_enabled is False
        md_path = output_dir / f"{doc_id}.md"
        md_path.write_text("# Section 1\n\nConcrete text.", encoding="utf-8")
        (output_dir / f"{doc_id}_meta.json").write_text(
            '{"title": "MinerU Title Should Be Ignored", "context_summary_enabled": false}',
            encoding="utf-8",
        )
        return md_path

    indexed_titles: list[str] = []

    async def fake_index_to_milvus(chunks, _config):
        indexed_titles.extend(chunk.metadata.source_title for chunk in chunks)
        return len(chunks)

    async def fake_index_to_elasticsearch(chunks, _config):
        indexed_titles.extend(chunk.metadata.source_title for chunk in chunks)
        return len(chunks)

    async def fake_delete_document_chunks(source_name: str, _config):
        return {"milvus": 0, "elasticsearch": 0}

    async def fake_invalidate_retriever_cache():
        return None

    monkeypatch.setattr(pipeline_runner, "parse_pdf", fake_parse_pdf)
    monkeypatch.setattr(pipeline_runner, "index_to_milvus", fake_index_to_milvus)
    monkeypatch.setattr(
        pipeline_runner,
        "index_to_elasticsearch",
        fake_index_to_elasticsearch,
    )
    monkeypatch.setattr(
        pipeline_runner,
        "delete_document_chunks",
        fake_delete_document_chunks,
    )
    monkeypatch.setattr(
        pipeline_runner,
        "invalidate_retriever_cache",
        fake_invalidate_retriever_cache,
    )

    result = await pipeline_runner.run_single_document(doc_id, config)

    assert result["chunks"] > 0
    assert indexed_titles
    assert set(indexed_titles) == {requested_file_name}


@pytest.mark.asyncio
async def test_run_single_document_skips_context_summary_when_disabled(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    doc_id = "EN1992"
    pdf_dir = tmp_path / "pdfs"
    parsed_dir = tmp_path / "parsed"
    pdf_dir.mkdir()
    output_dir = parsed_dir / doc_id
    output_dir.mkdir(parents=True)
    (pdf_dir / f"{doc_id}.pdf").write_bytes(b"%PDF-1.4 demo")
    (output_dir / "parse_options.json").write_text(
        '{"context_summary_enabled": false}',
        encoding="utf-8",
    )
    config = PipelineConfig(
        pdf_dir=str(pdf_dir),
        parsed_dir=str(parsed_dir),
        mineru_poll_interval_seconds=0,
        tree_pruning_enabled=False,
    )

    async def fake_parse_pdf(
        pdf_path: Path,
        output_dir: Path,
        _config: PipelineConfig,
        *,
        context_summary_enabled: bool = True,
    ):
        assert context_summary_enabled is False
        md_path = output_dir / f"{doc_id}.md"
        md_path.write_text("# Section 1\n\nConcrete text.", encoding="utf-8")
        (output_dir / f"{doc_id}_meta.json").write_text(
            '{"context_summary_enabled": false}',
            encoding="utf-8",
        )
        return md_path

    async def fake_enrich(*args, **kwargs):
        raise AssertionError("context summary should be skipped")

    async def fake_index_to_milvus(chunks, _config):
        return len(chunks)

    async def fake_index_to_elasticsearch(chunks, _config):
        return len(chunks)

    async def fake_delete_document_chunks(source_name: str, _config):
        return {"milvus": 0, "elasticsearch": 0}

    async def fake_invalidate_retriever_cache():
        return None

    monkeypatch.setattr(pipeline_runner, "parse_pdf", fake_parse_pdf)
    monkeypatch.setattr(pipeline_runner, "enrich_chunks", fake_enrich)
    monkeypatch.setattr(pipeline_runner, "index_to_milvus", fake_index_to_milvus)
    monkeypatch.setattr(
        pipeline_runner,
        "index_to_elasticsearch",
        fake_index_to_elasticsearch,
    )
    monkeypatch.setattr(
        pipeline_runner,
        "delete_document_chunks",
        fake_delete_document_chunks,
    )
    monkeypatch.setattr(
        pipeline_runner,
        "invalidate_retriever_cache",
        fake_invalidate_retriever_cache,
    )

    result = await pipeline_runner.run_single_document(doc_id, config)

    assert result["chunks"] > 0
