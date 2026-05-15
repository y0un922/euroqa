"""文档管理 API：列表、上传、处理、状态、删除、页面预览。"""
from __future__ import annotations

import asyncio
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

import fitz
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response, StreamingResponse

from server.deps import get_config, invalidate_retriever_cache
from server.models.schemas import (
    DeletedChunks,
    DocumentDeleteBatchRequest,
    DocumentDeleteBatchResponse,
    DocumentDeleteError,
    DocumentDeleteItem,
    DocumentInfo,
    DocumentParseRequest,
    DocumentParseResponse,
    DocumentStatusBatchRequest,
    DocumentStatusBatchResponse,
    DocumentStatusError,
    DocumentStatusItem,
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


def _is_active_pipeline_state(state: object | None) -> bool:
    """Return whether a task-manager state is still processing."""
    if state is None:
        return False
    return getattr(state, "stage", None) not in {PipelineStage.READY, PipelineStage.ERROR}


def _utc_iso() -> str:
    """Return an ISO 8601 UTC timestamp for external API payloads."""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _normalize_external_status(status: DocumentStatus) -> str:
    """Map internal document states to the external API contract."""
    if status == DocumentStatus.READY:
        return "success"
    if status == DocumentStatus.ERROR:
        return "failed"
    return "processing"


def _status_progress(status: DocumentStatus) -> float:
    """Return a stable progress value for internal document states."""
    progress_map = {
        DocumentStatus.UPLOADED: 0.0,
        DocumentStatus.PENDING: 0.0,
        DocumentStatus.PARSING: 0.05,
        DocumentStatus.STRUCTURING: 0.25,
        DocumentStatus.CHUNKING: 0.50,
        DocumentStatus.SUMMARIZING: 0.60,
        DocumentStatus.INDEXING: 0.88,
        DocumentStatus.READY: 1.0,
        DocumentStatus.ERROR: 1.0,
    }
    return progress_map.get(status, 0.0)


def _status_message(status: DocumentStatus) -> str:
    """Return a human-readable status message for the external contract."""
    messages = {
        DocumentStatus.UPLOADED: "已上传，等待解析",
        DocumentStatus.PENDING: "排队等待处理",
        DocumentStatus.PARSING: "正在解析 PDF",
        DocumentStatus.STRUCTURING: "正在构建文档结构",
        DocumentStatus.CHUNKING: "正在分块处理",
        DocumentStatus.SUMMARIZING: "正在生成特殊元素摘要",
        DocumentStatus.INDEXING: "正在写入索引",
        DocumentStatus.READY: "解析完成",
        DocumentStatus.ERROR: "解析失败",
    }
    return messages.get(status, "正在处理")


def _read_indexed_chunk_count(doc_id: str, parsed_dir: str) -> int | None:
    """Read indexed chunk count from the ready sentinel when available."""
    marker = Path(parsed_dir) / doc_id / _INDEX_READY_SENTINEL
    if not marker.is_file():
        return None
    try:
        data = json.loads(marker.read_text(encoding="utf-8"))
        value = data.get("milvus") or data.get("elasticsearch")
        return int(value) if value is not None else None
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return None


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


async def _build_external_document_status(doc_id: str, config) -> DocumentStatusItem:
    """Build one batch status item using the interface-document contract."""
    tm = get_task_manager()
    state = tm.get_status(doc_id)
    if state is not None:
        status = _STAGE_TO_STATUS.get(state.stage, DocumentStatus.READY)
        error = None
        if status == DocumentStatus.ERROR:
            error = DocumentStatusError(
                type="INTERNAL_ERROR",
                detail=state.error or "文档解析失败",
                stage=status.value,
                timestamp=_utc_iso(),
            )
        return DocumentStatusItem(
            doc_id=doc_id,
            status=_normalize_external_status(status),
            progress=state.progress,
            stage=status.value,
            message=state.error or _status_message(status),
            chunk_count=_read_indexed_chunk_count(doc_id, config.parsed_dir)
            if status == DocumentStatus.READY else None,
            error=error,
        )

    pdf_path = _get_pdf_path(doc_id, config.pdf_dir)
    parsed_dir = Path(config.parsed_dir) / doc_id
    if not pdf_path.is_file() and not parsed_dir.is_dir():
        return DocumentStatusItem(
            doc_id=doc_id,
            status="failed",
            progress=0.0,
            stage="error",
            message="文档不存在",
            error=DocumentStatusError(
                type="NOT_FOUND",
                detail="文档不存在",
                stage="error",
                timestamp=_utc_iso(),
            ),
        )

    status = await _get_document_status(doc_id, config)
    return DocumentStatusItem(
        doc_id=doc_id,
        status=_normalize_external_status(status),
        progress=_status_progress(status),
        stage="ready" if status == DocumentStatus.READY else status.value,
        message=_status_message(status),
        chunk_count=_read_indexed_chunk_count(doc_id, config.parsed_dir)
        if status == DocumentStatus.READY else None,
        error=DocumentStatusError(
            type="INTERNAL_ERROR",
            detail="文档解析失败",
            stage="error",
            timestamp=_utc_iso(),
        ) if status == DocumentStatus.ERROR else None,
    )


def _prepare_external_pdf_reference(request: DocumentParseRequest, config) -> None:
    """Make locally visible MinIO/object-path files available to the pipeline."""
    target_path = _get_pdf_path(request.doc_id, config.pdf_dir)
    if target_path.is_file():
        return

    source_path = Path(request.minio_path)
    if source_path.is_file():
        Path(config.pdf_dir).mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source_path, target_path)


async def _enqueue_document_parse(
    request: DocumentParseRequest,
    config,
) -> DocumentParseResponse:
    """Enqueue one document parse request using the external contract."""
    tm = get_task_manager()
    state = tm.get_status(request.doc_id)
    if _is_active_pipeline_state(state):
        raise HTTPException(status_code=409, detail="该文档正在解析中，不可重复触发")

    _prepare_external_pdf_reference(request, config)
    tm.enqueue(request.doc_id)
    return DocumentParseResponse(
        doc_id=request.doc_id,
        status="processing",
        message="已加入解析队列",
    )


async def _delete_one_document(doc_id: str, config) -> DocumentDeleteItem:
    """Delete one document and return an external-contract result item."""
    tm = get_task_manager()
    state = tm.get_status(doc_id)
    if _is_active_pipeline_state(state):
        return DocumentDeleteItem(
            doc_id=doc_id,
            deleted=False,
            error=DocumentDeleteError(
                code="CONFLICT",
                message="文档正在解析中，无法删除",
            ),
        )

    pdf_path = _get_pdf_path(doc_id, config.pdf_dir)
    parsed_dir = Path(config.parsed_dir) / doc_id
    if not pdf_path.is_file() and not parsed_dir.is_dir():
        return DocumentDeleteItem(
            doc_id=doc_id,
            deleted=False,
            error=DocumentDeleteError(code="NOT_FOUND", message="文档不存在"),
        )

    from pipeline.config import PipelineConfig
    from pipeline.index import delete_document_chunks

    pipeline_config = PipelineConfig()
    deleted = {"milvus": 0, "elasticsearch": 0}
    for source_name in _source_names_for_doc_id(doc_id):
        result = await delete_document_chunks(source_name, pipeline_config)
        deleted["milvus"] += int(result.get("milvus", 0) or 0)
        deleted["elasticsearch"] += int(result.get("elasticsearch", 0) or 0)

    if parsed_dir.is_dir():
        shutil.rmtree(parsed_dir)

    pdf_path.unlink(missing_ok=True)
    await invalidate_retriever_cache()

    return DocumentDeleteItem(
        doc_id=doc_id,
        deleted=True,
        deleted_chunks=DeletedChunks(**deleted),
    )


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

    response = await _enqueue_document_parse(
        DocumentParseRequest(
            docId=doc_id,
            fileName=f"{doc_id}.pdf",
            minioPath=str(pdf_path),
        ),
        config,
    )
    return DocumentProcessResponse(
        doc_id=response.doc_id,
        stage="pending",
        message=response.message,
    )


@router.post("/documents/parse", response_model=DocumentParseResponse)
async def parse_document(
    request: DocumentParseRequest,
    config=Depends(get_config),
) -> DocumentParseResponse:
    """触发 PDF 解析，符合外部接口文档契约。"""
    return await _enqueue_document_parse(request, config)


@router.post("/documents/status", response_model=DocumentStatusBatchResponse)
async def batch_document_status(
    request: DocumentStatusBatchRequest,
    config=Depends(get_config),
) -> DocumentStatusBatchResponse:
    """批量查询文档解析状态。"""
    results = [
        await _build_external_document_status(doc_id, config)
        for doc_id in request.doc_ids
    ]
    return DocumentStatusBatchResponse(results=results)


@router.post("/documents/delete", response_model=DocumentDeleteBatchResponse)
async def batch_delete_documents(
    request: DocumentDeleteBatchRequest,
    config=Depends(get_config),
) -> DocumentDeleteBatchResponse:
    """批量删除文档索引数据。"""
    results = [await _delete_one_document(doc_id, config) for doc_id in request.doc_ids]
    return DocumentDeleteBatchResponse(results=results)


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
    result = await _delete_one_document(doc_id, config)
    if not result.deleted:
        status_code = 409 if result.error and result.error.code == "CONFLICT" else 404
        raise HTTPException(status_code, result.error.message if result.error else "删除失败")

    deleted = result.deleted_chunks or DeletedChunks(milvus=0, elasticsearch=0)

    return {
        "doc_id": doc_id,
        "deleted_milvus": deleted.milvus,
        "deleted_elasticsearch": deleted.elasticsearch,
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
