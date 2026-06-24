"""知识库管理 API：逻辑分组、文档绑定、批量上传与删除。"""

from __future__ import annotations

import sqlite3

import structlog
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from server.api.v1.documents import (
    _enqueue_document_parse,
    _get_document_status,
    _is_active_pipeline_state,
    _load_parse_options,
    _delete_one_document_index,
    _sanitize_doc_id,
)
from server.deps import get_config, get_kb_database
from server.models.schemas import (
    DocumentParseRequest,
    KnowledgeBaseCreate,
    KnowledgeBaseDetail,
    KnowledgeBaseDocumentsUpdate,
    KBDocumentInfo,
    KnowledgeBaseInfo,
    KnowledgeBaseUpdate,
)
from server.services.kb_database import KBDatabase
from server.services.minio_storage import upload_pdf_to_minio
from server.services.task_manager import get_task_manager

router = APIRouter(prefix="/knowledge-bases")
logger = structlog.get_logger(__name__)


def _file_name_for_doc_id(doc_id: str, parsed_dir: str) -> str:
    options = _load_parse_options(parsed_dir, doc_id)
    file_name = options.get("file_name") or options.get("fileName")
    if isinstance(file_name, str) and file_name.strip():
        return file_name.strip()
    return f"{doc_id}.pdf"


async def _require_kb(kb_db: KBDatabase, kb_id: str) -> dict:
    kb = await kb_db.get_kb(kb_id)
    if kb is None:
        raise HTTPException(status_code=404, detail="知识库不存在")
    return kb


async def _build_kb_detail(
    kb_db: KBDatabase,
    kb_id: str,
    config,
) -> KnowledgeBaseDetail:
    kb = await _require_kb(kb_db, kb_id)
    documents = []
    for row in await kb_db.list_documents(kb_id):
        documents.append(
            KBDocumentInfo(
                doc_id=row["doc_id"],
                file_name=row["file_name"] or _file_name_for_doc_id(
                    row["doc_id"],
                    config.parsed_dir,
                ),
                status=await _get_document_status(row["doc_id"], config),
                added_at=row["added_at"],
            )
        )
    return KnowledgeBaseDetail(**kb, documents=documents)


@router.post("", response_model=KnowledgeBaseInfo)
async def create_knowledge_base(
    payload: KnowledgeBaseCreate,
    kb_db: KBDatabase = Depends(get_kb_database),
) -> KnowledgeBaseInfo:
    try:
        kb = await kb_db.create_kb(payload.name, payload.description)
    except sqlite3.IntegrityError as exc:
        raise HTTPException(status_code=409, detail="知识库名称已存在") from exc
    return KnowledgeBaseInfo(**kb)


@router.get("", response_model=list[KnowledgeBaseInfo])
async def list_knowledge_bases(
    kb_db: KBDatabase = Depends(get_kb_database),
) -> list[KnowledgeBaseInfo]:
    return [KnowledgeBaseInfo(**row) for row in await kb_db.list_kbs()]


@router.get("/{kb_id}", response_model=KnowledgeBaseDetail)
async def get_knowledge_base(
    kb_id: str,
    config=Depends(get_config),
    kb_db: KBDatabase = Depends(get_kb_database),
) -> KnowledgeBaseDetail:
    return await _build_kb_detail(kb_db, kb_id, config)


@router.patch("/{kb_id}", response_model=KnowledgeBaseInfo)
async def update_knowledge_base(
    kb_id: str,
    payload: KnowledgeBaseUpdate,
    kb_db: KBDatabase = Depends(get_kb_database),
) -> KnowledgeBaseInfo:
    try:
        kb = await kb_db.update_kb(
            kb_id,
            name=payload.name,
            description=payload.description,
        )
    except sqlite3.IntegrityError as exc:
        raise HTTPException(status_code=409, detail="知识库名称已存在") from exc
    if kb is None:
        raise HTTPException(status_code=404, detail="知识库不存在")
    return KnowledgeBaseInfo(**kb)


@router.delete("/{kb_id}")
async def delete_knowledge_base(
    kb_id: str,
    delete_documents: bool = False,
    config=Depends(get_config),
    kb_db: KBDatabase = Depends(get_kb_database),
) -> dict:
    await _require_kb(kb_db, kb_id)
    doc_ids = await kb_db.get_kb_doc_ids(kb_id)
    exclusive_doc_ids = set(await kb_db.get_exclusive_doc_ids(kb_id))

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
            detail=f"知识库内文档正在解析中，无法删除: {', '.join(blocked)}",
        )

    deleted_metadata = await kb_db.delete_kb(kb_id)
    deleted_documents = []
    kept_shared = sorted(set(doc_ids) - exclusive_doc_ids)
    if delete_documents:
        for doc_id in sorted(exclusive_doc_ids):
            deleted_documents.append(await _delete_one_document_index(doc_id, config))

    return {
        "deleted": deleted_metadata,
        "delete_documents": delete_documents,
        "deleted_documents": deleted_documents,
        "kept_shared_doc_ids": kept_shared,
    }


@router.post("/{kb_id}/documents", response_model=KnowledgeBaseDetail)
async def add_knowledge_base_documents(
    kb_id: str,
    payload: KnowledgeBaseDocumentsUpdate,
    config=Depends(get_config),
    kb_db: KBDatabase = Depends(get_kb_database),
) -> KnowledgeBaseDetail:
    await _require_kb(kb_db, kb_id)
    docs = [
        (doc_id, _file_name_for_doc_id(doc_id, config.parsed_dir))
        for doc_id in payload.doc_ids
        if doc_id.strip()
    ]
    await kb_db.add_documents(kb_id, docs)
    return await _build_kb_detail(kb_db, kb_id, config)


@router.delete("/{kb_id}/documents", response_model=KnowledgeBaseDetail)
async def remove_knowledge_base_documents(
    kb_id: str,
    payload: KnowledgeBaseDocumentsUpdate,
    config=Depends(get_config),
    kb_db: KBDatabase = Depends(get_kb_database),
) -> KnowledgeBaseDetail:
    await _require_kb(kb_db, kb_id)
    await kb_db.remove_documents(kb_id, payload.doc_ids)
    return await _build_kb_detail(kb_db, kb_id, config)


@router.post("/{kb_id}/upload")
async def upload_knowledge_base_documents(
    kb_id: str,
    files: list[UploadFile] = File(...),
    context_summary_enabled: bool | None = Form(None, alias="contextSummaryEnabled"),
    context_summary_enabled_legacy: bool | None = Form(
        None,
        alias="context_summary_enabled",
    ),
    config=Depends(get_config),
    kb_db: KBDatabase = Depends(get_kb_database),
) -> dict:
    await _require_kb(kb_db, kb_id)
    summary_enabled = (
        context_summary_enabled
        if context_summary_enabled is not None
        else context_summary_enabled_legacy
        if context_summary_enabled_legacy is not None
        else True
    )

    uploaded = []
    errors = []
    bucket = "eurocode"
    for file in files:
        if not file.filename or not file.filename.lower().endswith(".pdf"):
            errors.append({"file_name": file.filename or "", "error": "只接受 PDF 文件"})
            continue

        doc_id = _sanitize_doc_id(file.filename)
        if not doc_id:
            errors.append({"file_name": file.filename, "error": "无效的文件名"})
            continue

        tm = get_task_manager()
        state = tm.get_status_or_persisted(doc_id, config.parsed_dir)
        if _is_active_pipeline_state(state):
            errors.append(
                {
                    "doc_id": doc_id,
                    "file_name": file.filename,
                    "error": "文档正在解析中",
                }
            )
            continue

        content = await file.read()
        if not content:
            errors.append(
                {
                    "doc_id": doc_id,
                    "file_name": file.filename,
                    "error": "PDF 文件不能为空",
                }
            )
            continue

        object_name = f"uploads/{doc_id}.pdf"
        try:
            minio_path = upload_pdf_to_minio(
                bucket=bucket,
                object_name=object_name,
                content=content,
                config=config,
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
        except HTTPException as exc:
            errors.append(
                {
                    "doc_id": doc_id,
                    "file_name": file.filename,
                    "error": str(exc.detail),
                }
            )
            continue
        except Exception:
            logger.exception("kb_upload_failed", kb_id=kb_id, doc_id=doc_id)
            errors.append(
                {
                    "doc_id": doc_id,
                    "file_name": file.filename,
                    "error": "文档上传失败",
                }
            )
            continue

        await kb_db.add_documents(kb_id, [(doc_id, file.filename)])
        uploaded.append(
            {
                "doc_id": parse_response.doc_id,
                "file_name": file.filename,
                "minio_path": minio_path,
                "status": parse_response.status,
                "message": parse_response.message,
            }
        )

    return {
        "kb_id": kb_id,
        "uploaded": uploaded,
        "errors": errors,
        "knowledge_base": await _build_kb_detail(kb_db, kb_id, config),
    }
