import {
  Copy,
  FileSearch,
  FileText,
  LoaderCircle,
  X
} from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type PointerEvent as ReactPointerEvent
} from "react";
import ReactMarkdown from "react-markdown";

import { buildPdfViewerPayload } from "../lib/evidencePanelPdf";
import {
  clampDrawerHeight,
  getDefaultDrawerHeight,
  resizeDrawerHeight
} from "../lib/evidenceDrawerLayout";
import { getEvidencePanelClassName } from "../lib/evidencePanelLayout";
import {
  markdownRehypePlugins,
  markdownRemarkPlugins
} from "../lib/markdown";
import type { PdfLocationStatus } from "../lib/pdfLocator";
import type { ReferenceRecord } from "../lib/types";
import PdfEvidenceViewer from "./PdfEvidenceViewer";

type EvidencePanelProps = {
  activeReference: ReferenceRecord | null;
  pdfFileUrl?: string | null;
  pdfLocationStatus?: PdfLocationStatus;
  onPdfLocationResolved?: (status: PdfLocationStatus) => void;
  sourceTranslationEnabled?: boolean;
  onSourceTranslationEnabledChange?: (enabled: boolean) => void;
  sourceTranslation?: string | null;
  sourceTranslationLoading?: boolean;
  sourceTranslationError?: string | null;
  previewImageUrl?: string | null;
  previewLoading?: boolean;
};

function getPdfLocationLabel(status: PdfLocationStatus): string {
  if (status === "highlighted" || status === "page_only") {
    return "已定位到页";
  }
  if (status === "error") {
    return "加载失败";
  }
  return "定位中…";
}

function getStatusBadgeClassName(status: PdfLocationStatus): string {
  if (status === "highlighted" || status === "page_only") {
    return "border-amber-200 bg-amber-50 text-amber-700";
  }
  if (status === "error") {
    return "border-rose-200 bg-rose-50 text-rose-700";
  }
  return "border-cyan-200 bg-cyan-50 text-cyan-700";
}

export default function EvidencePanel({
  activeReference,
  pdfFileUrl = null,
  pdfLocationStatus = "idle",
  onPdfLocationResolved,
  sourceTranslationEnabled = false,
  onSourceTranslationEnabledChange,
  sourceTranslation = null,
  sourceTranslationLoading = false,
  sourceTranslationError = null
}: EvidencePanelProps) {
  const panelRef = useRef<HTMLElement>(null);
  const [panelHeight, setPanelHeight] = useState(720);
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);
  const [drawerHeight, setDrawerHeight] = useState(280);
  const [copyTone, setCopyTone] = useState<"idle" | "success" | "error">("idle");
  const pdfViewerPayload = buildPdfViewerPayload(activeReference, pdfFileUrl);
  const resolvedTranslation =
    sourceTranslation ?? activeReference?.source.translation ?? "";
  const translationMarkdownClassName = [
    "max-w-none text-[13px] leading-6 text-stone-800",
    "[&_p]:mb-3 [&_p:last-child]:mb-0",
    "[&_ul]:mb-3 [&_ul]:list-disc [&_ul]:pl-5",
    "[&_ol]:mb-3 [&_ol]:list-decimal [&_ol]:pl-5",
    "[&_li]:mb-1",
    "[&_strong]:font-semibold [&_strong]:text-stone-900",
    "[&_code]:rounded [&_code]:bg-stone-100 [&_code]:px-1.5 [&_code]:py-0.5 [&_code]:font-mono [&_code]:text-[12px]",
    "[&_table]:mb-3 [&_table]:w-full [&_table]:border-collapse [&_table]:text-[12px]",
    "[&_th]:border [&_th]:border-stone-200 [&_th]:bg-stone-100 [&_th]:px-2 [&_th]:py-1.5 [&_th]:text-left [&_th]:font-semibold",
    "[&_td]:border [&_td]:border-stone-200 [&_td]:px-2 [&_td]:py-1.5 [&_td]:align-top",
    "[&_.katex-display]:my-3 [&_.katex-display]:overflow-x-auto [&_.katex]:text-[1.02em]"
  ].join(" ");

  useEffect(() => {
    const node = panelRef.current;
    if (!node || typeof ResizeObserver === "undefined") {
      return;
    }

    const observer = new ResizeObserver((entries) => {
      const nextHeight = entries[0]?.contentRect.height ?? node.clientHeight;
      if (!nextHeight) {
        return;
      }
      setPanelHeight(nextHeight);
      setDrawerHeight((current) => clampDrawerHeight(current, nextHeight));
    });

    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (!activeReference) {
      setIsDrawerOpen(false);
      return;
    }
    setIsDrawerOpen(true);
    setDrawerHeight(getDefaultDrawerHeight(panelHeight));
  }, [activeReference?.id, panelHeight]);

  async function handleCopyOriginal() {
    const text = activeReference?.source.original_text?.trim() ?? "";
    if (!text) {
      return;
    }
    try {
      await navigator.clipboard.writeText(text);
      setCopyTone("success");
    } catch {
      setCopyTone("error");
    }
    window.setTimeout(() => setCopyTone("idle"), 1600);
  }

  function handleResizeStart(event: ReactPointerEvent<HTMLButtonElement>) {
    if (!isDrawerOpen || !activeReference) {
      return;
    }

    event.preventDefault();
    const startY = event.clientY;
    const startHeight = drawerHeight;
    document.body.style.userSelect = "none";

    const handlePointerMove = (moveEvent: PointerEvent) => {
      setDrawerHeight(
        resizeDrawerHeight(startHeight, moveEvent.clientY - startY, panelHeight)
      );
    };

    const handlePointerEnd = () => {
      document.body.style.userSelect = "";
      window.removeEventListener("pointermove", handlePointerMove);
      window.removeEventListener("pointerup", handlePointerEnd);
      window.removeEventListener("pointercancel", handlePointerEnd);
    };

    window.addEventListener("pointermove", handlePointerMove);
    window.addEventListener("pointerup", handlePointerEnd);
    window.addEventListener("pointercancel", handlePointerEnd);
  }

  const drawerHeader = useMemo(() => {
    if (!activeReference) {
      return {
        title: "尚未选中引用",
        subtitle: "点击回答中的引用标注后，这里会显示原文与翻译。"
      };
    }

    const fileLabel =
      activeReference.source.file ||
      activeReference.documentId ||
      activeReference.source.document_id ||
      "未命名文档";

    const clauseLabel = activeReference.source.clause?.trim();
    const sectionLabel = activeReference.source.section?.trim();

    return {
      title: clauseLabel ? `${fileLabel}  Clause ${clauseLabel}` : fileLabel,
      subtitle: sectionLabel || "当前引用"
    };
  }, [activeReference]);

  return (
    <aside ref={panelRef} className={getEvidencePanelClassName()}>
      <div className="relative min-h-0 flex-1 overflow-hidden bg-[#ebe9e2]">
        {pdfViewerPayload ? (
          <PdfEvidenceViewer
            fileUrl={pdfViewerPayload.fileUrl}
            onLocationResolved={onPdfLocationResolved}
            page={pdfViewerPayload.page}
            toolbarSlot={
              <button
                aria-expanded={isDrawerOpen}
                className={[
                  "inline-flex items-center gap-1 rounded-md border px-2.5 py-1 text-xs font-medium transition",
                  activeReference
                    ? "border-cyan-200 bg-cyan-50 text-cyan-700 hover:bg-cyan-100"
                    : "cursor-not-allowed border-stone-200 bg-stone-100 text-stone-400"
                ].join(" ")}
                disabled={!activeReference}
                onClick={() => {
                  if (activeReference) {
                    setIsDrawerOpen((current) => !current);
                  }
                }}
                title={activeReference ? "打开引用抽屉" : "请先在回答中选中引用"}
                type="button"
              >
                <FileText className="h-3.5 w-3.5" />
                引用
              </button>
            }
          />
        ) : (
          <>
            <div className="absolute right-3 top-3 z-[2]">
              <button
                className="inline-flex cursor-not-allowed items-center gap-1 rounded-md border border-stone-200 bg-white/90 px-2.5 py-1 text-xs font-medium text-stone-400 shadow-sm backdrop-blur"
                disabled
                title="请先在回答中选中引用"
                type="button"
              >
                <FileText className="h-3.5 w-3.5" />
                引用
              </button>
            </div>
            <div className="flex h-full flex-col items-center justify-center gap-4 px-8">
              <FileSearch className="h-10 w-10 text-stone-300" />
              <div className="text-center">
                <p className="text-pretty text-sm font-medium text-stone-500">
                  点击回答中的引用标注，即可在此查看整页 PDF
                </p>
                <p className="mt-1 text-pretty text-xs text-stone-400">
                  右上角按钮可拉出引用抽屉，查看原文与 AI 辅助翻译
                </p>
              </div>
            </div>
          </>
        )}

        <AnimatePresence>
          {activeReference && isDrawerOpen ? (
            <motion.div
              animate={{ opacity: 1, y: 0 }}
              className="absolute inset-x-0 bottom-0 z-20 overflow-hidden rounded-t-[28px] border-t border-stone-200 bg-white/96 shadow-[0_-18px_50px_-24px_rgba(15,23,42,0.38)] backdrop-blur"
              exit={{ opacity: 0, y: 18 }}
              initial={{ opacity: 0, y: 18 }}
              style={{ height: drawerHeight }}
              transition={{ duration: 0.18, ease: "easeOut" }}
            >
              <div className="flex h-full flex-col">
                <div className="shrink-0 border-b border-stone-200 px-4 pt-2.5">
                  <div className="flex items-center justify-center pb-2">
                    <button
                      aria-label="调整抽屉高度"
                      className="group flex h-6 w-16 items-center justify-center"
                      onPointerDown={handleResizeStart}
                      type="button"
                    >
                      <span className="h-1.5 w-11 rounded-full bg-stone-300 transition group-hover:bg-stone-400" />
                    </button>
                  </div>
                  <div className="flex items-start gap-3 pb-3">
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-sm font-semibold text-stone-900">
                        {drawerHeader.title}
                      </div>
                      <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-stone-500">
                        <span>{drawerHeader.subtitle}</span>
                        <span className="rounded bg-stone-100 px-2 py-0.5 text-stone-600">
                          Page {activeReference.source.page}
                        </span>
                        <span
                          className={[
                            "rounded border px-2 py-0.5",
                            getStatusBadgeClassName(pdfLocationStatus)
                          ].join(" ")}
                        >
                          {getPdfLocationLabel(pdfLocationStatus)}
                        </span>
                      </div>
                    </div>
                    <div className="flex shrink-0 items-center gap-2">
                      <button
                        className="inline-flex items-center gap-1 rounded-md border border-stone-200 bg-white px-2.5 py-1.5 text-xs text-stone-600 transition hover:border-stone-300 hover:bg-stone-50"
                        onClick={() => void handleCopyOriginal()}
                        type="button"
                      >
                        <Copy className="h-3.5 w-3.5" />
                        {copyTone === "success"
                          ? "已复制"
                          : copyTone === "error"
                            ? "复制失败"
                            : "复制原文"}
                      </button>
                      <button
                        className={[
                          "inline-flex items-center rounded-md border px-2.5 py-1.5 text-xs transition",
                          sourceTranslationEnabled
                            ? "border-cyan-200 bg-cyan-50 text-cyan-700 hover:bg-cyan-100"
                            : "border-stone-200 bg-white text-stone-600 hover:bg-stone-50"
                        ].join(" ")}
                        onClick={() =>
                          onSourceTranslationEnabledChange?.(!sourceTranslationEnabled)
                        }
                        type="button"
                      >
                        {sourceTranslationEnabled ? "关闭翻译" : "显示翻译"}
                      </button>
                      <button
                        aria-label="关闭引用抽屉"
                        className="inline-flex h-8 w-8 items-center justify-center rounded-md border border-stone-200 bg-white text-stone-500 transition hover:bg-stone-50"
                        onClick={() => setIsDrawerOpen(false)}
                        type="button"
                      >
                        <X className="h-4 w-4" />
                      </button>
                    </div>
                  </div>
                </div>

                <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4">
                  <div className="grid gap-4">
                    <section className="overflow-hidden rounded-2xl border border-stone-200 bg-white shadow-sm">
                      <div className="border-b border-stone-200 bg-stone-50 px-4 py-3 text-xs font-semibold uppercase tracking-[0.16em] text-stone-500">
                        原文引用
                      </div>
                      <div className="px-4 py-4 text-[15px] leading-8 text-stone-800">
                        {activeReference.source.original_text}
                      </div>
                    </section>

                    <section className="overflow-hidden rounded-2xl border border-cyan-200 bg-cyan-50/60 shadow-sm">
                      <div className="border-b border-cyan-100 px-4 py-3 text-xs font-semibold uppercase tracking-[0.16em] text-cyan-700">
                        AI 辅助翻译
                      </div>
                      <div className="px-4 py-4">
                        {!sourceTranslationEnabled ? (
                          <div className="text-sm text-stone-400">翻译已关闭</div>
                        ) : sourceTranslationLoading ? (
                          <div className="flex items-center gap-2 text-sm text-stone-500">
                            <LoaderCircle className="h-4 w-4 animate-spin text-cyan-600" />
                            正在生成引用翻译…
                          </div>
                        ) : sourceTranslationError ? (
                          <div className="text-sm text-rose-600">
                            翻译失败：{sourceTranslationError}
                          </div>
                        ) : resolvedTranslation.trim() ? (
                          <div className={translationMarkdownClassName}>
                            <ReactMarkdown
                              rehypePlugins={markdownRehypePlugins}
                              remarkPlugins={markdownRemarkPlugins}
                            >
                              {resolvedTranslation}
                            </ReactMarkdown>
                          </div>
                        ) : (
                          <div className="text-sm text-stone-400">已开启，暂无译文</div>
                        )}
                      </div>
                    </section>
                  </div>
                </div>
              </div>
            </motion.div>
          ) : null}
        </AnimatePresence>
      </div>
    </aside>
  );
}
