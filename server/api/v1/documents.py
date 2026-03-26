"""GET /api/v1/documents — document list + page preview."""
from __future__ import annotations

from pathlib import Path

import fitz
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from server.deps import get_config
from server.models.schemas import DocumentInfo

router = APIRouter()


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
                ))
                doc.close()
            except Exception:
                pass
    return docs


@router.get("/documents/{doc_id}/page/{page}")
async def get_page_image(doc_id: str, page: int, config=Depends(get_config)) -> Response:
    pdf_path = Path(config.pdf_dir) / f"{doc_id}.pdf"
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
