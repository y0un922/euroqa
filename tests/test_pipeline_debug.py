"""Tests for pipeline debug run recorder and store."""
from __future__ import annotations

from pipeline.structure import DocumentNode, ElementType as TreeElementType
from server.models.schemas import Chunk, ChunkMetadata, ElementType
from shared.pipeline_debug import PipelineDebugRecorder, PipelineDebugStore


def _make_chunk() -> Chunk:
    return Chunk(
        chunk_id="chunk-1",
        content="Chunk content",
        embedding_text="Embedding text",
        metadata=ChunkMetadata(
            source="EN 1990:2002",
            source_title="Basis",
            section_path=["2.3"],
            page_numbers=[28],
            page_file_index=[27],
            clause_ids=["2.3(1)"],
            element_type=ElementType.TEXT,
        ),
    )


def test_pipeline_debug_recorder_persists_run_history(tmp_path):
    recorder = PipelineDebugRecorder.create(tmp_path)
    recorder.start_stage("stage_1", summary={"message": "PDF -> Markdown"})
    recorder.record_text_artifact(
        document_id="EN1990_2002",
        stage="stage_1",
        filename="stage1.md",
        label="Markdown",
        content="# Demo",
        content_type="text/markdown",
    )
    recorder.complete_stage("stage_1", summary={"count": 1})

    tree = DocumentNode(
        title="Section 1",
        content="body",
        element_type=TreeElementType.SECTION,
        level=1,
        children=[
            DocumentNode(
                title="formula",
                content="$$a=b$$",
                element_type=TreeElementType.FORMULA,
            )
        ],
        source="EN 1990:2002",
    )
    recorder.record_json_artifact(
        document_id="EN1990_2002",
        stage="stage_2",
        filename="tree.json",
        label="Tree",
        payload=PipelineDebugRecorder.serialize_tree(tree),
    )
    recorder.record_json_artifact(
        document_id="EN1990_2002",
        stage="stage_3",
        filename="chunks.json",
        label="Chunks",
        payload=PipelineDebugRecorder.serialize_chunks([_make_chunk()]),
    )
    recorder.complete_run(summary={"documents": 1})

    store = PipelineDebugStore(tmp_path)
    runs = store.list_runs()

    assert len(runs) == 1
    run = runs[0]
    assert run["status"] == "completed"
    assert run["stages"]["stage_1"]["summary"]["count"] == 1
    artifact = run["documents"]["EN1990_2002"]["stages"]["stage_1"]["artifacts"][0]
    assert store.read_text_artifact(run["run_id"], artifact["path"]) == "# Demo"
    tree_payload = store.read_json_artifact(
        run["run_id"],
        run["documents"]["EN1990_2002"]["stages"]["stage_2"]["artifacts"][0]["path"],
    )
    assert tree_payload["children"][0]["element_type"] == "formula"
