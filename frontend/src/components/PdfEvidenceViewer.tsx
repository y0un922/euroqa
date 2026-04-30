import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { Document, Page, pdfjs } from "react-pdf";

import {
  clampPdfPage,
  type PdfLocationStatus
} from "../lib/pdfLocator";
import {
  getPdfNavigationState,
  resolvePdfPageState,
  stepPdfPage,
} from "../lib/pdfViewerPage";

pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  "pdfjs-dist/build/pdf.worker.min.mjs",
  import.meta.url
).toString();

type PdfEvidenceViewerProps = {
  fileUrl: string;
  page: number;
  onLocationResolved?: (status: PdfLocationStatus) => void;
  toolbarSlot?: ReactNode;
};

export function PdfEvidenceViewer({
  fileUrl,
  page,
  onLocationResolved,
  toolbarSlot = null
}: PdfEvidenceViewerProps) {
  const [totalPages, setTotalPages] = useState<number | null>(null);
  const [currentPage, setCurrentPage] = useState(() => clampPdfPage(page, null));
  const [pageInput, setPageInput] = useState(() =>
    String(clampPdfPage(page, null))
  );
  const safePage = clampPdfPage(currentPage, totalPages);
  const hasFatalErrorRef = useRef(false);
  const lastReportedStatusRef = useRef<PdfLocationStatus>("idle");
  const onLocationResolvedRef = useRef(onLocationResolved);
  const scrollContainerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    onLocationResolvedRef.current = onLocationResolved;
  }, [onLocationResolved]);

  useEffect(() => {
    hasFatalErrorRef.current = false;
    lastReportedStatusRef.current = "idle";
    const nextPage = clampPdfPage(page, null);
    setCurrentPage(nextPage);
    setPageInput(String(nextPage));
    onLocationResolvedRef.current?.("idle");
  }, [fileUrl, page]);

  useEffect(() => {
    setTotalPages(null);
  }, [fileUrl]);

  useEffect(() => {
    const nextState = resolvePdfPageState(page, currentPage, totalPages);
    setCurrentPage(nextState.currentPage);
    setPageInput(nextState.pageInput);
  }, [page, totalPages]);

  useEffect(() => {
    requestAnimationFrame(() => {
      scrollContainerRef.current?.scrollTo({ top: 0, behavior: "smooth" });
    });
  }, [safePage]);

  function reportStatus(status: PdfLocationStatus) {
    if (lastReportedStatusRef.current === status) {
      return;
    }
    lastReportedStatusRef.current = status;
    onLocationResolvedRef.current?.(status);
  }

  const navigationState = useMemo(
    () => getPdfNavigationState(safePage, totalPages),
    [safePage, totalPages]
  );

  function commitPageInput(nextValue: string) {
    const nextState = resolvePdfPageState(Number(nextValue), safePage, totalPages);
    setCurrentPage(nextState.currentPage);
    setPageInput(nextState.pageInput);
  }

  function stepDisplayedPage(direction: "prev" | "next") {
    const requestedPage = stepPdfPage(safePage, direction, totalPages);
    const nextState = resolvePdfPageState(requestedPage, safePage, totalPages);
    setCurrentPage(nextState.currentPage);
    setPageInput(nextState.pageInput);
  }

  return (
    <div
      ref={scrollContainerRef}
      className="flex h-full w-full flex-col overflow-auto"
    >
      <div className="sticky top-0 z-[1] flex items-center justify-between border-b border-stone-200 bg-white/95 px-3 py-2 backdrop-blur">
        <div className="text-xs font-medium text-stone-500">PDF 全文</div>
        <div className="flex items-center gap-2">
          <button
            aria-label="上一页"
            className="inline-flex h-7 w-7 items-center justify-center rounded-md border border-stone-200 text-stone-600 transition hover:bg-stone-50 disabled:cursor-not-allowed disabled:opacity-40"
            disabled={!navigationState.canGoPrev}
            onClick={() => stepDisplayedPage("prev")}
            type="button"
          >
            <ChevronLeft className="h-4 w-4" />
          </button>
          <label className="flex items-center gap-1 text-xs text-stone-500">
            <span>第</span>
            <input
              aria-label="页码"
              className="w-14 rounded-md border border-stone-200 bg-white px-2 py-1 text-center text-xs text-stone-700 outline-none focus:border-cyan-300"
              inputMode="numeric"
              onBlur={(event) => commitPageInput(event.target.value)}
              onChange={(event) => setPageInput(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  commitPageInput(pageInput);
                }
              }}
              value={pageInput}
            />
            <span>/ {totalPages ?? "..."}</span>
          </label>
          <button
            aria-label="下一页"
            className="inline-flex h-7 w-7 items-center justify-center rounded-md border border-stone-200 text-stone-600 transition hover:bg-stone-50 disabled:cursor-not-allowed disabled:opacity-40"
            disabled={!navigationState.canGoNext}
            onClick={() => stepDisplayedPage("next")}
            type="button"
          >
            <ChevronRight className="h-4 w-4" />
          </button>
          {toolbarSlot}
        </div>
      </div>
      <Document
        key={fileUrl}
        file={fileUrl}
        loading={
          <div className="flex flex-col items-center gap-3 p-6">
            <p className="text-xs text-stone-400">正在加载文档…</p>
            <div className="h-48 w-full animate-pulse rounded bg-stone-200/60" />
            <div className="h-4 w-3/4 animate-pulse rounded bg-stone-200/60" />
            <div className="h-4 w-1/2 animate-pulse rounded bg-stone-200/60" />
          </div>
        }
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
        <div className="flex justify-center px-4 py-4">
          <Page
            key={`${fileUrl}:${safePage}`}
            pageNumber={safePage}
            renderAnnotationLayer={false}
            renderTextLayer={false}
            onLoadError={() => {
              hasFatalErrorRef.current = true;
              reportStatus("error");
            }}
            onRenderSuccess={() => {
              if (!hasFatalErrorRef.current) {
                reportStatus("page_only");
              }
            }}
            onRenderError={() => {
              hasFatalErrorRef.current = true;
              reportStatus("error");
            }}
          />
        </div>
      </Document>
    </div>
  );
}

export default PdfEvidenceViewer;
