"""文档管理 API：列表、上传、处理、状态、删除、页面预览。"""

from __future__ import annotations

import asyncio
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

import fitz
import structlog
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response, StreamingResponse

from server.deps import get_config, invalidate_retriever_cache
from server.models.schemas import (
    DeletedChunks,
    DocumentDeleteBatchRequest,
    DocumentDeleteBatchResponse,
    DocumentDeleteError,
    DocumentDeleteItem,
    DocumentInfo,
    DocumentParseBatchRequest,
    DocumentParseBatchResponse,
    DocumentParseFileItem,
    DocumentParseQueueResponse,
    DocumentParseRequest,
    DocumentParseResponse,
    DocumentParseResultItem,
    DocumentStatusBatchRequest,
    DocumentStatusBatchResponse,
    DocumentStatusError,
    DocumentStatusItem,
    DocumentStatus,
    DocumentUploadResponse,
    DocumentUploadToMinioResponse,
    DocumentProcessResponse,
)
from server.services.task_manager import (
    MAX_FILES_PER_PARSE_REQUEST,
    PipelineStage,
    get_task_manager,
)
from server.services.minio_storage import download_pdf_from_minio, upload_pdf_to_minio
from shared.elasticsearch_client import build_async_elasticsearch

router = APIRouter()
logger = structlog.get_logger(__name__)

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


def _normalize_pdf_lookup_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def _resolve_pdf_path(doc_id: str, pdf_dir: str) -> Path | None:
    """Resolve local PDF paths across current and legacy document id shapes."""
    pdf_dir_path = Path(pdf_dir)
    raw_doc_id = doc_id.strip()
    candidates = [
        raw_doc_id,
        Path(raw_doc_id).stem if raw_doc_id.lower().endswith(".pdf") else raw_doc_id,
        _sanitize_doc_id(raw_doc_id),
    ]
    if raw_doc_id.lower().endswith("_pdf"):
        candidates.append(raw_doc_id[:-4])

    for candidate in dict.fromkeys(filter(None, candidates)):
        pdf_path = _get_pdf_path(candidate, pdf_dir)
        if pdf_path.is_file():
            return pdf_path

    if not pdf_dir_path.is_dir():
        return None

    target_keys = {
        _normalize_pdf_lookup_key(candidate) for candidate in candidates if candidate
    }
    for pdf_path in sorted(pdf_dir_path.glob("*.pdf")):
        path_keys = {
            _normalize_pdf_lookup_key(pdf_path.stem),
            _normalize_pdf_lookup_key(pdf_path.name),
        }
        if target_keys & path_keys and pdf_path.is_file():
            return pdf_path
    return None


def _pdf_lookup_candidates(doc_id: str) -> list[str]:
    raw_doc_id = doc_id.strip()
    candidates = [
        raw_doc_id,
        Path(raw_doc_id).stem if raw_doc_id.lower().endswith(".pdf") else raw_doc_id,
        _sanitize_doc_id(raw_doc_id),
    ]
    if raw_doc_id.lower().endswith("_pdf"):
        candidates.append(raw_doc_id[:-4])
    return list(dict.fromkeys(filter(None, candidates)))


def _load_parse_options(parsed_dir: str, doc_id: str) -> dict:
    for candidate in _pdf_lookup_candidates(doc_id):
        options_path = Path(parsed_dir) / candidate / "parse_options.json"
        if not options_path.is_file():
            continue
        try:
            payload = json.loads(options_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            logger.warning("parse_options_load_failed", path=str(options_path))
            continue
        if isinstance(payload, dict):
            return payload
    return {}


def _minio_candidates_for_doc_id(doc_id: str, parsed_dir: str) -> list[str]:
    options = _load_parse_options(parsed_dir, doc_id)
    candidates: list[str] = []
    minio_path = options.get("minio_path") or options.get("minioPath")
    if isinstance(minio_path, str) and minio_path.strip():
        candidates.append(minio_path.strip())

    file_name = options.get("file_name") or options.get("fileName")
    if isinstance(file_name, str) and file_name.strip():
        sanitized_file_name = _sanitize_doc_id(file_name)
        if sanitized_file_name:
            candidates.append(f"eurocode/uploads/{sanitized_file_name}.pdf")

    for candidate in _pdf_lookup_candidates(doc_id):
        candidates.append(f"eurocode/uploads/{candidate}.pdf")
    return list(dict.fromkeys(candidates))


def _resolve_pdf_path_with_minio(doc_id: str, config) -> Path | None:
    pdf_path = _resolve_pdf_path(doc_id, config.pdf_dir)
    if pdf_path is not None:
        return pdf_path

    target_candidates = _pdf_lookup_candidates(doc_id)
    target_name = target_candidates[0] if target_candidates else doc_id.strip()
    if target_name.lower().endswith(".pdf"):
        target_name = Path(target_name).stem
    target_path = _get_pdf_path(target_name, config.pdf_dir)
    for minio_path in _minio_candidates_for_doc_id(doc_id, config.parsed_dir):
        try:
            download_pdf_from_minio(
                minio_path=minio_path,
                destination=target_path,
                config=config,
            )
        except ValueError:
            continue
        except Exception:
            logger.warning(
                "document_pdf_minio_download_failed",
                doc_id=doc_id,
                minio_path=minio_path,
            )
            continue
        if target_path.is_file():
            return target_path
    return None


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
    return getattr(state, "stage", None) not in {
        PipelineStage.READY,
        PipelineStage.ERROR,
    }


def _ensure_documents_deletable(doc_ids: list[str], config) -> None:
    """Raise when any requested document is still being processed."""
    tm = get_task_manager()
    blocked = [
        doc_id
        for doc_id in doc_ids
        if _is_active_pipeline_state(
            tm.get_status_or_persisted(doc_id, config.parsed_dir)
        )
    ]
    if blocked:
        raise HTTPException(
            status_code=409,
            detail=f"文档正在解析中，无法删除: {', '.join(blocked)}",
        )


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


def _read_usage_report(doc_id: str, parsed_dir: str) -> dict[str, object]:
    """Load official token/cost report written after a parse run."""
    path = Path(parsed_dir) / doc_id / "usage.json"
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


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
    state = tm.get_status_or_persisted(doc_id, config.parsed_dir)
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
    state = tm.get_status_or_persisted(doc_id, config.parsed_dir)
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
        usage_report = _read_usage_report(doc_id, config.parsed_dir)
        return DocumentStatusItem(
            doc_id=doc_id,
            status=_normalize_external_status(status),
            progress=state.progress,
            stage=status.value,
            message=state.error or state.message or _status_message(status),
            chunk_count=_read_indexed_chunk_count(doc_id, config.parsed_dir)
            if status == DocumentStatus.READY
            else None,
            usage=usage_report.get("usage") if status == DocumentStatus.READY else None,
            cost=usage_report.get("cost") if status == DocumentStatus.READY else None,
            error=error,
        )

    pdf_path = _get_pdf_path(doc_id, config.pdf_dir)
    parsed_dir = Path(config.parsed_dir) / doc_id
    if not pdf_path.is_file() and not parsed_dir.is_dir():
        return DocumentStatusItem(
            doc_id=doc_id,
            status="not_found",
            progress=0.0,
            stage="not_found",
            message="文档不存在或尚未上传",
            error=DocumentStatusError(
                type="NOT_FOUND",
                detail="文档不存在或尚未上传",
                stage="not_found",
                timestamp=_utc_iso(),
            ),
        )

    status = await _get_document_status(doc_id, config)
    usage_report = _read_usage_report(doc_id, config.parsed_dir)
    return DocumentStatusItem(
        doc_id=doc_id,
        status=_normalize_external_status(status),
        progress=_status_progress(status),
        stage="ready" if status == DocumentStatus.READY else status.value,
        message=_status_message(status),
        chunk_count=_read_indexed_chunk_count(doc_id, config.parsed_dir)
        if status == DocumentStatus.READY
        else None,
        usage=usage_report.get("usage") if status == DocumentStatus.READY else None,
        cost=usage_report.get("cost") if status == DocumentStatus.READY else None,
        error=DocumentStatusError(
            type="INTERNAL_ERROR",
            detail="文档解析失败",
            stage="error",
            timestamp=_utc_iso(),
        )
        if status == DocumentStatus.ERROR
        else None,
    )


def _prepare_external_pdf_reference(request: DocumentParseRequest, config) -> None:
    """Download or copy the externally uploaded PDF into the pipeline PDF dir.

    Used by internal upload paths that already have the file available. The
    external batch parse endpoint defers MinIO fetch to the worker.
    """
    target_path = _get_pdf_path(request.doc_id, config.pdf_dir)
    if target_path.is_file():
        return

    source_path = Path(request.minio_path)
    if source_path.is_file():
        Path(config.pdf_dir).mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source_path, target_path)
        return

    try:
        download_pdf_from_minio(
            minio_path=request.minio_path,
            destination=target_path,
            config=config,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail="MinIO 文件读取失败") from exc


def _persist_parse_options(request: DocumentParseRequest, config) -> None:
    """Persist parse options so the worker can read them later."""
    parsed_dir = Path(config.parsed_dir) / request.doc_id
    parsed_dir.mkdir(parents=True, exist_ok=True)
    (parsed_dir / "parse_options.json").write_text(
        json.dumps(
            {
                "context_summary_enabled": request.context_summary_enabled,
                "file_name": request.file_name,
                "minio_path": request.minio_path,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def _file_item_to_parse_request(
    item: DocumentParseFileItem,
    *,
    default_context_summary_enabled: bool,
) -> DocumentParseRequest:
    context_enabled = (
        default_context_summary_enabled
        if item.context_summary_enabled is None
        else item.context_summary_enabled
    )
    return DocumentParseRequest(
        doc_id=item.doc_id.strip(),
        file_name=item.file_name.strip(),
        minio_path=item.minio_path.strip(),
        context_summary_enabled=context_enabled,
    )


def _validate_parse_file_item(
    item: DocumentParseFileItem,
    *,
    default_context_summary_enabled: bool,
) -> tuple[DocumentParseRequest | None, DocumentParseResultItem | None]:
    """Validate one batch file entry. Returns (request, rejected_result)."""
    doc_id = (item.doc_id or "").strip()
    file_name = (item.file_name or "").strip()
    minio_path = (item.minio_path or "").strip()
    if not doc_id:
        return None, DocumentParseResultItem(
            doc_id=item.doc_id or "",
            status="rejected",
            message="docId 不能为空",
            error={"type": "VALIDATION_ERROR", "detail": "docId is required"},
        )
    if not file_name:
        return None, DocumentParseResultItem(
            doc_id=doc_id,
            status="rejected",
            message="fileName 不能为空",
            error={"type": "VALIDATION_ERROR", "detail": "fileName is required"},
        )
    if not minio_path:
        return None, DocumentParseResultItem(
            doc_id=doc_id,
            status="rejected",
            message="minioPath 不能为空",
            error={"type": "VALIDATION_ERROR", "detail": "minioPath is required"},
        )
    return (
        _file_item_to_parse_request(
            DocumentParseFileItem(
                doc_id=doc_id,
                file_name=file_name,
                minio_path=minio_path,
                context_summary_enabled=item.context_summary_enabled,
            ),
            default_context_summary_enabled=default_context_summary_enabled,
        ),
        None,
    )


async def _enqueue_document_parse(
    request: DocumentParseRequest,
    config,
    *,
    prepare_pdf: bool = True,
    raise_on_active: bool = True,
) -> DocumentParseResponse:
    """Enqueue one document parse request.

    Internal upload helpers keep ``prepare_pdf=True`` and ``raise_on_active=True``.
    The external batch endpoint uses soft active handling and defers PDF fetch.
    """
    tm = get_task_manager()
    state = tm.get_status_or_persisted(request.doc_id, config.parsed_dir)
    if _is_active_pipeline_state(state):
        if raise_on_active:
            raise HTTPException(
                status_code=409, detail="该文档正在解析中，不可重复触发"
            )
        return DocumentParseResponse(
            doc_id=request.doc_id,
            status="already_processing",
            message="该文档正在解析中，未重复入队",
        )

    if prepare_pdf:
        _prepare_external_pdf_reference(request, config)
    _persist_parse_options(request, config)
    try:
        enqueued = tm.enqueue(request.doc_id)
    except RuntimeError as exc:
        if "parse queue is full" in str(exc):
            raise HTTPException(
                status_code=429, detail="解析队列已满，请稍后重试"
            ) from exc
        raise
    status = "queued" if enqueued.stage == PipelineStage.PENDING else "processing"
    return DocumentParseResponse(
        doc_id=request.doc_id,
        status=status,
        message="已加入解析队列",
    )


async def _enqueue_document_parse_batch(
    request: DocumentParseBatchRequest,
    config,
) -> DocumentParseBatchResponse:
    """Accept a batch of parse requests with per-file results."""
    tm = get_task_manager()
    results: list[DocumentParseResultItem] = []
    seen_doc_ids: set[str] = set()
    accepted_requests: list[DocumentParseRequest] = []

    for item in request.files:
        parsed_req, rejected = _validate_parse_file_item(
            item,
            default_context_summary_enabled=request.context_summary_enabled,
        )
        if rejected is not None:
            results.append(rejected)
            continue
        assert parsed_req is not None
        if parsed_req.doc_id in seen_doc_ids:
            results.append(
                DocumentParseResultItem(
                    doc_id=parsed_req.doc_id,
                    status="rejected",
                    message="请求内重复的 docId，已忽略",
                    error={
                        "type": "DUPLICATE_IN_REQUEST",
                        "detail": "duplicate docId in files[]",
                    },
                )
            )
            continue
        seen_doc_ids.add(parsed_req.doc_id)

        state = tm.get_status_or_persisted(parsed_req.doc_id, config.parsed_dir)
        if _is_active_pipeline_state(state):
            results.append(
                DocumentParseResultItem(
                    doc_id=parsed_req.doc_id,
                    status="already_processing",
                    message="该文档正在解析中，未重复入队",
                )
            )
            continue

        accepted_requests.append(parsed_req)
        # Placeholder; replaced after capacity check / enqueue.
        results.append(
            DocumentParseResultItem(
                doc_id=parsed_req.doc_id,
                status="queued",
                message="已加入解析队列",
            )
        )

    new_slots = len(accepted_requests)
    if new_slots and not tm.can_accept(new_slots):
        raise HTTPException(
            status_code=429,
            detail=(
                f"解析队列剩余名额不足：需要 {new_slots}，"
                f"剩余 {tm.remaining_slots()}（容量 {tm.capacity}）"
            ),
        )

    # Re-walk results and enqueue accepted docs in order.
    accepted_iter = iter(accepted_requests)
    final_results: list[DocumentParseResultItem] = []
    for item in results:
        if item.status != "queued":
            final_results.append(item)
            continue
        parsed_req = next(accepted_iter)
        response = await _enqueue_document_parse(
            parsed_req,
            config,
            prepare_pdf=False,
            raise_on_active=False,
        )
        final_results.append(
            DocumentParseResultItem(
                doc_id=response.doc_id,
                status=response.status,
                message=response.message,
            )
        )

    return DocumentParseBatchResponse(results=final_results)


async def _delete_one_document(doc_id: str, config) -> DocumentDeleteItem:
    """Delete one document and return an external-contract result item."""
    tm = get_task_manager()
    state = tm.get_status_or_persisted(doc_id, config.parsed_dir)
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
    await _remove_document_from_kbs(doc_id)
    await invalidate_retriever_cache()

    return DocumentDeleteItem(
        doc_id=doc_id,
        deleted=True,
        deleted_chunks=DeletedChunks(**deleted),
    )


async def _delete_one_document_index(doc_id: str, config) -> DocumentDeleteItem:
    """Delete indexed data for one doc_id, regardless of local PDF state."""
    tm = get_task_manager()
    state = tm.get_status_or_persisted(doc_id, config.parsed_dir)
    if _is_active_pipeline_state(state):
        return DocumentDeleteItem(
            doc_id=doc_id,
            deleted=False,
            error=DocumentDeleteError(
                code="CONFLICT",
                message="文档正在解析中，无法删除",
            ),
        )

    try:
        from pipeline.config import PipelineConfig
        from pipeline.index import delete_document_sources

        pipeline_config = PipelineConfig()
        deleted = await delete_document_sources(
            _source_names_for_doc_id(doc_id),
            pipeline_config,
        )

        await invalidate_retriever_cache()
        await _remove_document_from_kbs(doc_id)
    except Exception:
        logger.exception("document_index_delete_failed", doc_id=doc_id)
        return DocumentDeleteItem(
            doc_id=doc_id,
            deleted=False,
            error=DocumentDeleteError(
                code="INTERNAL_ERROR",
                message="文档删除失败",
            ),
        )

    return DocumentDeleteItem(
        doc_id=doc_id,
        deleted=True,
        deleted_chunks=DeletedChunks(
            milvus=int(deleted.get("milvus", 0) or 0),
            elasticsearch=int(deleted.get("elasticsearch", 0) or 0),
        ),
    )


async def _remove_document_from_kbs(doc_id: str) -> None:
    try:
        from server.deps import get_kb_database

        await get_kb_database().remove_document_everywhere(doc_id)
    except RuntimeError:
        return
    except Exception:
        logger.warning("kb_document_cleanup_failed", doc_id=doc_id, exc_info=True)


# -- 文档列表 --


@router.get("/documents", response_model=list[DocumentInfo])
async def list_documents(config=Depends(get_config)) -> list[DocumentInfo]:
    pdf_dir = Path(config.pdf_dir)
    docs = []
    if pdf_dir.exists():
        for pdf_path in sorted(pdf_dir.glob("*.pdf")):
            try:
                doc = fitz.open(str(pdf_path))
                usage_report = _read_usage_report(pdf_path.stem, config.parsed_dir)
                usage = usage_report.get("usage")
                cost = usage_report.get("cost")
                docs.append(
                    DocumentInfo(
                        id=pdf_path.stem,
                        name=pdf_path.stem.replace("_", " "),
                        title=doc.metadata.get("title", pdf_path.stem),
                        total_pages=len(doc),
                        chunk_count=0,
                        status=await _get_document_status(pdf_path.stem, config),
                        usage=usage if isinstance(usage, dict) else None,
                        cost=cost if isinstance(cost, dict) else None,
                    )
                )
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


@router.post("/documents/upload-to-minio", response_model=DocumentUploadToMinioResponse)
async def upload_document_to_minio(
    file: UploadFile = File(...),
    context_summary_enabled: bool | None = Form(None, alias="contextSummaryEnabled"),
    context_summary_enabled_legacy: bool | None = Form(
        None,
        alias="context_summary_enabled",
    ),
    config=Depends(get_config),
) -> DocumentUploadToMinioResponse:
    """Upload a PDF through the backend proxy and trigger parsing."""
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "只接受 PDF 文件")

    doc_id = _sanitize_doc_id(file.filename)
    if not doc_id:
        raise HTTPException(400, "无效的文件名")

    content = await file.read()
    if not content:
        raise HTTPException(400, "PDF 文件不能为空")

    bucket = "eurocode"
    object_name = f"uploads/{doc_id}.pdf"
    try:
        minio_path = upload_pdf_to_minio(
            bucket=bucket,
            object_name=object_name,
            content=content,
            config=config,
        )
    except Exception as exc:
        raise HTTPException(status_code=503, detail="MinIO 文件上传失败") from exc

    summary_enabled = (
        context_summary_enabled
        if context_summary_enabled is not None
        else context_summary_enabled_legacy
        if context_summary_enabled_legacy is not None
        else True
    )
    parse_response = await _enqueue_document_parse(
        DocumentParseRequest(
            docId=doc_id,
            fileName=file.filename,
            minioPath=minio_path,
            contextSummaryEnabled=summary_enabled,
        ),
        config,
    )
    return DocumentUploadToMinioResponse(
        doc_id=parse_response.doc_id,
        file_name=file.filename,
        minio_path=minio_path,
        status=parse_response.status,
        message=parse_response.message,
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
            contextSummaryEnabled=True,
        ),
        config,
    )
    return DocumentProcessResponse(
        doc_id=response.doc_id,
        stage="pending",
        message=response.message,
    )


@router.post("/documents/parse", response_model=DocumentParseBatchResponse)
async def parse_document(
    request: DocumentParseBatchRequest,
    config=Depends(get_config),
) -> DocumentParseBatchResponse:
    """批量触发 PDF 解析（外部契约：仅 files[]）。"""
    if len(request.files) > MAX_FILES_PER_PARSE_REQUEST:
        raise HTTPException(
            status_code=400,
            detail=f"files 上限为 {MAX_FILES_PER_PARSE_REQUEST} 个",
        )
    return await _enqueue_document_parse_batch(request, config)


@router.get("/documents/parse-queue", response_model=DocumentParseQueueResponse)
async def get_parse_queue() -> DocumentParseQueueResponse:
    """查询解析队列占用与剩余可提交名额。"""
    stats = get_task_manager().get_queue_stats()
    return DocumentParseQueueResponse(**stats)


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
    _ensure_documents_deletable(request.doc_ids, config)

    try:
        from pipeline.config import PipelineConfig
        from pipeline.index import delete_document_sources

        pipeline_config = PipelineConfig()
        source_names = [
            source_name
            for doc_id in request.doc_ids
            for source_name in _source_names_for_doc_id(doc_id)
        ]
        deleted = await delete_document_sources(source_names, pipeline_config)
        await invalidate_retriever_cache()
    except Exception:
        logger.exception("document_batch_delete_failed", doc_ids=request.doc_ids)
        raise HTTPException(status_code=500, detail="文档删除失败")

    deleted_chunks = DeletedChunks(
        milvus=int(deleted.get("milvus", 0) or 0),
        elasticsearch=int(deleted.get("elasticsearch", 0) or 0),
    )
    if deleted_chunks.milvus == 0 and deleted_chunks.elasticsearch == 0:
        raise HTTPException(status_code=404, detail="文档不存在")

    return DocumentDeleteBatchResponse(
        deleted=True,
        deleted_chunks=deleted_chunks,
    )


# -- SSE 状态流 --


@router.get("/documents/{doc_id}/status")
async def document_status_stream(doc_id: str, config=Depends(get_config)):
    """SSE 端点：推送 pipeline 处理进度。"""
    tm = get_task_manager()

    async def event_generator():
        queue = tm.subscribe(doc_id, config.parsed_dir)
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=30.0)
                    data = json.dumps(
                        {
                            "doc_id": event.doc_id,
                            "stage": event.stage.value,
                            "progress": event.progress,
                            "message": event.message,
                            "error": event.error,
                        },
                        ensure_ascii=False,
                    )
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
        raise HTTPException(
            status_code, result.error.message if result.error else "删除失败"
        )

    deleted = result.deleted_chunks or DeletedChunks(milvus=0, elasticsearch=0)

    return {
        "doc_id": doc_id,
        "deleted_milvus": deleted.milvus,
        "deleted_elasticsearch": deleted.elasticsearch,
    }


# -- 页面预览 --


@router.get("/documents/{doc_id}/page/{page}")
async def get_page_image(
    doc_id: str, page: int, config=Depends(get_config)
) -> Response:
    pdf_path = _resolve_pdf_path_with_minio(doc_id, config)
    if pdf_path is None:
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
    pdf_path = _resolve_pdf_path_with_minio(doc_id, config)
    if pdf_path is None:
        raise HTTPException(404, f"Document {doc_id} not found")

    return Response(content=pdf_path.read_bytes(), media_type="application/pdf")
