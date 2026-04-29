"""Pipeline CLI: orchestrate Stage 1-4."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import click
import structlog

from pipeline.content_list import content_list_output_name
from pipeline.config import PipelineConfig
from pipeline.parse import parse_all_pdfs
from pipeline.structure import (
    TreePruningConfig,
    parse_markdown_to_tree,
    prune_document_tree,
)
from pipeline.chunk import create_chunks
from pipeline.chunk import validate_unique_chunk_ids
from pipeline.summarize import enrich_chunk_summaries
from pipeline.index import index_to_milvus, index_to_elasticsearch
from server.models.schemas import Chunk
from shared.pipeline_debug import PipelineDebugRecorder, PipelineDebugStore

logger = structlog.get_logger()

# 阶段编号映射
_STAGE_ORDER = {"1": 1, "2": 2, "3": 3, "3.5": 3.5, "4": 4}


def _load_content_list(md_path: Path, meta: dict) -> object | None:
    """Load the extracted MinerU content_list payload when present."""

    output_name = meta.get("content_list_output")
    if not isinstance(output_name, str) or not output_name.strip():
        output_name = content_list_output_name(md_path.stem)
    content_list_path = md_path.parent / output_name
    if not content_list_path.is_file():
        return None
    return json.loads(content_list_path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# 断点续跑：从上次 run 的产物中恢复 chunks
# ---------------------------------------------------------------------------

def _find_latest_run_with_stage(
    debug_dir: str,
    required_artifact: str,
) -> str | None:
    """找到最新的、包含指定产物的 run。"""
    store = PipelineDebugStore(debug_dir)
    for run in store.list_runs():
        run_id = run["run_id"]
        run_dir = Path(debug_dir) / run_id
        # 检查所有文档目录中是否有所需产物
        artifacts_dir = run_dir / "artifacts"
        if not artifacts_dir.exists():
            continue
        has_artifact = any(
            (doc_dir / required_artifact).exists()
            for doc_dir in artifacts_dir.iterdir()
            if doc_dir.is_dir() and doc_dir.name != "_global"
        )
        if has_artifact:
            return run_id
    return None


def _load_chunks_from_run(
    debug_dir: str,
    run_id: str,
    artifact_filename: str,
) -> list[Chunk]:
    """从指定 run 的产物中反序列化 Chunk 列表。"""
    run_dir = Path(debug_dir) / run_id / "artifacts"
    all_chunks: list[Chunk] = []

    for doc_dir in sorted(run_dir.iterdir()):
        if not doc_dir.is_dir() or doc_dir.name == "_global":
            continue
        artifact_path = doc_dir / artifact_filename
        if not artifact_path.exists():
            logger.warning("artifact_missing", doc=doc_dir.name, artifact=artifact_filename)
            continue
        data = json.loads(artifact_path.read_text(encoding="utf-8"))
        chunk_dicts = data.get("chunks", [])
        for cd in chunk_dicts:
            all_chunks.append(Chunk.model_validate(cd))
        logger.info(
            "chunks_loaded_from_run",
            doc=doc_dir.name,
            run_id=run_id,
            count=len(chunk_dicts),
        )

    return all_chunks


# ---------------------------------------------------------------------------
# Pipeline 主流程
# ---------------------------------------------------------------------------

async def _run_pipeline(
    config: PipelineConfig,
    start_stage: float = 1,
    resume_run: str | None = None,
) -> None:
    """Execute full pipeline, optionally resuming from a specific stage."""
    recorder = PipelineDebugRecorder.create(config.debug_pipeline_dir)
    logger.info("pipeline_run_created", run_id=recorder.run_id, start_stage=start_stage)

    try:
        all_chunks: list[Chunk] = []

        # ---- 断点续跑：从已有产物加载 chunks ----
        if start_stage > 3.5:
            # 从 stage35_chunks.json 恢复
            source_run = resume_run or _find_latest_run_with_stage(
                config.debug_pipeline_dir, "stage35_chunks.json",
            )
            if source_run is None:
                raise RuntimeError(
                    "无法续跑：找不到包含 stage35_chunks.json 的历史 run。"
                    "请先完整运行一次 pipeline，或指定 --resume-run。"
                )
            logger.info("resuming_from_run", run_id=source_run, artifact="stage35_chunks.json")
            all_chunks = _load_chunks_from_run(
                config.debug_pipeline_dir, source_run, "stage35_chunks.json",
            )
            validate_unique_chunk_ids(all_chunks)
            logger.info("resume_chunks_loaded", count=len(all_chunks))

        elif start_stage > 3:
            # 从 stage3_chunks.json 恢复，然后跑 stage 3.5
            source_run = resume_run or _find_latest_run_with_stage(
                config.debug_pipeline_dir, "stage3_chunks.json",
            )
            if source_run is None:
                raise RuntimeError(
                    "无法续跑：找不到包含 stage3_chunks.json 的历史 run。"
                )
            logger.info("resuming_from_run", run_id=source_run, artifact="stage3_chunks.json")
            all_chunks = _load_chunks_from_run(
                config.debug_pipeline_dir, source_run, "stage3_chunks.json",
            )
            validate_unique_chunk_ids(all_chunks)
            logger.info("resume_chunks_loaded", count=len(all_chunks))

        # ---- Stage 1: MinerU PDF parsing ----
        if start_stage <= 1:
            logger.info("stage_1_start", msg="PDF -> Markdown")
            recorder.start_stage("stage_1", summary={"message": "PDF -> Markdown"})
            md_paths = await parse_all_pdfs(config)
            for md_path in md_paths:
                doc_id = md_path.stem
                meta_path = md_path.parent / f"{doc_id}_meta.json"
                markdown = md_path.read_text(encoding="utf-8")
                meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
                content_list = _load_content_list(md_path, meta)
                recorder.record_text_artifact(
                    document_id=doc_id,
                    stage="stage_1",
                    filename="stage1.md",
                    label="Markdown",
                    content=markdown,
                    content_type="text/markdown",
                )
                recorder.record_json_artifact(
                    document_id=doc_id,
                    stage="stage_1",
                    filename="stage1_meta.json",
                    label="Metadata",
                    payload=meta,
                )
                recorder.complete_stage(
                    "stage_1",
                    document_id=doc_id,
                    summary={"markdown_length": len(markdown), "has_meta": bool(meta)},
                )
            recorder.complete_stage("stage_1", summary={"count": len(md_paths)})
            logger.info("stage_1_done", count=len(md_paths), run_id=recorder.run_id)
        else:
            # 获取已解析的 markdown 文件列表（断点续跑时仍需要文档列表）
            md_paths = sorted(Path(config.parsed_dir).glob("*/*.md"))
            logger.info("stage_1_skipped", count=len(md_paths))

        # ---- Stage 2 + 3 + 3.5: 逐文档处理 ----
        if start_stage <= 1 or (start_stage <= 3.5 and not all_chunks):
            pruning_config = TreePruningConfig.from_pipeline_settings(
                enabled=config.tree_pruning_enabled,
                body_start_titles=config.tree_pruning_body_start_titles,
            )

            for md_path in md_paths:
                doc_id = md_path.stem
                source_name = doc_id
                display_source_name = doc_id.replace("_", " ")
                markdown = md_path.read_text(encoding="utf-8")
                meta_path = md_path.parent / f"{doc_id}_meta.json"
                meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
                content_list = _load_content_list(md_path, meta)
                source_title = meta.get("title", display_source_name)

                # Stage 2: Structure
                if start_stage <= 2:
                    logger.info("stage_2_start", source=source_name)
                    recorder.start_stage("stage_2", document_id=doc_id, summary={"source": source_name})
                    raw_tree = parse_markdown_to_tree(
                        markdown,
                        source=source_name,
                        content_list=content_list,
                    )
                    tree = prune_document_tree(raw_tree, pruning_config)
                    recorder.record_json_artifact(
                        document_id=doc_id,
                        stage="stage_2",
                        filename="stage2_tree.json",
                        label="Raw Document Tree",
                        payload=PipelineDebugRecorder.serialize_tree(raw_tree),
                    )
                    recorder.record_json_artifact(
                        document_id=doc_id,
                        stage="stage_2",
                        filename="stage2_tree_pruned.json",
                        label="Pruned Document Tree",
                        payload=PipelineDebugRecorder.serialize_tree(tree),
                    )
                    recorder.complete_stage(
                        "stage_2",
                        document_id=doc_id,
                        summary={
                            "raw_top_level_sections": len(raw_tree.children),
                            "pruned_top_level_sections": len(tree.children),
                        },
                    )
                    logger.info(
                        "stage_2_done",
                        source=source_name,
                        raw_sections=len(raw_tree.children),
                        pruned_sections=len(tree.children),
                    )

                # Stage 3: Chunking
                if start_stage <= 3:
                    if start_stage > 2:
                        # 需要先跑 Stage 2
                        raw_tree = parse_markdown_to_tree(
                            markdown,
                            source=source_name,
                            content_list=content_list,
                        )
                        tree = prune_document_tree(raw_tree, pruning_config)

                    logger.info("stage_3_start", source=source_name)
                    recorder.start_stage("stage_3", document_id=doc_id, summary={"source": source_name})
                    chunks = create_chunks(tree, source_title=source_title)
                    validate_unique_chunk_ids(chunks)
                    recorder.record_json_artifact(
                        document_id=doc_id,
                        stage="stage_3",
                        filename="stage3_chunks.json",
                        label="Chunks",
                        payload=PipelineDebugRecorder.serialize_chunks(chunks),
                    )
                    recorder.complete_stage(
                        "stage_3",
                        document_id=doc_id,
                        summary={"chunks": len(chunks)},
                    )
                    logger.info("stage_3_done", source=source_name, chunks=len(chunks))

                # Stage 3.5: LLM summaries
                if start_stage <= 3.5:
                    if start_stage > 3 and all_chunks:
                        # chunks 已从断点加载
                        chunks = [c for c in all_chunks if c.metadata.source == source_name]

                    special_count = sum(1 for c in chunks if c.metadata.element_type.value != "text")
                    logger.info("stage_3_5_start", source=source_name, special_chunks=special_count)
                    recorder.start_stage(
                        "stage_3_5",
                        document_id=doc_id,
                        summary={"total_special_chunks": special_count, "completed": 0},
                    )

                    def _on_summary_progress(payload: dict) -> None:
                        logger.info(
                            "stage_3_5_progress",
                            source=source_name,
                            completed=payload["completed"],
                            total=payload["total"],
                            element_type=payload["element_type"],
                        )
                        recorder.update_stage("stage_3_5", document_id=doc_id, summary=payload)

                    chunks = await enrich_chunk_summaries(
                        chunks,
                        config,
                        progress_callback=_on_summary_progress,
                    )
                    recorder.record_json_artifact(
                        document_id=doc_id,
                        stage="stage_3_5",
                        filename="stage35_chunks.json",
                        label="Enriched Chunks",
                        payload=PipelineDebugRecorder.serialize_chunks(chunks),
                    )
                    recorder.complete_stage(
                        "stage_3_5",
                        document_id=doc_id,
                        summary={"completed": special_count, "total_special_chunks": special_count},
                    )
                    logger.info("stage_3_5_done", source=source_name, special_chunks=special_count)

                    all_chunks.extend(chunks)

        logger.info("total_chunks", count=len(all_chunks))

        # ---- Stage 4: Embedding + indexing ----
        if start_stage <= 4:
            recorder.start_stage("stage_4", summary={"total_chunks": len(all_chunks)})
            logger.info("stage_4_start", total_chunks=len(all_chunks))
            milvus_count = await index_to_milvus(all_chunks, config)
            es_count = await index_to_elasticsearch(all_chunks, config)
            stage4_summary = {
                "milvus": milvus_count,
                "es": es_count,
                "embedding_provider": config.embedding_provider,
                "rerank_provider": config.rerank_provider,
            }
            recorder.record_json_artifact(
                document_id=None,
                stage="stage_4",
                filename="stage4_summary.json",
                label="Stage 4 Summary",
                payload=stage4_summary,
            )
            recorder.complete_stage("stage_4", summary=stage4_summary)
            recorder.complete_run(
                summary={"documents": len(md_paths), "chunks": len(all_chunks), **stage4_summary},
            )
            logger.info("stage_4_done", milvus=milvus_count, es=es_count)
        else:
            recorder.complete_run(summary={"documents": len(md_paths), "chunks": len(all_chunks)})

    except Exception as exc:
        recorder.fail_run(error=str(exc))
        raise


@click.command()
@click.option("--pdf-dir", default=None, help="PDF directory (overrides .env)")
@click.option(
    "--start-stage",
    default="1",
    type=click.Choice(["1", "2", "3", "3.5", "4"]),
    help="从指定阶段开始执行（跳过之前的阶段，从历史 run 产物恢复）",
)
@click.option(
    "--resume-run",
    default=None,
    help="指定从哪个 run_id 恢复产物（默认自动找最新可用的 run）",
)
def main(pdf_dir: str | None, start_stage: str, resume_run: str | None) -> None:
    """Eurocode document processing pipeline."""
    config = PipelineConfig()
    if pdf_dir:
        config.pdf_dir = pdf_dir
    stage_num = _STAGE_ORDER[start_stage]
    asyncio.run(_run_pipeline(config, start_stage=stage_num, resume_run=resume_run))


if __name__ == "__main__":
    main()
