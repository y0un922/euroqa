import { useEffect, useMemo, useRef, useState } from "react";
import { motion } from "motion/react";
import { Document, Page, pdfjs } from "react-pdf";
import "react-pdf/dist/Page/TextLayer.css";

import {
  bboxToOverlayStyle,
  clampPdfPage,
  hasUsablePdfBbox,
  hasUsableLocatorText,
  resolvePdfHighlightMatch,
  type PdfLocationStatus
} from "../lib/pdfLocator";

pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  "pdfjs-dist/build/pdf.worker.min.mjs",
  import.meta.url
).toString();

type PdfEvidenceViewerProps = {
  fileUrl: string;
  page: number;
  bbox?: number[];
  highlightText?: string;
  locatorText?: string;
  onLocationResolved?: (status: PdfLocationStatus) => void;
};

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

export function PdfEvidenceViewer({
  fileUrl,
  page,
  bbox = [],
  highlightText = "",
  locatorText = "",
  onLocationResolved
}: PdfEvidenceViewerProps) {
  const [totalPages, setTotalPages] = useState<number | null>(null);
  const [pageTextItems, setPageTextItems] = useState<string[]>([]);
  const safePage = clampPdfPage(page, totalPages);
  const useBboxOverlay = hasUsablePdfBbox(bbox);
  const useTextHighlight =
    !useBboxOverlay &&
    (hasUsableLocatorText(highlightText) || hasUsableLocatorText(locatorText));
  const hasFatalErrorRef = useRef(false);
  const lastReportedStatusRef = useRef<PdfLocationStatus>("idle");
  const onLocationResolvedRef = useRef(onLocationResolved);
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const overlayRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    onLocationResolvedRef.current = onLocationResolved;
  }, [onLocationResolved]);

  useEffect(() => {
    hasFatalErrorRef.current = false;
    lastReportedStatusRef.current = "idle";
    setPageTextItems([]);
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

  // 文本匹配高亮：当没有 bbox 时，利用 pdfLocator 的文本匹配能力
  const textHighlightMatch = useMemo(() => {
    if (!useTextHighlight || pageTextItems.length === 0) {
      return { itemIndexes: [] as number[], status: "page_only" as PdfLocationStatus };
    }
    return resolvePdfHighlightMatch({
      textItems: pageTextItems,
      highlightText,
      locatorText
    });
  }, [highlightText, locatorText, pageTextItems, useTextHighlight]);

  const highlightedIndexSet = useMemo(
    () => new Set(textHighlightMatch.itemIndexes),
    [textHighlightMatch.itemIndexes]
  );

  useEffect(() => {
    if (!useBboxOverlay || !overlayStyle || hasFatalErrorRef.current) {
      return;
    }
    reportStatus("highlighted");
    requestAnimationFrame(() => {
      overlayRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
    });
  }, [overlayStyle, useBboxOverlay]);

  // 保持 ref 同步以便在 onRenderTextLayerSuccess 回调中访问最新匹配结果
  const textHighlightMatchRef = useRef(textHighlightMatch);
  textHighlightMatchRef.current = textHighlightMatch;

  return (
    <div ref={scrollContainerRef} className="flex h-full w-full items-start justify-center overflow-auto">
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
        <div className="relative inline-block">
          <Page
            key={`${fileUrl}:${safePage}:${bbox.join(",")}`}
            pageNumber={safePage}
            renderAnnotationLayer={false}
            renderTextLayer
            customTextRenderer={
              useTextHighlight
                ? ({ str, itemIndex }) => {
                    const escaped = escapeHtml(str);
                    return highlightedIndexSet.has(itemIndex)
                      ? `<mark>${escaped}</mark>`
                      : escaped;
                  }
                : undefined
            }
            onGetTextSuccess={(textContent) => {
              if (!useTextHighlight) {
                return;
              }
              const items = textContent.items.flatMap((item) =>
                "str" in item && typeof item.str === "string" ? [item.str] : []
              );
              setPageTextItems((prev) => {
                const sig = items.join("\0");
                const prevSig = prev.join("\0");
                return sig === prevSig ? prev : items;
              });
            }}
            onLoadError={() => {
              hasFatalErrorRef.current = true;
              reportStatus("error");
            }}
            onRenderSuccess={() => {
              if (!useBboxOverlay && !useTextHighlight && !hasFatalErrorRef.current) {
                reportStatus("page_only");
              }
            }}
            onRenderTextLayerSuccess={() => {
              if (useBboxOverlay || hasFatalErrorRef.current) {
                return;
              }
              if (!useTextHighlight) {
                reportStatus("page_only");
                return;
              }
              // 此时 text layer DOM 已渲染完成，可以安全查询 <mark> 元素
              const match = textHighlightMatchRef.current;
              reportStatus(match.status);
              if (match.status === "highlighted") {
                requestAnimationFrame(() => {
                  const highlightNode = scrollContainerRef.current?.querySelector("mark");
                  if (highlightNode instanceof HTMLElement) {
                    highlightNode.scrollIntoView({ behavior: "smooth", block: "center" });
                  }
                });
              }
            }}
            onRenderTextLayerError={() => {
              if (!useBboxOverlay && !hasFatalErrorRef.current) {
                reportStatus("page_only");
              }
            }}
            onRenderError={() => {
              hasFatalErrorRef.current = true;
              reportStatus("error");
            }}
          />
          {overlayStyle ? (
            <motion.div
              ref={overlayRef}
              className="pointer-events-none absolute rounded border-2 border-cyan-500/60 bg-cyan-300/20 shadow-[0_0_0_1px_rgba(8,145,178,0.15)]"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ duration: 0.2, ease: "easeOut" }}
              style={overlayStyle}
            />
          ) : null}
        </div>
      </Document>
    </div>
  );
}

export default PdfEvidenceViewer;
