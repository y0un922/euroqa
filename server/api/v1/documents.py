"""文档管理 API：列表、上传、处理、状态、删除、页面预览。"""
from __future__ import annotations

import asyncio
import json
import re
import shutil
from pathlib import Path

import fitz
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response, StreamingResponse

from server.deps import get_config, invalidate_retriever_cache
from server.models.schemas import (
    DocumentInfo,
    DocumentStatus,
    DocumentUploadResponse,
    DocumentProcessResponse,
)
from server.services.task_manager import get_task_manager, PipelineStage
from shared.elasticsearch_client import build_async_elasticsearch

router = APIRouter()

_INDEX_READY_SENTINEL = ".indexed"

_STAGE_TO_STATUS: dict[PipelineStage, DocumentStatus] = {
    PipelineStage.PENDING: DocumentStatus.PENDING,
    PipelineStage.PARSING: DocumentStatus.PARSING,
    PipelineStage.STRUCTURING: DocumentStatus.STRUCTURING,
    PipelineStage.CHUNKING: DocumentStatus.CHUNKING,
    PipelineStage.SUMMARIZING: DocumentStatus.SUMMARIZING,
    PipelineStage.INDEXING: DocumentStatus.INDEXING,
    PipelineStage.READY: DocumentStatus.READY,
    PipelineStage.ERROR: DocumentStatus.ERROR,
}


def _get_pdf_path(doc_id: str, pdf_dir: str) -> Path:
    return Path(pdf_dir) / f"{doc_id}.pdf"


def _sanitize_doc_id(filename: str) -> str:
    """将上传文件名转为安全的 doc_id。"""
    stem = Path(filename).stem
    return re.sub(r"[^A-Za-z0-9_\-]", "_", stem).strip("_")


def _source_names_for_doc_id(doc_id: str) -> list[str]:
    """Return current and legacy source keys for this uploaded document."""

    return list(dict.fromkeys([doc_id, doc_id.replace("_", " ")]))


async def _document_has_indexed_chunks(
    source_name: str,
    es_url: str,
    es_index: str,
) -> bool:
    """Return whether Elasticsearch already stores chunks for this source."""
    es = build_async_elasticsearch(es_url)
    try:
        if not await es.indices.exists(index=es_index):
            return False
        response = await es.count(
            index=es_index,
            body={"query": {"term": {"source": source_name}}},
        )
        return int(response.get("count", 0) or 0) > 0
    except Exception:
        return False
    finally:
        await es.close()


async def _get_document_status(doc_id: str, config) -> DocumentStatus:
    """查询 TaskManager 获取文档当前状态，若无任务状态则检查是否已完成索引。"""
    tm = get_task_manager()
    state = tm.get_status(doc_id)
    if state is not None:
        return _STAGE_TO_STATUS.get(state.stage, DocumentStatus.READY)

    # 无任务状态：只有存在索引完成标记时，才能认为文档真正可检索。
    parsed_path = Path(config.parsed_dir) / doc_id
    if (parsed_path / _INDEX_READY_SENTINEL).is_file():
        return DocumentStatus.READY
    if parsed_path.is_dir():
        for source_name in _source_names_for_doc_id(doc_id):
            if await _document_has_indexed_chunks(
                source_name,
                config.es_url,
                config.es_index,
            ):
                return DocumentStatus.READY
    return DocumentStatus.UPLOADED


# -- 文档列表 --

@router.get("/documents", response_model=list[DocumentInfo])
async def list_documents(config=Depends(get_config)) -> list[DocumentInfo]:
    pdf_dir = Path(config.pdf_dir)
    docs = []
    if pdf_dir.exists():
        for pdf_path in sorted(pdf_dir.glob("*.pdf")):
            try:
                doc = fitz.open(str(pdf_path))
                docs.append(DocumentInfo(
                    id=pdf_path.stem,
                    name=pdf_path.stem.replace("_", " "),
                    title=doc.metadata.get("title", pdf_path.stem),
                    total_pages=len(doc),
                    chunk_count=0,
                    status=await _get_document_status(pdf_path.stem, config),
                ))
                doc.close()
            except Exception:
                pass
    return docs


# -- 上传 --

@router.post("/documents/upload", response_model=DocumentUploadResponse)
async def upload_document(
    file: UploadFile = File(...),
    config=Depends(get_config),
) -> DocumentUploadResponse:
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "只接受 PDF 文件")

    doc_id = _sanitize_doc_id(file.filename)
    if not doc_id:
        raise HTTPException(400, "无效的文件名")

    pdf_path = _get_pdf_path(doc_id, config.pdf_dir)
    if pdf_path.exists():
        raise HTTPException(409, f"文档 {doc_id} 已存在")

    Path(config.pdf_dir).mkdir(parents=True, exist_ok=True)
    content = await file.read()
    pdf_path.write_bytes(content)

    try:
        doc = fitz.open(str(pdf_path))
        title = doc.metadata.get("title", doc_id)
        total_pages = len(doc)
        doc.close()
    except Exception:
        pdf_path.unlink(missing_ok=True)
        raise HTTPException(400, "无法解析 PDF 文件")

    return DocumentUploadResponse(
        doc_id=doc_id,
        name=doc_id.replace("_", " "),
        title=title,
        total_pages=total_pages,
    )


# -- 触发处理 --

@router.post("/documents/{doc_id}/process", response_model=DocumentProcessResponse)
async def process_document(doc_id: str, config=Depends(get_config)):
    pdf_path = _get_pdf_path(doc_id, config.pdf_dir)
    if not pdf_path.is_file():
        raise HTTPException(404, f"文档 {doc_id} 不存在")

    tm = get_task_manager()
    state = tm.get_status(doc_id)
    if state is not None and state.stage not in {PipelineStage.READY, PipelineStage.ERROR}:
        raise HTTPException(409, f"文档 {doc_id} 正在处理中")

    tm.enqueue(doc_id)
    return DocumentProcessResponse(
        doc_id=doc_id,
        stage="pending",
        message="已加入处理队列",
    )


# -- SSE 状态流 --

@router.get("/documents/{doc_id}/status")
async def document_status_stream(doc_id: str):
    """SSE 端点：推送 pipeline 处理进度。"""
    tm = get_task_manager()

    async def event_generator():
        queue = tm.subscribe(doc_id)
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=30.0)
                    data = json.dumps({
                        "doc_id": event.doc_id,
                        "stage": event.stage.value,
                        "progress": event.progress,
                        "message": event.message,
                        "error": event.error,
                    }, ensure_ascii=False)
                    yield f"event: progress\ndata: {data}\n\n"
                    if event.terminal:
                        yield f"event: done\ndata: {data}\n\n"
                        return
                except asyncio.TimeoutError:
                    yield ": heartbeat\n\n"
        finally:
            tm.unsubscribe(doc_id, queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# -- 删除 --

@router.delete("/documents/{doc_id}")
async def delete_document(doc_id: str, config=Depends(get_config)):
    tm = get_task_manager()
    state = tm.get_status(doc_id)
    if state is not None and state.stage not in {PipelineStage.READY, PipelineStage.ERROR}:
        raise HTTPException(409, f"文档 {doc_id} 正在处理中，无法删除")

    pdf_path = _get_pdf_path(doc_id, config.pdf_dir)
    if not pdf_path.is_file():
        raise HTTPException(404, f"文档 {doc_id} 不存在")

    from pipeline.config import PipelineConfig
    from pipeline.index import delete_document_chunks
    pipeline_config = PipelineConfig()
    deleted = {"milvus": 0, "elasticsearch": 0}
    for source_name in _source_names_for_doc_id(doc_id):
        result = await delete_document_chunks(source_name, pipeline_config)
        deleted["milvus"] += result["milvus"]
        deleted["elasticsearch"] += result["elasticsearch"]

    parsed_dir = Path(config.parsed_dir) / doc_id
    if parsed_dir.is_dir():
        shutil.rmtree(parsed_dir)

    pdf_path.unlink(missing_ok=True)
    await invalidate_retriever_cache()

    return {
        "doc_id": doc_id,
        "deleted_milvus": deleted["milvus"],
        "deleted_elasticsearch": deleted["elasticsearch"],
    }


# -- 页面预览 --

@router.get("/documents/{doc_id}/page/{page}")
async def get_page_image(doc_id: str, page: int, config=Depends(get_config)) -> Response:
    pdf_path = _get_pdf_path(doc_id, config.pdf_dir)
    if not pdf_path.exists():
        raise HTTPException(404, f"Document {doc_id} not found")

    doc = fitz.open(str(pdf_path))
    if page < 1 or page > len(doc):
        doc.close()
        raise HTTPException(404, f"Page {page} out of range")

    pix = doc[page - 1].get_pixmap(dpi=150)
    png_bytes = pix.tobytes("png")
    doc.close()
    return Response(content=png_bytes, media_type="image/png")


@router.get("/documents/{doc_id}/file")
async def get_document_file(doc_id: str, config=Depends(get_config)) -> Response:
    pdf_path = _get_pdf_path(doc_id, config.pdf_dir)
    if not pdf_path.is_file():
        raise HTTPException(404, f"Document {doc_id} not found")

    return Response(content=pdf_path.read_bytes(), media_type="application/pdf")
