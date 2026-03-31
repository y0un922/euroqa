import { useEffect, useMemo, useRef, useState } from "react";
import { Document, Page, pdfjs } from "react-pdf";
import "react-pdf/dist/Page/TextLayer.css";

import {
  bboxToOverlayStyle,
  clampPdfPage,
  hasUsablePdfBbox,
  normalizePdfText,
  resolvePdfHighlightMatch,
  resolvePdfLocationStatus,
  type PdfLocationStatus
} from "../lib/pdfLocator";

pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  "pdfjs-dist/build/pdf.worker.min.mjs",
  import.meta.url
).toString();

type PdfEvidenceViewerProps = {
  fileUrl: string;
  page: number;
  elementType?: "text" | "table" | "formula" | "image";
  bbox?: number[];
  highlightText: string;
  locatorText: string;
  onLocationResolved?: (status: PdfLocationStatus) => void;
};

function escapeHtml(value: string): string {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

export function PdfEvidenceViewer({
  fileUrl,
  page,
  elementType = "text",
  bbox = [],
  highlightText,
  locatorText,
  onLocationResolved
}: PdfEvidenceViewerProps) {
  const [totalPages, setTotalPages] = useState<number | null>(null);
  const [pageViewport, setPageViewport] = useState<{ width: number; height: number } | null>(
    null
  );
  const safePage = clampPdfPage(page, totalPages);
  const useBboxOverlay = hasUsablePdfBbox(bbox);
  const normalizedTarget = useMemo(
    () => normalizePdfText(highlightText || locatorText),
    [highlightText, locatorText]
  );
  const matchedTextItemsRef = useRef<string[]>([]);
  const highlightedItemIndexesRef = useRef<Set<number>>(new Set());
  const hasFatalErrorRef = useRef(false);
  const textLayerFailedRef = useRef(false);
  const lastReportedStatusRef = useRef<PdfLocationStatus>("idle");
  const onLocationResolvedRef = useRef(onLocationResolved);

  useEffect(() => {
    onLocationResolvedRef.current = onLocationResolved;
  }, [onLocationResolved]);

  useEffect(() => {
    matchedTextItemsRef.current = [];
    highlightedItemIndexesRef.current = new Set();
    hasFatalErrorRef.current = false;
    textLayerFailedRef.current = false;
    lastReportedStatusRef.current = "idle";
    setPageViewport(null);
    onLocationResolvedRef.current?.("idle");
  }, [bbox, fileUrl, highlightText, locatorText, safePage]);

  useEffect(() => {
    setTotalPages(null);
  }, [fileUrl]);

  function reportStatus(status: PdfLocationStatus) {
    if (lastReportedStatusRef.current === status) {
      return;
    }
    lastReportedStatusRef.current = status;
    onLocationResolvedRef.current?.(status);
  }

  const overlayStyle = useMemo(() => {
    if (!useBboxOverlay) {
      return null;
    }
    return bboxToOverlayStyle(bbox);
  }, [bbox, useBboxOverlay]);

  useEffect(() => {
    if (!useBboxOverlay || !overlayStyle || hasFatalErrorRef.current) {
      return;
    }
    reportStatus("highlighted");
  }, [overlayStyle, useBboxOverlay]);

  return (
    <div className="flex h-full w-full items-start justify-center overflow-auto">
      <Document
        key={fileUrl}
        file={fileUrl}
        loading={<div className="p-4 text-sm text-neutral-500">Loading PDF...</div>}
        onLoadSuccess={(pdf) => {
          setTotalPages(pdf.numPages);
        }}
        onLoadError={() => {
          hasFatalErrorRef.current = true;
          reportStatus("error");
        }}
        onSourceError={() => {
          hasFatalErrorRef.current = true;
          reportStatus("error");
        }}
      >
        <div className="relative inline-block">
          <Page
            key={`${fileUrl}:${safePage}:${normalizedTarget}:${elementType}:${bbox.join(",")}`}
            pageNumber={safePage}
            renderAnnotationLayer={false}
            renderTextLayer
            onLoadError={() => {
              hasFatalErrorRef.current = true;
              reportStatus("error");
            }}
            onLoadSuccess={(pdfPage) => {
              const viewport = pdfPage.getViewport({ scale: 1 });
              setPageViewport({ width: viewport.width, height: viewport.height });
            }}
            onGetTextSuccess={({ items }) => {
              const textItems = items.map((item) => ("str" in item ? item.str : ""));
              matchedTextItemsRef.current = textItems;
              const match = resolvePdfHighlightMatch({
                textItems,
                highlightText,
                locatorText
              });
              highlightedItemIndexesRef.current = new Set(match.itemIndexes);
            }}
            onGetTextError={() => {
              textLayerFailedRef.current = true;
              reportStatus("page_only");
            }}
            onRenderTextLayerError={() => {
              textLayerFailedRef.current = true;
              reportStatus("page_only");
            }}
            onRenderError={() => {
              hasFatalErrorRef.current = true;
              reportStatus("error");
            }}
            onRenderTextLayerSuccess={() => {
              if (textLayerFailedRef.current) {
                reportStatus("page_only");
                return;
              }
              const match = resolvePdfHighlightMatch({
                textItems: matchedTextItemsRef.current,
                highlightText,
                locatorText
              });
              if (match.status === "highlighted") {
                reportStatus("highlighted");
                return;
              }
              reportStatus(
                resolvePdfLocationStatus({
                  locatorText: highlightText || locatorText,
                  matchedTextItems: [],
                  hasError: hasFatalErrorRef.current
                })
              );
            }}
            customTextRenderer={({ itemIndex, str }) => {
              if (!str) {
                return str;
              }
              if (!highlightedItemIndexesRef.current.has(itemIndex)) {
                return escapeHtml(str);
              }
              return `<mark>${escapeHtml(str)}</mark>`;
            }}
          />
          {overlayStyle ? (
            <div
              className="pointer-events-none absolute rounded border-2 border-cyan-500/80 bg-cyan-300/25 shadow-[0_0_0_1px_rgba(8,145,178,0.2)]"
              style={overlayStyle}
            />
          ) : null}
        </div>
      </Document>
    </div>
  );
}

export default PdfEvidenceViewer;
