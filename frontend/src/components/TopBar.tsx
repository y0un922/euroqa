import { useState } from "react";
import {
  Activity,
  AlertCircle,
  BookOpen,
  Check,
  Database,
  Download,
  Settings2,
  Sparkles
} from "lucide-react";

import {
  buildConversationExportFilename,
  buildConversationMarkdown,
  downloadMarkdownFile,
  isChatTurnExportable
} from "../lib/replyExport";
import type { ChatTurn, LlmSettings } from "../lib/types";
import LlmSettingsPanel from "./LlmSettingsPanel";

type TopBarProps = {
  apiState: "loading" | "ready" | "degraded";
  conversationId: string | null;
  documentCount: number;
  glossaryCount: number;
  llmApiKeyConfigured: boolean;
  llmDefaultSettings: LlmSettings;
  llmSettings: LlmSettings | null;
  messages: ChatTurn[];
  onResetLlmSettings: () => void;
  onSaveLlmSettings: (settings: LlmSettings) => void;
};

export default function TopBar({
  apiState,
  conversationId,
  documentCount,
  glossaryCount,
  llmApiKeyConfigured,
  llmDefaultSettings,
  llmSettings,
  messages,
  onResetLlmSettings,
  onSaveLlmSettings
}: TopBarProps) {
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [exportState, setExportState] = useState<"idle" | "success" | "error">("idle");
  const statusLabel =
    apiState === "ready"
      ? "API 已连接"
      : apiState === "degraded"
        ? "部分能力受限"
        : "连接中";

  const statusTone =
    apiState === "ready"
      ? "text-emerald-700 bg-emerald-50 border-emerald-100"
      : apiState === "degraded"
        ? "text-amber-700 bg-amber-50 border-amber-100"
        : "text-stone-500 bg-stone-100 border-stone-200";
  const hasExportableMessages = messages.some(isChatTurnExportable);

  function handleExportConversation() {
    if (!hasExportableMessages) {
      return;
    }

    try {
      const exportedAt = new Date().toISOString();
      const markdown = buildConversationMarkdown(messages, {
        conversationId,
        exportedAt
      });
      downloadMarkdownFile(
        buildConversationExportFilename(conversationId, exportedAt),
        markdown
      );
      setExportState("success");
    } catch {
      setExportState("error");
    }

    window.setTimeout(() => {
      setExportState("idle");
    }, 1800);
  }

  return (
    <header className="z-10 flex h-14 shrink-0 items-center justify-between border-b border-stone-200 bg-white px-6">
      <div className="flex items-center gap-4">
        <div className="flex items-center gap-2 font-serif text-xl font-semibold tracking-tight text-stone-800">
          <div className="h-5 w-5 rounded-sm bg-cyan-800" />
          Euro_QA
        </div>
        <div className="mx-2 h-4 w-px bg-stone-300" />
        <div
          className={`flex items-center gap-2 rounded-md border px-2 py-1 text-xs font-medium ${statusTone}`}
        >
          <Activity className="h-3 w-3" />
          <span>{statusLabel}</span>
        </div>
      </div>
      <div className="relative flex items-center gap-5 text-sm text-stone-600">
        <div className="flex items-center gap-1.5">
          <Database className="h-4 w-4" />
          <span>{documentCount} 份文档</span>
        </div>
        <div className="flex items-center gap-1.5">
          <BookOpen className="h-4 w-4" />
          <span>{glossaryCount} 条术语</span>
        </div>
        <div className="flex items-center gap-1.5">
          <Sparkles className="h-4 w-4" />
          <span>实时演示模式</span>
        </div>
        <button
          aria-label={
            hasExportableMessages
              ? "导出当前会话的 Markdown 文件"
              : "当前没有可导出的完成态回答"
          }
          type="button"
          disabled={!hasExportableMessages}
          onClick={handleExportConversation}
          className={`inline-flex items-center gap-1.5 rounded-xl border px-3 py-1.5 text-sm font-medium transition ${
            exportState === "success"
              ? "border-emerald-200 bg-emerald-50 text-emerald-700"
              : exportState === "error"
                ? "border-rose-200 bg-rose-50 text-rose-700"
                : "border-stone-200 text-stone-600 hover:border-stone-300 hover:bg-stone-50 disabled:cursor-not-allowed disabled:border-stone-200 disabled:bg-stone-100 disabled:text-stone-400"
          }`}
          title={
            hasExportableMessages
              ? "导出当前会话的 Markdown 文件"
              : "当前没有可导出的完成态回答"
          }
        >
          {exportState === "success" ? (
            <Check className="h-4 w-4" />
          ) : exportState === "error" ? (
            <AlertCircle className="h-4 w-4" />
          ) : (
            <Download className="h-4 w-4" />
          )}
          <span>
            {exportState === "success"
              ? "已导出"
              : exportState === "error"
                ? "导出失败"
                : "导出会话"}
          </span>
        </button>
        <button
          type="button"
          onClick={() => {
            setIsSettingsOpen((current) => !current);
          }}
          className={`inline-flex items-center gap-1.5 rounded-xl border px-3 py-1.5 text-sm font-medium transition ${
            isSettingsOpen
              ? "border-cyan-200 bg-cyan-50 text-cyan-700"
              : "border-stone-200 text-stone-600 hover:border-stone-300 hover:bg-stone-50"
          }`}
        >
          <Settings2 className="h-4 w-4" />
          <span>LLM 设置</span>
        </button>
        {isSettingsOpen ? (
          <LlmSettingsPanel
            apiKeyConfigured={llmApiKeyConfigured}
            defaults={llmDefaultSettings}
            localSettings={llmSettings}
            onReset={() => {
              onResetLlmSettings();
              setIsSettingsOpen(false);
            }}
            onSave={(settings) => {
              onSaveLlmSettings(settings);
              setIsSettingsOpen(false);
            }}
          />
        ) : null}
      </div>
    </header>
  );
}
