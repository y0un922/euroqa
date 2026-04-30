import {
  BookMarked,
  History,
  MessageSquarePlus,
  Search,
  Trash2
} from "lucide-react";

import type { DocumentInfo, DocumentStatus, GlossaryEntry } from "../lib/types";
import DocumentStatusBadge from "./DocumentStatusBadge";
import DocumentUpload from "./DocumentUpload";

type HistorySessionSummary = {
  id: string;
  title: string;
  messageCount: number;
  lastUpdatedLabel: string;
};

type SidebarProps = {
  documents: DocumentInfo[];
  glossary: GlossaryEntry[];
  historySessions?: HistorySessionSummary[];
  hotQuestions: string[];
  activeSessionId?: string | null;
  onNewSession: () => void;
  onSelectHistorySession?: (sessionId: string) => void;
  onSelectHotQuestion: (question: string) => void;
  onUploadFile?: (file: File) => void;
  onDeleteDocument?: (docId: string) => void;
  processingDocId?: string | null;
  pipelineStage?: DocumentStatus | null;
  pipelineProgress?: number;
};

export default function Sidebar(props: SidebarProps) {
  const {
    documents,
    historySessions = [],
    hotQuestions,
    activeSessionId = null,
    onNewSession,
    onSelectHistorySession,
    onSelectHotQuestion,
    onUploadFile,
    onDeleteDocument,
    processingDocId,
    pipelineStage,
    pipelineProgress = 0
  } = props;
  const isProcessing = Boolean(processingDocId);

  return (
    <aside className="hidden h-full w-72 shrink-0 flex-col border-r border-stone-200 bg-stone-50/60 lg:flex">
      <div className="p-4">
        <button
          className="flex w-full items-center justify-center gap-2 rounded-md bg-stone-900 px-4 py-2 text-sm font-medium text-white shadow-sm transition-colors hover:bg-stone-800"
          onClick={onNewSession}
          type="button"
        >
          <MessageSquarePlus className="h-4 w-4" />
          新建检索会话
        </button>
      </div>

      <div className="flex-1 space-y-6 overflow-y-auto px-3 py-2">
        <section>
          <h3 className="mb-2 px-2 text-xs font-semibold uppercase tracking-wider text-stone-400">
            历史会话
          </h3>
          {historySessions.length > 0 ? (
            <ul className="space-y-1">
              {historySessions.map((session) => {
                const isActive = session.id === activeSessionId;
                return (
                  <li key={session.id}>
                    <button
                      className={`flex w-full items-start gap-2 rounded-md px-2 py-2 text-left transition-colors ${
                        isActive
                          ? "bg-stone-200/80 text-stone-900"
                          : "text-stone-600 hover:bg-stone-200/50 hover:text-stone-900"
                      }`}
                      onClick={() => onSelectHistorySession?.(session.id)}
                      type="button"
                    >
                      <History className="mt-0.5 h-3.5 w-3.5 shrink-0 text-stone-400" />
                      <span className="min-w-0 flex-1">
                        <span className="line-clamp-2 block text-sm">
                          {session.title}
                        </span>
                        <span className="mt-1 block text-[11px] text-stone-400">
                          {session.messageCount} 条问答 · {session.lastUpdatedLabel}
                        </span>
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
          ) : (
            <div className="rounded-md border border-dashed border-stone-200 bg-white/70 px-3 py-3 text-xs leading-5 text-stone-400">
              新建检索会话后，旧会话会归档到这里。
            </div>
          )}
        </section>

        <section>
          <h3 className="mb-2 px-2 text-xs font-semibold uppercase tracking-wider text-stone-400">
            已载入文档
          </h3>
          <ul className="space-y-0.5">
            {documents.map((document) => {
              const docStatus = document.id === processingDocId
                ? (pipelineStage ?? "pending")
                : (document.status ?? "ready");
              const showProgress =
                document.id === processingDocId && pipelineProgress > 0 && pipelineProgress < 1;
              return (
                <li key={document.id}>
                  <div className="group flex w-full items-center justify-between rounded-md px-2 py-1.5 text-sm text-stone-600">
                    <div className="flex min-w-0 flex-1 items-center gap-2">
                      <BookMarked className="h-3.5 w-3.5 shrink-0 text-cyan-700" />
                      <span className="truncate">
                        {document.name}
                      </span>
                      <DocumentStatusBadge status={docStatus} />
                    </div>
                    <div className="flex shrink-0 items-center gap-1">
                      {onDeleteDocument && (
                        <span
                          className="hidden rounded p-0.5 text-stone-300 transition-colors hover:bg-rose-100 hover:text-rose-500 group-hover:inline-block"
                          onClick={(e) => {
                            e.stopPropagation();
                            if (window.confirm(`确认删除文档 "${document.name}"？`)) {
                              onDeleteDocument(document.id);
                            }
                          }}
                          role="button"
                          tabIndex={-1}
                        >
                          <Trash2 className="h-3 w-3" />
                        </span>
                      )}
                    </div>
                  </div>
                  {showProgress && (
                    <div className="mx-2 mt-0.5 h-1 overflow-hidden rounded-full bg-stone-200">
                      <div
                        className="h-full rounded-full bg-cyan-600 transition-all"
                        style={{ width: `${Math.round(pipelineProgress * 100)}%` }}
                      />
                    </div>
                  )}
                </li>
              );
            })}
          </ul>
          {onUploadFile && (
            <div className="mt-2 px-1">
              <DocumentUpload
                disabled={isProcessing}
                onSelectFile={onUploadFile}
              />
            </div>
          )}
        </section>

        <section>
          <h3 className="mb-2 px-2 text-xs font-semibold uppercase tracking-wider text-stone-400">
            热门问题
          </h3>
          <ul className="space-y-0.5">
            {hotQuestions.slice(0, 10).map((question) => (
              <li key={question}>
                <button
                  className="flex w-full items-start gap-2 rounded-md px-2 py-1.5 text-left text-sm text-stone-600 transition-colors hover:bg-stone-200/50 hover:text-stone-900"
                  onClick={() => onSelectHotQuestion(question)}
                  type="button"
                >
                  <Search className="mt-0.5 h-3.5 w-3.5 shrink-0 text-stone-400" />
                  <span className="line-clamp-2">{question}</span>
                </button>
              </li>
            ))}
          </ul>
        </section>
      </div>
    </aside>
  );
}
