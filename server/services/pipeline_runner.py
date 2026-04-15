"""桥接 pipeline 模块到 server：单文档 pipeline 执行器。"""
from __future__ import annotations

import inspect
import json
from collections.abc import Awaitable, Callable
from pathlib import Path

import structlog

from pipeline.chunk import create_chunks
from pipeline.config import PipelineConfig
from pipeline.content_list import content_list_output_name
from pipeline.index import (
    delete_document_chunks,
    index_to_elasticsearch,
    index_to_milvus,
)
from pipeline.parse import parse_pdf
from pipeline.structure import (
    TreePruningConfig,
    parse_markdown_to_tree,
    prune_document_tree,
)
from pipeline.summarize import enrich_chunk_summaries
from server.deps import invalidate_retriever_cache

logger = structlog.get_logger()

_INDEX_READY_SENTINEL = ".indexed"

ProgressCallback = Callable[[str, float, str], Awaitable[None] | None]


async def _emit(
    on_progress: ProgressCallback | None,
    stage: str,
    progress: float,
    message: str,
) -> None:
    """统一调用进度回调，兼容 sync/async callback。"""
    if on_progress is None:
        return
    result = on_progress(stage, max(0.0, min(1.0, progress)), message)
    if inspect.isawaitable(result):
        await result


def _load_content_list(md_path: Path, meta: dict) -> object | None:
    output_name = meta.get("content_list_output")
    if not isinstance(output_name, str) or not output_name.strip():
        output_name = content_list_output_name(md_path.stem)
    cl_path = md_path.parent / output_name
    if not cl_path.is_file():
        return None
    return json.loads(cl_path.read_text(encoding="utf-8"))


async def run_single_document(
    doc_id: str,
    pipeline_config: PipelineConfig,
    on_progress: ProgressCallback | None = None,
) -> dict[str, int]:
    """对单个文档执行完整的 parse → structure → chunk → summarize → index 流程。"""
    pdf_dir = Path(pipeline_config.pdf_dir)
    pdf_path = pdf_dir / f"{doc_id}.pdf"
    output_dir = Path(pipeline_config.parsed_dir) / doc_id
    ready_marker = output_dir / _INDEX_READY_SENTINEL
    source_name = doc_id.replace("_", " ")

    if not pdf_path.is_file():
        raise FileNotFoundError(f"PDF 文件不存在: {pdf_path}")

    # Rebuilds must earn readiness again after Stage 4 completes.
    ready_marker.unlink(missing_ok=True)

    # Stage 1: MinerU 解析
    await _emit(on_progress, "parsing", 0.05, f"正在解析 {pdf_path.name}")
    md_path = await parse_pdf(pdf_path, output_dir, pipeline_config)

    # Stage 2: 结构化
    await _emit(on_progress, "structuring", 0.25, "正在构建文档树")
    markdown = md_path.read_text(encoding="utf-8")
    meta_path = output_dir / f"{doc_id}_meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.is_file() else {}
    content_list = _load_content_list(md_path, meta)
    source_title = str(meta.get("title") or source_name)

    pruning_config = TreePruningConfig.from_pipeline_settings(
        enabled=pipeline_config.tree_pruning_enabled,
        body_start_titles=pipeline_config.tree_pruning_body_start_titles,
    )
    raw_tree = parse_markdown_to_tree(
        markdown, source=source_name, content_list=content_list,
    )
    tree = prune_document_tree(raw_tree, pruning_config)

    # Stage 3: 分块
    await _emit(on_progress, "chunking", 0.50, "正在创建文档块")
    chunks = create_chunks(tree, source_title=source_title)

    # Stage 3.5: LLM 摘要
    await _emit(on_progress, "summarizing", 0.60, "正在生成特殊元素摘要")

    def _on_summary_progress(payload: dict) -> None:
        total = int(payload.get("total", 0) or 0)
        completed = int(payload.get("completed", 0) or 0)
        ratio = completed / total if total else 1.0
        overall = 0.60 + 0.25 * ratio
        if on_progress is not None:
            import asyncio
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(_emit(
                    on_progress, "summarizing", overall,
                    f"已摘要 {completed}/{total} 个特殊块",
                ))

    chunks = await enrich_chunk_summaries(
        chunks, pipeline_config, progress_callback=_on_summary_progress,
    )

    # Stage 4: 索引（先删旧再插新）
    await _emit(on_progress, "indexing", 0.88, "正在清理旧索引并写入新数据")
    deleted = await delete_document_chunks(source_name, pipeline_config)
    milvus_count = await index_to_milvus(chunks, pipeline_config)
    es_count = await index_to_elasticsearch(chunks, pipeline_config)

    # 热更新 retriever 缓存
    await invalidate_retriever_cache()
    ready_marker.write_text(
        json.dumps(
            {
                "doc_id": doc_id,
                "milvus": milvus_count,
                "elasticsearch": es_count,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    await _emit(
        on_progress, "ready", 1.0,
        f"完成: {len(chunks)} 个块已索引 (Milvus={milvus_count}, ES={es_count})",
    )

    logger.info(
        "single_document_pipeline_complete",
        doc_id=doc_id,
        chunks=len(chunks),
        deleted=deleted,
        milvus=milvus_count,
        es=es_count,
    )

    return {
        "chunks": len(chunks),
        "milvus": milvus_count,
        "elasticsearch": es_count,
        "deleted_milvus": deleted["milvus"],
        "deleted_elasticsearch": deleted["elasticsearch"],
    }
