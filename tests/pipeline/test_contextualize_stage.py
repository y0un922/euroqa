"""Tests for Stage 3.5 contextual chunk enrichment."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from structlog.testing import capture_logs

from pipeline.config import PipelineConfig
from pipeline.contextualize import build_embedding_text, enrich_chunks
from pipeline.contextualizer import ContextualizeResult
from pipeline.structure import DocumentNode
from pipeline.structure import ElementType as StructElementType
from server.models.schemas import Chunk, ChunkMetadata, ElementType


def _chunk(
    chunk_id: str,
    content: str,
    element_type: ElementType,
    *,
    parent_chunk_id: str | None = None,
    parent_text_chunk_id: str | None = None,
) -> Chunk:
    return Chunk(
        chunk_id=chunk_id,
        content=content,
        embedding_text=content,
        metadata=ChunkMetadata(
            source="EN 1992-1-1:2004",
            source_title="Design of concrete structures",
            section_path=["Section 3", "3.2 Concrete"],
            page_numbers=[1],
            page_file_index=[0],
            clause_ids=[],
            element_type=element_type,
            parent_chunk_id=parent_chunk_id,
            parent_text_chunk_id=parent_text_chunk_id,
            object_label="Figure 3.3" if element_type == ElementType.IMAGE else "",
        ),
    )


@pytest.fixture
def stage_chunks() -> list[Chunk]:
    parent = _chunk("parent-1", "Parent section text.", ElementType.TEXT)
    text_1 = _chunk("text-1", "First text chunk.", ElementType.TEXT, parent_chunk_id="parent-1")
    text_2 = _chunk("text-2", "Second text chunk.", ElementType.TEXT, parent_chunk_id="parent-1")
    table = _chunk("table-1", "<table><tr><td>fck</td></tr></table>", ElementType.TABLE, parent_text_chunk_id="parent-1")
    formula = _chunk("formula-1", "$$f_cd = alpha_cc f_ck / gamma_c$$", ElementType.FORMULA, parent_text_chunk_id="parent-1")
    image = _chunk("image-1", "![Figure 3.3](images/figure-3-3.png)", ElementType.IMAGE, parent_text_chunk_id="parent-1")
    return [parent, text_1, text_2, table, formula, image]


@pytest.fixture
def document_tree() -> DocumentNode:
    return DocumentNode(
        title="root",
        source="EN 1992-1-1:2004",
        children=[
            DocumentNode(
                title="Section 3 Materials",
                content="Concrete material properties.",
                element_type=StructElementType.SECTION,
                source="EN 1992-1-1:2004",
            )
        ],
    )


def _result_for_kind(kind: str) -> ContextualizeResult:
    if kind == "text":
        return ContextualizeResult(context_blurb="text context", semantic_description="")
    return ContextualizeResult(context_blurb=f"{kind} context", semantic_description=f"{kind} description")


@pytest.mark.asyncio
async def test_enrich_chunks_contextualizes_all_chunks_and_preserves_content(stage_chunks, document_tree):
    original_content = {chunk.chunk_id: chunk.content for chunk in stage_chunks}
    progress_events: list[dict] = []

    async def fake_contextualize_chunk(request):
        return _result_for_kind(request.chunk_kind)

    with patch("pipeline.contextualize.Contextualizer") as contextualizer_cls:
        instance = contextualizer_cls.return_value
        instance.generate_doc_summary = AsyncMock(return_value="Document summary.")
        instance.contextualize_chunk = AsyncMock(side_effect=fake_contextualize_chunk)
        enriched = await enrich_chunks(
            stage_chunks,
            PipelineConfig(contextualize_concurrency=2),
            tree=document_tree,
            progress_callback=progress_events.append,
        )

    assert enriched is stage_chunks
    assert instance.generate_doc_summary.await_count == 1
    assert instance.contextualize_chunk.await_count == len(stage_chunks)
    assert len(progress_events) == len(stage_chunks)
    for chunk in enriched:
        assert chunk.content == original_content[chunk.chunk_id]
        if chunk.metadata.element_type == ElementType.TEXT:
            assert chunk.embedding_text.startswith("[CTX] text context\n\n")
            assert chunk.embedding_text.endswith(chunk.content)
        else:
            kind = chunk.metadata.element_type.value
            assert chunk.embedding_text == f"[CTX] {kind} context\n\n[DESC] {kind} description"


@pytest.mark.asyncio
async def test_enrich_chunks_single_chunk_failure_keeps_raw_embedding(stage_chunks, document_tree):
    async def fake_contextualize_chunk(request):
        if request.chunk_content == "First text chunk.":
            raise RuntimeError("llm failed")
        return _result_for_kind(request.chunk_kind)

    with patch("pipeline.contextualize.Contextualizer") as contextualizer_cls:
        instance = contextualizer_cls.return_value
        instance.generate_doc_summary = AsyncMock(return_value="Document summary.")
        instance.contextualize_chunk = AsyncMock(side_effect=fake_contextualize_chunk)
        with capture_logs() as logs:
            enriched = await enrich_chunks(stage_chunks, PipelineConfig(), tree=document_tree)

    failed = next(chunk for chunk in enriched if chunk.chunk_id == "text-1")
    assert failed.embedding_text == "First text chunk."
    assert any(log["event"] == "contextualize_failed" and log["chunk_id"] == "text-1" for log in logs)


@pytest.mark.asyncio
async def test_enrich_chunks_doc_summary_failure_propagates(stage_chunks, document_tree):
    with patch("pipeline.contextualize.Contextualizer") as contextualizer_cls:
        instance = contextualizer_cls.return_value
        instance.generate_doc_summary = AsyncMock(side_effect=RuntimeError("summary failed"))
        with pytest.raises(RuntimeError, match="summary failed"):
            await enrich_chunks(stage_chunks, PipelineConfig(), tree=document_tree)


def test_build_embedding_text_text_chunk():
    chunk = _chunk("text-1", "Raw text chunk.", ElementType.TEXT)
    result = ContextualizeResult(context_blurb="context", semantic_description="")

    assert build_embedding_text(chunk, result) == "[CTX] context\n\nRaw text chunk."


def test_build_embedding_text_special_chunk():
    chunk = _chunk("table-1", "<table></table>", ElementType.TABLE)
    result = ContextualizeResult(context_blurb="context", semantic_description="description")

    assert build_embedding_text(chunk, result) == "[CTX] context\n\n[DESC] description"


@pytest.mark.asyncio
async def test_enrich_chunks_empty_input_returns_immediately():
    result = await enrich_chunks([], PipelineConfig())
    assert result == []


@pytest.mark.asyncio
async def test_enrich_chunks_without_tree_uses_chunk_outline(stage_chunks):
    """When tree is None, _build_outline_from_chunks fallback runs."""
    captured: dict = {}

    async def fake_contextualize_chunk(request):
        return _result_for_kind(request.chunk_kind)

    async def fake_doc_summary(*, source_title, doc_outline_text):
        captured["outline"] = doc_outline_text
        return "Document summary."

    with patch("pipeline.contextualize.Contextualizer") as contextualizer_cls:
        instance = contextualizer_cls.return_value
        instance.generate_doc_summary = AsyncMock(side_effect=fake_doc_summary)
        instance.contextualize_chunk = AsyncMock(side_effect=fake_contextualize_chunk)
        await enrich_chunks(stage_chunks, PipelineConfig())  # tree omitted -> None

    # Outline derived from chunk metadata.section_path, not DocumentNode.
    assert "3.2 Concrete" in captured["outline"]


@pytest.mark.asyncio
async def test_enrich_chunks_progress_callback_can_be_async(stage_chunks, document_tree):
    """When progress_callback returns an awaitable, it is awaited."""
    async_calls: list[dict] = []

    async def async_progress(payload: dict):
        async_calls.append(payload)

    async def fake_contextualize_chunk(request):
        return _result_for_kind(request.chunk_kind)

    with patch("pipeline.contextualize.Contextualizer") as contextualizer_cls:
        instance = contextualizer_cls.return_value
        instance.generate_doc_summary = AsyncMock(return_value="Document summary.")
        instance.contextualize_chunk = AsyncMock(side_effect=fake_contextualize_chunk)
        await enrich_chunks(
            stage_chunks,
            PipelineConfig(),
            tree=document_tree,
            progress_callback=async_progress,
        )

    assert len(async_calls) == len(stage_chunks)


@pytest.mark.asyncio
async def test_text_chunk_without_parent_uses_own_content_as_parent_section(document_tree):
    """Text chunk lacking parent_chunk_id falls back to its own content."""
    orphan = _chunk("orphan-1", "Standalone text.", ElementType.TEXT)  # no parent_chunk_id
    captured_parent: list[str] = []

    async def fake_contextualize_chunk(request):
        captured_parent.append(request.parent_section_text)
        return _result_for_kind(request.chunk_kind)

    with patch("pipeline.contextualize.Contextualizer") as contextualizer_cls:
        instance = contextualizer_cls.return_value
        instance.generate_doc_summary = AsyncMock(return_value="Document summary.")
        instance.contextualize_chunk = AsyncMock(side_effect=fake_contextualize_chunk)
        await enrich_chunks([orphan], PipelineConfig(), tree=document_tree)

    assert captured_parent == ["Standalone text."]


@pytest.mark.asyncio
async def test_image_chunk_without_alt_markdown_uses_object_label(document_tree):
    """Image chunk where regex fails to extract alt falls back to object_label."""
    weird_image = _chunk(
        "img-1",
        "no markdown here",  # regex won't match
        ElementType.IMAGE,
        parent_text_chunk_id=None,
    )
    captured_alt: list[str] = []

    async def fake_contextualize_chunk(request):
        captured_alt.append(request.chunk_alt)
        return _result_for_kind(request.chunk_kind)

    with patch("pipeline.contextualize.Contextualizer") as contextualizer_cls:
        instance = contextualizer_cls.return_value
        instance.generate_doc_summary = AsyncMock(return_value="Document summary.")
        instance.contextualize_chunk = AsyncMock(side_effect=fake_contextualize_chunk)
        await enrich_chunks([weird_image], PipelineConfig(), tree=document_tree)

    assert captured_alt == ["Figure 3.3"]  # object_label set in _chunk fixture


@pytest.mark.asyncio
async def test_special_chunk_without_parent_uses_empty_parent_section(document_tree):
    table = _chunk("table-orphan", "| A |\n|---|\n| 1 |", ElementType.TABLE)
    captured_parent: list[str] = []

    async def fake_contextualize_chunk(request):
        captured_parent.append(request.parent_section_text)
        return _result_for_kind(request.chunk_kind)

    with patch("pipeline.contextualize.Contextualizer") as contextualizer_cls:
        instance = contextualizer_cls.return_value
        instance.generate_doc_summary = AsyncMock(return_value="Document summary.")
        instance.contextualize_chunk = AsyncMock(side_effect=fake_contextualize_chunk)
        await enrich_chunks([table], PipelineConfig(), tree=document_tree)

    assert captured_parent == [""]
