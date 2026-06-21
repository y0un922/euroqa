"""Index administration API for Milvus and Elasticsearch."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel

from server.services import index_admin

router = APIRouter(prefix="/index-admin")


class RebuildIndexRequest(BaseModel):
    delete_first: bool = True


class IndexOperationResponse(BaseModel):
    code: int = 200
    message: str = "ok"
    data: dict[str, Any]


@router.get("/overview", response_model=IndexOperationResponse)
async def get_index_overview() -> IndexOperationResponse:
    """Return Milvus/Elasticsearch index overview and source aggregates."""
    return IndexOperationResponse(data=await index_admin.index_overview())


@router.get("/documents/{doc_id}", response_model=IndexOperationResponse)
async def inspect_document_index(
    doc_id: str,
    sample_size: int = Query(default=5, ge=0, le=50),
) -> IndexOperationResponse:
    """Inspect one document's indexed chunks and sample ES documents."""
    return IndexOperationResponse(
        data=await index_admin.inspect_document_index(
            doc_id,
            sample_size=sample_size,
        )
    )


@router.delete("/documents/{doc_id}", response_model=IndexOperationResponse)
async def delete_document_index(doc_id: str) -> IndexOperationResponse:
    """Delete one document from Milvus and Elasticsearch indexes only."""
    return IndexOperationResponse(
        data=await index_admin.delete_document_index(doc_id),
        message="deleted",
    )


@router.post("/documents/{doc_id}/rebuild", response_model=IndexOperationResponse)
async def rebuild_document_index(
    doc_id: str,
    request: RebuildIndexRequest = RebuildIndexRequest(),
) -> IndexOperationResponse:
    """Rebuild one document index from data/parsed without reparsing PDF."""
    return IndexOperationResponse(
        data=await index_admin.rebuild_document_index(
            doc_id,
            delete_first=request.delete_first,
        ),
        message="rebuilt",
    )
