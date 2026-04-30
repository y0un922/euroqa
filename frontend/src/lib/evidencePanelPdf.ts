import { buildDocumentFileUrl } from "./api.ts";
import type { ReferenceRecord } from "./types.ts";

export type PdfViewerPayload = {
  fileUrl: string;
  page: number;
};

function toPdfPage(page: number | string): number {
  const parsed = Number(page);
  return Number.isFinite(parsed) && parsed >= 1 ? Math.floor(parsed) : 1;
}

export function buildPdfViewerPayload(
  activeReference: ReferenceRecord | null,
  pdfFileUrl?: string | null
): PdfViewerPayload | null {
  if (!activeReference) {
    return null;
  }

  const documentId =
    activeReference.documentId ?? activeReference.source.document_id ?? "";
  const fileUrl = pdfFileUrl ?? buildDocumentFileUrl(documentId);
  if (!fileUrl) {
    return null;
  }

  return {
    fileUrl,
    page: toPdfPage(activeReference.source.page)
  };
}
