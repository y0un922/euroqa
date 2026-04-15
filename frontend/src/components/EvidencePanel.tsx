import { FileSearch, LoaderCircle } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import ReactMarkdown from "react-markdown";

import { buildDocumentFileUrl } from "../lib/api";
import PdfEvidenceViewer from "./PdfEvidenceViewer";
import { getEvidencePanelClassName } from "../lib/evidencePanelLayout";
import {
  markdownRehypePlugins,
  markdownRemarkPlugins
} from "../lib/markdown";
import type { PdfLocationStatus } from "../lib/pdfLocator";
import type { ReferenceRecord } from "../lib/types";

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

function toPdfPage(page: number | string): number {
  const parsed = Number(page);
  return Number.isFinite(parsed) && parsed >= 1 ? Math.floor(parsed) : 1;
}

function getPdfLocationLabel(status: PdfLocationStatus): string {
  if (status === "highlighted") {
    return "已定位并高亮";
  }
  if (status === "page_only") {
    return "已定位到页";
  }
  if (status === "error") {
    return "加载失败";
  }
  return "定位中…";
}

function getStatusDotColor(status: PdfLocationStatus): string {
  if (status === "highlighted") {
    return "bg-emerald-500";
  }
  if (status === "page_only") {
    return "bg-amber-500";
  }
  if (status === "error") {
    return "bg-rose-500";
  }
  return "bg-cyan-500 animate-pulse";
}

function getStatusTextColor(status: PdfLocationStatus): string {
  if (status === "highlighted") {
    return "text-emerald-700";
  }
  if (status === "page_only") {
    return "text-amber-700";
  }
  if (status === "error") {
    return "text-rose-700";
  }
  return "text-cyan-700";
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
    "[&_.katex-display]:my-3 [&_.katex-display]:overflow-x-auto [&_.katex]:text-[1.02em]",
  ].join(" ");
  const resolvedTranslation =
    sourceTranslation ?? activeReference?.source.translation ?? "";

  return (
    <aside className={getEvidencePanelClassName()}>
      {/* 内容区域：三层布局或空状态 */}
      <div className="min-h-0 flex-1">
        <AnimatePresence mode="wait">
          {activeReference ? (
            <motion.div
              animate={{ opacity: 1 }}
              className="flex h-full flex-col"
              exit={{ opacity: 0 }}
              initial={{ opacity: 0 }}
              key={activeReference.id}
              transition={{ duration: 0.15 }}
            >
              {/* 第一层：元数据 property chips */}
              <div className="flex min-h-[44px] shrink-0 flex-wrap items-center gap-1.5 border-b border-stone-200 bg-white px-3 py-2">
                <span className="truncate rounded bg-stone-100 px-1.5 py-0.5 font-mono text-xs font-medium text-stone-700">
                  {activeReference.documentId ?? activeReference.source.document_id ?? ""}
                </span>
                {activeReference.source.clause ? (
                  <span className="rounded bg-cyan-50 px-1.5 py-0.5 text-xs text-cyan-700">
                    &sect;{activeReference.source.clause}
                  </span>
                ) : null}
                <span className="rounded bg-stone-100 px-1.5 py-0.5 text-xs text-stone-500">
                  p.{activeReference.source.page}
                </span>
                <span className={`flex items-center gap-1 text-xs ${getStatusTextColor(pdfLocationStatus)}`}>
                  <span className={`inline-block h-2 w-2 rounded-full ${getStatusDotColor(pdfLocationStatus)}`} />
                  {getPdfLocationLabel(pdfLocationStatus)}
                </span>
                <div className="ml-auto flex items-center gap-1.5">
                  <span className="text-xs text-stone-500">翻译</span>
                  <button
                    aria-pressed={sourceTranslationEnabled}
                    className={[
                      "relative h-[18px] w-9 rounded-full transition-colors",
                      sourceTranslationEnabled ? "bg-cyan-600" : "bg-stone-300",
                      "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-cyan-600",
                      "hover:opacity-90 active:opacity-80",
                      "disabled:cursor-not-allowed disabled:opacity-50"
                    ].join(" ")}
                    disabled={!onSourceTranslationEnabledChange}
                    onClick={() => onSourceTranslationEnabledChange?.(!sourceTranslationEnabled)}
                    type="button"
                  >
                    <span
                      className={`absolute top-[2px] h-[14px] w-[14px] rounded-full bg-white shadow-sm transition-all duration-150 ${
                        sourceTranslationEnabled ? "left-[18px]" : "left-[2px]"
                      }`}
                    />
                  </button>
                </div>
              </div>

              {/* 第二层：PDF 查看器（占据所有剩余空间） */}
              <div className="relative min-h-0 flex-1 bg-[#eae9e4]">
                {pdfFileUrl || activeReference.documentId || activeReference.source.document_id ? (
                  <PdfEvidenceViewer
                    fileUrl={
                      pdfFileUrl ??
                      buildDocumentFileUrl(
                        activeReference.documentId ??
                          activeReference.source.document_id ??
                          ""
                      )
                    }
                    bbox={activeReference.source.bbox}
                    highlightText={activeReference.source.highlight_text ?? ""}
                    locatorText={activeReference.source.locator_text ?? ""}
                    onLocationResolved={onPdfLocationResolved}
                    page={toPdfPage(activeReference.source.page)}
                  />
                ) : (
                  <div className="flex h-full items-center justify-center px-4 text-center text-sm text-stone-400">
                    当前引用未提供可用文档 ID。
                  </div>
                )}
              </div>

              {/* 第三层：可折叠翻译栏 */}
              <div className="min-h-[40px] shrink-0 border-t border-stone-200 bg-stone-50/80">
                <AnimatePresence mode="wait">
                  {!sourceTranslationEnabled ? (
                    <motion.div
                      key="disabled"
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      exit={{ opacity: 0 }}
                      transition={{ duration: 0.12 }}
                      className="px-4 py-2.5 text-xs text-stone-400"
                    >
                      引用翻译已关闭
                    </motion.div>
                  ) : sourceTranslationLoading ? (
                    <motion.div
                      key="loading"
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      exit={{ opacity: 0 }}
                      transition={{ duration: 0.12 }}
                      className="flex items-center gap-2 px-4 py-2.5 text-xs text-stone-500"
                    >
                      <LoaderCircle className="h-3 w-3 animate-spin text-cyan-600" />
                      正在生成引用翻译…
                    </motion.div>
                  ) : sourceTranslationError ? (
                    <motion.div
                      key="error"
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      exit={{ opacity: 0 }}
                      transition={{ duration: 0.12 }}
                      className="px-4 py-2.5 text-xs text-rose-600"
                    >
                      翻译失败：{sourceTranslationError}
                    </motion.div>
                  ) : resolvedTranslation.trim() ? (
                    <motion.div
                      key="content"
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      exit={{ opacity: 0 }}
                      transition={{ duration: 0.12 }}
                      className="max-h-40 overflow-y-auto px-4 py-3"
                    >
                      <div className={translationMarkdownClassName}>
                        <ReactMarkdown
                          rehypePlugins={markdownRehypePlugins}
                          remarkPlugins={markdownRemarkPlugins}
                        >
                          {resolvedTranslation}
                        </ReactMarkdown>
                      </div>
                    </motion.div>
                  ) : (
                    <motion.div
                      key="empty"
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      exit={{ opacity: 0 }}
                      transition={{ duration: 0.12 }}
                      className="px-4 py-2.5 text-xs text-stone-400"
                    >
                      已开启，暂无译文
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>
            </motion.div>
          ) : (
            <div className="flex h-full flex-col items-center justify-center gap-4 px-8">
              <FileSearch className="h-10 w-10 text-stone-300" />
              <div className="text-center">
                <p className="text-pretty text-sm font-medium text-stone-500">
                  点击回答中的引用标注，即可在此查看 PDF 原文定位
                </p>
                <p className="mt-1 text-pretty text-xs text-stone-400">
                  高亮显示原始文本段落，并提供中文翻译
                </p>
              </div>
            </div>
          )}
        </AnimatePresence>
      </div>
    </aside>
  );
}
