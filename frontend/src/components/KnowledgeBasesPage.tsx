import {
  Database,
  FilePlus2,
  FolderOpen,
  Link2,
  LoaderCircle,
  Plus,
  RefreshCcw,
  Trash2,
  Upload,
  X
} from "lucide-react";
import { memo, useEffect, useMemo, useRef, useState } from "react";

import DocumentStatusBadge from "./DocumentStatusBadge";
import {
  addKnowledgeBaseDocuments,
  createKnowledgeBase,
  deleteKnowledgeBase,
  getKnowledgeBase,
  removeKnowledgeBaseDocuments,
  uploadKnowledgeBaseDocuments
} from "../lib/api";
import type {
  DocumentInfo,
  KnowledgeBaseDetail,
  KnowledgeBaseInfo
} from "../lib/types";

type KnowledgeBasesPageProps = {
  documents: DocumentInfo[];
  knowledgeBases: KnowledgeBaseInfo[];
  onDocumentsChanged: () => Promise<void> | void;
  onRefreshKnowledgeBases: () => Promise<void> | void;
};

type OperationState = {
  kind: "idle" | "loading" | "error" | "success";
  message: string;
};

function formatDateTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit"
  });
}

export default memo(function KnowledgeBasesPage({
  documents,
  knowledgeBases,
  onDocumentsChanged,
  onRefreshKnowledgeBases
}: KnowledgeBasesPageProps) {
  const [selectedKbId, setSelectedKbId] = useState<string | null>(
    knowledgeBases[0]?.id ?? null
  );
  const [detail, setDetail] = useState<KnowledgeBaseDetail | null>(null);
  const [operation, setOperation] = useState<OperationState>({
    kind: "idle",
    message: ""
  });
  const [nameDraft, setNameDraft] = useState("");
  const [descriptionDraft, setDescriptionDraft] = useState("");
  const [selectedDocIds, setSelectedDocIds] = useState<string[]>([]);
  const [dangerDeleteDocs, setDangerDeleteDocs] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (selectedKbId && knowledgeBases.some((kb) => kb.id === selectedKbId)) {
      return;
    }
    setSelectedKbId(knowledgeBases[0]?.id ?? null);
  }, [knowledgeBases, selectedKbId]);

  useEffect(() => {
    let cancelled = false;
    if (!selectedKbId) {
      setDetail(null);
      return;
    }

    setOperation({ kind: "loading", message: "正在加载知识库详情" });
    getKnowledgeBase(selectedKbId)
      .then((nextDetail) => {
        if (cancelled) return;
        setDetail(nextDetail);
        setOperation({ kind: "idle", message: "" });
      })
      .catch((error) => {
        if (cancelled) return;
        setDetail(null);
        setOperation({
          kind: "error",
          message: error instanceof Error ? error.message : "知识库详情加载失败"
        });
      });

    return () => {
      cancelled = true;
    };
  }, [selectedKbId]);

  const boundDocIds = useMemo(
    () => new Set(detail?.documents.map((doc) => doc.docId) ?? []),
    [detail]
  );
  const availableDocuments = useMemo(
    () => documents.filter((document) => !boundDocIds.has(document.id)),
    [boundDocIds, documents]
  );

  async function refreshDetail(kbId = selectedKbId) {
    if (!kbId) return;
    const nextDetail = await getKnowledgeBase(kbId);
    setDetail(nextDetail);
  }

  async function refreshAll(kbId = selectedKbId) {
    await Promise.all([onRefreshKnowledgeBases(), onDocumentsChanged()]);
    await refreshDetail(kbId);
  }

  async function handleCreate() {
    const name = nameDraft.trim();
    if (!name) return;
    setOperation({ kind: "loading", message: "正在创建知识库" });
    try {
      const created = await createKnowledgeBase({
        name,
        description: descriptionDraft.trim()
      });
      setNameDraft("");
      setDescriptionDraft("");
      setSelectedKbId(created.id);
      await onRefreshKnowledgeBases();
      setOperation({ kind: "success", message: "知识库已创建" });
    } catch (error) {
      setOperation({
        kind: "error",
        message: error instanceof Error ? error.message : "创建失败"
      });
    }
  }

  async function handleAddExistingDocuments() {
    if (!selectedKbId || selectedDocIds.length === 0) return;
    setOperation({ kind: "loading", message: "正在绑定已有文档" });
    try {
      const nextDetail = await addKnowledgeBaseDocuments(
        selectedKbId,
        selectedDocIds
      );
      setDetail(nextDetail);
      setSelectedDocIds([]);
      await onRefreshKnowledgeBases();
      setOperation({ kind: "success", message: "文档已加入知识库" });
    } catch (error) {
      setOperation({
        kind: "error",
        message: error instanceof Error ? error.message : "绑定失败"
      });
    }
  }

  async function handleRemoveDocument(docId: string) {
    if (!selectedKbId) return;
    setOperation({ kind: "loading", message: "正在移出文档" });
    try {
      const nextDetail = await removeKnowledgeBaseDocuments(selectedKbId, [docId]);
      setDetail(nextDetail);
      await onRefreshKnowledgeBases();
      setOperation({ kind: "success", message: "文档已移出知识库" });
    } catch (error) {
      setOperation({
        kind: "error",
        message: error instanceof Error ? error.message : "移出失败"
      });
    }
  }

  async function handleUploadFiles(files: FileList | null) {
    if (!selectedKbId || !files || files.length === 0) return;
    const pdfFiles = Array.from(files).filter(
      (file) => file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf")
    );
    if (pdfFiles.length === 0) {
      setOperation({ kind: "error", message: "请选择 PDF 文件" });
      return;
    }
    setOperation({ kind: "loading", message: "正在上传并加入解析队列" });
    try {
      const result = await uploadKnowledgeBaseDocuments(selectedKbId, pdfFiles);
      setDetail(result.knowledge_base);
      await refreshAll(selectedKbId);
      setOperation({
        kind: result.errors.length > 0 ? "error" : "success",
        message:
          result.errors.length > 0
            ? `已上传 ${result.uploaded.length} 个，失败 ${result.errors.length} 个`
            : `已上传 ${result.uploaded.length} 个文档`
      });
    } catch (error) {
      setOperation({
        kind: "error",
        message: error instanceof Error ? error.message : "上传失败"
      });
    } finally {
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
    }
  }

  async function handleDeleteKnowledgeBase() {
    if (!selectedKbId) return;
    setOperation({ kind: "loading", message: "正在删除知识库" });
    try {
      await deleteKnowledgeBase(selectedKbId, dangerDeleteDocs);
      setDangerDeleteDocs(false);
      setSelectedKbId(null);
      setDetail(null);
      await refreshAll(null);
      setOperation({ kind: "success", message: "知识库已删除" });
    } catch (error) {
      setOperation({
        kind: "error",
        message: error instanceof Error ? error.message : "删除失败"
      });
    }
  }

  return (
    <main className="flex min-h-0 flex-1 overflow-hidden bg-stone-50">
      <aside className="flex w-80 shrink-0 flex-col border-r border-stone-200 bg-white">
        <div className="border-b border-stone-100 p-5">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-lg font-semibold text-stone-900">知识库</h1>
              <p className="mt-1 text-xs text-stone-500">
                {knowledgeBases.length} 个逻辑文档集合
              </p>
            </div>
            <button
              aria-label="刷新知识库"
              className="inline-flex h-8 w-8 items-center justify-center rounded-lg border border-stone-200 text-stone-500 hover:bg-stone-50"
              onClick={() => {
                void refreshAll();
              }}
              title="刷新"
              type="button"
            >
              <RefreshCcw className="h-4 w-4" />
            </button>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto p-3">
          {knowledgeBases.length === 0 ? (
            <div className="rounded-lg border border-dashed border-stone-200 p-4 text-sm text-stone-500">
              暂无知识库
            </div>
          ) : null}
          <div className="space-y-2">
            {knowledgeBases.map((kb) => {
              const isActive = selectedKbId === kb.id;
              return (
                <button
                  className={`block w-full rounded-lg border px-3 py-3 text-left transition ${
                    isActive
                      ? "border-cyan-300 bg-cyan-50 text-cyan-950"
                      : "border-stone-200 bg-white text-stone-700 hover:border-stone-300 hover:bg-stone-50"
                  }`}
                  key={kb.id}
                  onClick={() => setSelectedKbId(kb.id)}
                  type="button"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="truncate text-sm font-semibold">{kb.name}</p>
                      <p className="mt-1 line-clamp-2 text-xs text-stone-500">
                        {kb.description || "未填写描述"}
                      </p>
                    </div>
                    <span className="shrink-0 rounded-md bg-stone-100 px-2 py-1 text-xs text-stone-500">
                      {kb.documentCount}
                    </span>
                  </div>
                  <p className="mt-2 text-[11px] text-stone-400">
                    更新 {formatDateTime(kb.updatedAt)}
                  </p>
                </button>
              );
            })}
          </div>
        </div>

        <div className="border-t border-stone-100 p-4">
          <div className="space-y-2">
            <input
              className="w-full rounded-lg border border-stone-200 px-3 py-2 text-sm outline-none focus:border-cyan-500"
              onChange={(event) => setNameDraft(event.target.value)}
              placeholder="新知识库名称"
              value={nameDraft}
            />
            <textarea
              className="min-h-16 w-full resize-none rounded-lg border border-stone-200 px-3 py-2 text-sm outline-none focus:border-cyan-500"
              onChange={(event) => setDescriptionDraft(event.target.value)}
              placeholder="描述"
              value={descriptionDraft}
            />
            <button
              className="inline-flex w-full items-center justify-center gap-2 rounded-lg bg-stone-900 px-3 py-2 text-sm font-medium text-white hover:bg-stone-800 disabled:cursor-not-allowed disabled:bg-stone-300"
              disabled={!nameDraft.trim() || operation.kind === "loading"}
              onClick={() => {
                void handleCreate();
              }}
              type="button"
            >
              <Plus className="h-4 w-4" />
              创建知识库
            </button>
          </div>
        </div>
      </aside>

      <section className="flex min-w-0 flex-1 flex-col overflow-hidden">
        <div className="border-b border-stone-200 bg-white px-6 py-4">
          <div className="flex items-center justify-between gap-4">
            <div className="min-w-0">
              <div className="flex items-center gap-2 text-sm font-medium text-cyan-800">
                <FolderOpen className="h-4 w-4" />
                <span>{detail?.name ?? "选择一个知识库"}</span>
              </div>
              <p className="mt-1 max-w-3xl truncate text-sm text-stone-500">
                {detail?.description || "知识库只管理文档分组；删除知识库默认不会删除底层文档。"}
              </p>
            </div>
            <div className="flex items-center gap-2">
              {operation.kind === "loading" ? (
                <span className="inline-flex items-center gap-1.5 text-sm text-stone-500">
                  <LoaderCircle className="h-4 w-4 animate-spin" />
                  {operation.message}
                </span>
              ) : operation.kind === "error" ? (
                <span className="max-w-80 truncate text-sm text-rose-600">
                  {operation.message}
                </span>
              ) : operation.kind === "success" ? (
                <span className="max-w-80 truncate text-sm text-emerald-700">
                  {operation.message}
                </span>
              ) : null}
            </div>
          </div>
        </div>

        {detail ? (
          <div className="grid min-h-0 flex-1 grid-cols-[minmax(0,1fr)_320px] gap-0 overflow-hidden">
            <div className="overflow-y-auto p-6">
              <div className="mb-4 flex items-center justify-between">
                <div>
                  <h2 className="text-sm font-semibold text-stone-900">
                    文档列表
                  </h2>
                  <p className="mt-1 text-xs text-stone-500">
                    {detail.documents.length} 个文档绑定到该知识库
                  </p>
                </div>
                <input
                  ref={fileInputRef}
                  accept=".pdf,application/pdf"
                  className="hidden"
                  multiple
                  onChange={(event) => {
                    void handleUploadFiles(event.currentTarget.files);
                  }}
                  type="file"
                />
                <button
                  className="inline-flex items-center gap-2 rounded-lg border border-stone-200 bg-white px-3 py-2 text-sm text-stone-700 hover:bg-stone-50 disabled:cursor-not-allowed disabled:text-stone-400"
                  disabled={operation.kind === "loading"}
                  onClick={() => fileInputRef.current?.click()}
                  type="button"
                >
                  <Upload className="h-4 w-4" />
                  上传 PDF
                </button>
              </div>

              {detail.documents.length === 0 ? (
                <div className="flex min-h-64 flex-col items-center justify-center rounded-lg border border-dashed border-stone-200 bg-white text-center text-stone-500">
                  <Database className="mb-3 h-8 w-8 text-stone-300" />
                  <p className="text-sm">该知识库还没有文档</p>
                </div>
              ) : (
                <div className="overflow-hidden rounded-lg border border-stone-200 bg-white">
                  <table className="w-full border-collapse text-sm">
                    <thead className="bg-stone-50 text-xs text-stone-500">
                      <tr>
                        <th className="px-4 py-3 text-left font-medium">文档</th>
                        <th className="px-4 py-3 text-left font-medium">状态</th>
                        <th className="px-4 py-3 text-left font-medium">加入时间</th>
                        <th className="px-4 py-3 text-right font-medium">操作</th>
                      </tr>
                    </thead>
                    <tbody>
                      {detail.documents.map((document) => (
                        <tr className="border-t border-stone-100" key={document.docId}>
                          <td className="px-4 py-3">
                            <div className="font-medium text-stone-800">
                              {document.fileName}
                            </div>
                            <div className="mt-1 font-mono text-xs text-stone-400">
                              {document.docId}
                            </div>
                          </td>
                          <td className="px-4 py-3">
                            <DocumentStatusBadge status={document.status} />
                          </td>
                          <td className="px-4 py-3 text-stone-500">
                            {formatDateTime(document.addedAt)}
                          </td>
                          <td className="px-4 py-3 text-right">
                            <button
                              aria-label="从知识库移出文档"
                              className="inline-flex h-8 w-8 items-center justify-center rounded-lg text-stone-400 hover:bg-stone-100 hover:text-rose-600"
                              onClick={() => {
                                void handleRemoveDocument(document.docId);
                              }}
                              title="移出文档"
                              type="button"
                            >
                              <X className="h-4 w-4" />
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>

            <aside className="overflow-y-auto border-l border-stone-200 bg-white p-5">
              <section>
                <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-stone-900">
                  <Link2 className="h-4 w-4" />
                  绑定已有文档
                </div>
                <div className="max-h-64 space-y-2 overflow-y-auto rounded-lg border border-stone-200 p-2">
                  {availableDocuments.length === 0 ? (
                    <p className="px-2 py-3 text-sm text-stone-500">
                      没有可添加的已有文档
                    </p>
                  ) : null}
                  {availableDocuments.map((document) => {
                    const checked = selectedDocIds.includes(document.id);
                    return (
                      <label
                        className="flex cursor-pointer items-start gap-2 rounded-md px-2 py-2 hover:bg-stone-50"
                        key={document.id}
                      >
                        <input
                          checked={checked}
                          className="mt-1"
                          onChange={(event) => {
                            setSelectedDocIds((current) =>
                              event.target.checked
                                ? [...current, document.id]
                                : current.filter((id) => id !== document.id)
                            );
                          }}
                          type="checkbox"
                        />
                        <span className="min-w-0">
                          <span className="block truncate text-sm text-stone-700">
                            {document.name || document.title || document.id}
                          </span>
                          <span className="block truncate font-mono text-xs text-stone-400">
                            {document.id}
                          </span>
                        </span>
                      </label>
                    );
                  })}
                </div>
                <button
                  className="mt-3 inline-flex w-full items-center justify-center gap-2 rounded-lg border border-stone-200 px-3 py-2 text-sm text-stone-700 hover:bg-stone-50 disabled:cursor-not-allowed disabled:text-stone-400"
                  disabled={selectedDocIds.length === 0 || operation.kind === "loading"}
                  onClick={() => {
                    void handleAddExistingDocuments();
                  }}
                  type="button"
                >
                  <FilePlus2 className="h-4 w-4" />
                  加入 {selectedDocIds.length} 个文档
                </button>
              </section>

              <section className="mt-8 border-t border-stone-100 pt-5">
                <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-rose-800">
                  <Trash2 className="h-4 w-4" />
                  删除
                </div>
                <label className="flex items-start gap-2 text-sm text-stone-600">
                  <input
                    checked={dangerDeleteDocs}
                    className="mt-1"
                    onChange={(event) => setDangerDeleteDocs(event.target.checked)}
                    type="checkbox"
                  />
                  <span>同时删除仅属于该知识库的底层索引文档</span>
                </label>
                <button
                  className="mt-3 inline-flex w-full items-center justify-center gap-2 rounded-lg border border-rose-200 px-3 py-2 text-sm text-rose-700 hover:bg-rose-50 disabled:cursor-not-allowed disabled:text-stone-400"
                  disabled={operation.kind === "loading"}
                  onClick={() => {
                    void handleDeleteKnowledgeBase();
                  }}
                  type="button"
                >
                  <Trash2 className="h-4 w-4" />
                  删除知识库
                </button>
              </section>
            </aside>
          </div>
        ) : (
          <div className="flex flex-1 items-center justify-center text-stone-500">
            <div className="text-center">
              <FolderOpen className="mx-auto mb-3 h-8 w-8 text-stone-300" />
              <p className="text-sm">请选择或创建知识库</p>
            </div>
          </div>
        )}
      </section>
    </main>
  );
});
