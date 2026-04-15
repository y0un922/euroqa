import {
  BookMarked,
  Library,
  MessageSquarePlus,
  Search,
  Trash2
} from "lucide-react";

import type { DocumentInfo, DocumentStatus, GlossaryEntry } from "../lib/types";
import DocumentStatusBadge from "./DocumentStatusBadge";
import DocumentUpload from "./DocumentUpload";

type SidebarProps = {
  documents: DocumentInfo[];
  glossary: GlossaryEntry[];
  hotQuestions: string[];
  onNewSession: () => void;
  onSelectHotQuestion: (question: string) => void;
  onUploadFile?: (file: File) => void;
  onDeleteDocument?: (docId: string) => void;
  processingDocId?: string | null;
  pipelineStage?: DocumentStatus | null;
  pipelineProgress?: number;
};

export default function Sidebar({
  documents,
  glossary,
  hotQuestions,
  onNewSession,
  onSelectHotQuestion,
  onUploadFile,
  onDeleteDocument,
  processingDocId,
  pipelineStage,
  pipelineProgress = 0
}: SidebarProps) {
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
            {hotQuestions.slice(0, 4).map((question) => (
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

        <section>
          <h3 className="mb-2 px-2 text-xs font-semibold uppercase tracking-wider text-stone-400">
            术语预览
          </h3>
          <ul className="space-y-1.5">
            {glossary.slice(0, 5).map((entry) => (
              <li
                key={`${entry.en}-${entry.zh[0]}`}
                className="rounded-md border border-stone-200 bg-white px-3 py-2 text-xs shadow-sm"
              >
                <div className="mb-1 flex items-center gap-1.5 text-stone-700">
                  <Library className="h-3.5 w-3.5 text-cyan-700" />
                  <span className="font-medium">{entry.zh[0]}</span>
                </div>
                <div className="font-mono text-[11px] text-stone-500">
                  {entry.en}
                </div>
              </li>
            ))}
          </ul>
        </section>
      </div>
    </aside>
  );
}
