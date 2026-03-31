import { BookOpen, LoaderCircle, ShieldCheck } from "lucide-react";
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
import type { DocumentInfo, ReferenceRecord } from "../lib/types";

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
  selectedDocument?: DocumentInfo | null;
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
    return "已定位到页，但未能精确高亮";
  }
  if (status === "error") {
    return "文档加载失败";
  }
  return "正在定位文档";
}

function getPdfLocationTone(status: PdfLocationStatus): string {
  if (status === "highlighted") {
    return "border-emerald-100 bg-emerald-50 text-emerald-700";
  }
  if (status === "page_only") {
    return "border-amber-100 bg-amber-50 text-amber-700";
  }
  if (status === "error") {
    return "border-rose-100 bg-rose-50 text-rose-700";
  }
  return "border-cyan-100 bg-cyan-50 text-cyan-700";
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
  sourceTranslationError = null,
  selectedDocument = null
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
      {/* 固定面板标题栏 */}
      <div className="flex h-14 shrink-0 items-center border-b border-stone-200 bg-white px-5">
        <h2 className="flex items-center gap-2 text-sm font-semibold text-stone-800">
          <ShieldCheck className="h-4 w-4 text-cyan-700" />
          证据与溯源
        </h2>
      </div>

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
              {/* 第一层：紧凑元数据头 */}
              <div className="flex h-12 shrink-0 items-center justify-between border-b border-stone-200 bg-stone-50/80 px-4">
                <div className="flex items-center gap-2 overflow-hidden">
                  <ShieldCheck className="h-3.5 w-3.5 shrink-0 text-cyan-700" />
                  <span className="truncate font-mono text-[11px] font-semibold text-stone-700">
                    {activeReference.documentId ?? activeReference.source.document_id ?? ""}
                  </span>
                  {activeReference.source.clause ? (
                    <span className="text-[10px] text-stone-400">
                      &sect;{activeReference.source.clause}
                    </span>
                  ) : null}
                  <span className="text-[10px] text-stone-400">
                    p.{activeReference.source.page}
                  </span>
                  <span
                    className={`rounded-full px-2 py-0.5 text-[9px] font-semibold ${getPdfLocationTone(pdfLocationStatus)}`}
                  >
                    {getPdfLocationLabel(pdfLocationStatus)}
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-[10px] text-stone-500">翻译</span>
                  <button
                    aria-pressed={sourceTranslationEnabled}
                    className={`relative h-[18px] w-9 rounded-full transition-colors ${
                      sourceTranslationEnabled ? "bg-cyan-600" : "bg-stone-300"
                    }`}
                    disabled={!onSourceTranslationEnabledChange}
                    onClick={() => onSourceTranslationEnabledChange?.(!sourceTranslationEnabled)}
                    type="button"
                  >
                    <span
                      className={`absolute top-[2px] h-[14px] w-[14px] rounded-full bg-white shadow transition-[left] ${
                        sourceTranslationEnabled ? "left-[18px]" : "left-[2px]"
                      }`}
                    />
                  </button>
                </div>
              </div>

              {/* 第二层：PDF 查看器（占据所有剩余空间） */}
              <div className="relative min-h-0 flex-1 bg-neutral-600">
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
                    elementType={activeReference.source.element_type}
                    bbox={activeReference.source.bbox}
                    highlightText={activeReference.source.highlight_text?.trim() || ""}
                    locatorText={
                      activeReference.source.locator_text?.trim() ||
                      activeReference.source.original_text ||
                      ""
                    }
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
              <div className="shrink-0 border-t border-stone-200 bg-stone-50/80">
                {!sourceTranslationEnabled ? (
                  <div className="px-4 py-2.5 text-[11px] text-stone-400">
                    引用翻译已关闭
                  </div>
                ) : sourceTranslationLoading ? (
                  <div className="flex items-center gap-2 px-4 py-2.5 text-[11px] text-stone-500">
                    <LoaderCircle className="h-3 w-3 animate-spin text-cyan-600" />
                    正在生成引用翻译…
                  </div>
                ) : sourceTranslationError ? (
                  <div className="px-4 py-2.5 text-[11px] text-rose-600">
                    翻译失败：{sourceTranslationError}
                  </div>
                ) : resolvedTranslation.trim() ? (
                  <div className="max-h-40 overflow-y-auto px-4 py-3">
                    <div className={translationMarkdownClassName}>
                      <ReactMarkdown
                        rehypePlugins={markdownRehypePlugins}
                        remarkPlugins={markdownRemarkPlugins}
                      >
                        {resolvedTranslation}
                      </ReactMarkdown>
                    </div>
                  </div>
                ) : (
                  <div className="px-4 py-2.5 text-[11px] text-stone-400">
                    已开启，暂无译文
                  </div>
                )}
              </div>
            </motion.div>
          ) : (
            <div className="flex h-full flex-col items-center justify-center p-8 text-center text-stone-400">
              <BookOpen className="mb-4 h-12 w-12 opacity-20" />
              <p className="text-sm">
                点击回答区中的引用后，
                <br />
                这里会直接打开 PDF 原文定位并展示引用翻译。
              </p>
            </div>
          )}
        </AnimatePresence>
      </div>
    </aside>
  );
}
