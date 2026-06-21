import {
  AlertTriangle,
  Database,
  FileSearch,
  LoaderCircle,
  RefreshCcw,
  RotateCcw,
  Search,
  Trash2
} from "lucide-react";
import { memo, useEffect, useMemo, useState } from "react";

import {
  deleteDocumentIndex,
  getIndexOverview,
  inspectDocumentIndex,
  rebuildDocumentIndex
} from "../lib/api";
import type {
  DocumentIndexInspection,
  DocumentInfo,
  IndexBackendStats,
  IndexOverview
} from "../lib/types";

type IndexAdminPageProps = {
  documents: DocumentInfo[];
};

type OperationState = {
  kind: "idle" | "loading" | "error" | "success";
  message: string;
};

function formatCount(value: unknown): string {
  return typeof value === "number" ? value.toLocaleString("zh-CN") : "0";
}

function BackendCard({
  title,
  stats,
  countLabel
}: {
  title: string;
  stats: IndexBackendStats;
  countLabel: string;
}) {
  const ok = Boolean(stats.exists) && stats.schema_ok !== false && !stats.error;
  const fields = stats.fields ?? stats.mapping_fields ?? [];
  return (
    <div className="rounded-lg border border-stone-200 bg-white p-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Database className="h-4 w-4 text-cyan-700" />
          <h2 className="text-sm font-semibold text-stone-800">{title}</h2>
        </div>
        <span
          className={`rounded-full px-2 py-0.5 text-xs ${
            ok
              ? "bg-emerald-50 text-emerald-700"
              : "bg-amber-50 text-amber-700"
          }`}
        >
          {ok ? "正常" : "需检查"}
        </span>
      </div>
      <div className="mt-4 grid grid-cols-2 gap-3 text-sm">
        <div>
          <p className="text-xs text-stone-400">名称</p>
          <p className="mt-1 truncate font-medium text-stone-800">
            {stats.collection || stats.index || "-"}
          </p>
        </div>
        <div>
          <p className="text-xs text-stone-400">{countLabel}</p>
          <p className="mt-1 font-medium text-stone-800">
            {formatCount(stats.entity_count ?? stats.document_count)}
          </p>
        </div>
      </div>
      {fields.length > 0 ? (
        <div className="mt-4">
          <p className="text-xs text-stone-400">字段</p>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {fields.slice(0, 10).map((field) => (
              <span
                className="rounded border border-stone-200 bg-stone-50 px-1.5 py-0.5 text-[11px] text-stone-600"
                key={field}
              >
                {field}
              </span>
            ))}
          </div>
        </div>
      ) : null}
      {stats.error ? (
        <p className="mt-3 text-xs leading-5 text-rose-600">{stats.error}</p>
      ) : null}
    </div>
  );
}

export default memo(function IndexAdminPage({ documents }: IndexAdminPageProps) {
  const [overview, setOverview] = useState<IndexOverview | null>(null);
  const [inspection, setInspection] = useState<DocumentIndexInspection | null>(null);
  const [docIdDraft, setDocIdDraft] = useState(documents[0]?.id ?? "");
  const [operation, setOperation] = useState<OperationState>({
    kind: "idle",
    message: ""
  });

  const docOptions = useMemo(
    () => documents.map((document) => ({ id: document.id, name: document.name })),
    [documents]
  );

  async function refreshOverview(options?: { quiet?: boolean }) {
    if (!options?.quiet) {
      setOperation({ kind: "loading", message: "正在加载索引概览" });
    }
    try {
      const nextOverview = await getIndexOverview();
      setOverview(nextOverview);
      if (!options?.quiet) {
        setOperation({ kind: "idle", message: "" });
      }
    } catch (error) {
      setOperation({
        kind: "error",
        message: error instanceof Error ? error.message : "索引概览加载失败"
      });
    }
  }

  useEffect(() => {
    void refreshOverview();
  }, []);

  async function handleInspect() {
    const docId = docIdDraft.trim();
    if (!docId) return;
    setOperation({ kind: "loading", message: "正在查询文档索引" });
    try {
      const nextInspection = await inspectDocumentIndex(docId, 5);
      setInspection(nextInspection);
      setOperation({ kind: "success", message: "文档索引已加载" });
    } catch (error) {
      setInspection(null);
      setOperation({
        kind: "error",
        message: error instanceof Error ? error.message : "文档索引查询失败"
      });
    }
  }

  async function handleDelete() {
    const docId = docIdDraft.trim();
    if (!docId) return;
    if (!window.confirm(`确认删除 ${docId} 在 Milvus 和 Elasticsearch 中的索引？`)) {
      return;
    }
    setOperation({ kind: "loading", message: "正在删除文档索引" });
    try {
      const result = await deleteDocumentIndex(docId);
      setOperation({
        kind: "success",
        message: `已删除 Milvus ${result.deleted.milvus} 条，ES ${result.deleted.elasticsearch} 条`
      });
      setInspection(null);
      await refreshOverview({ quiet: true });
    } catch (error) {
      setOperation({
        kind: "error",
        message: error instanceof Error ? error.message : "删除失败"
      });
    }
  }

  async function handleRebuild() {
    const docId = docIdDraft.trim();
    if (!docId) return;
    if (!window.confirm(`确认从 data/parsed 重建 ${docId} 的索引？`)) {
      return;
    }
    setOperation({ kind: "loading", message: "正在重建文档索引" });
    try {
      const result = await rebuildDocumentIndex(docId, true);
      setOperation({
        kind: "success",
        message: `已重建 ${result.chunks} 个 chunks`
      });
      await refreshOverview({ quiet: true });
      const nextInspection = await inspectDocumentIndex(docId, 5);
      setInspection(nextInspection);
    } catch (error) {
      setOperation({
        kind: "error",
        message: error instanceof Error ? error.message : "重建失败"
      });
    }
  }

  const busy = operation.kind === "loading";

  return (
    <main className="flex flex-1 flex-col overflow-hidden bg-stone-50">
      <div className="border-b border-stone-200 bg-white px-8 py-5">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-lg font-semibold text-stone-900">索引管理</h1>
            <p className="mt-1 text-sm text-stone-500">
              管理 Milvus 向量索引与 Elasticsearch 文本索引。
            </p>
          </div>
          <button
            className="inline-flex items-center gap-2 rounded-md border border-stone-200 bg-white px-3 py-2 text-sm font-medium text-stone-700 hover:bg-stone-50 disabled:cursor-not-allowed disabled:opacity-60"
            disabled={busy}
            onClick={() => {
              void refreshOverview();
            }}
            type="button"
          >
            {busy ? (
              <LoaderCircle className="h-4 w-4 animate-spin" />
            ) : (
              <RefreshCcw className="h-4 w-4" />
            )}
            刷新
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-8 py-6">
        {operation.message ? (
          <div
            className={`mb-4 rounded-md border px-3 py-2 text-sm ${
              operation.kind === "error"
                ? "border-rose-200 bg-rose-50 text-rose-700"
                : operation.kind === "success"
                  ? "border-emerald-200 bg-emerald-50 text-emerald-700"
                  : "border-cyan-200 bg-cyan-50 text-cyan-700"
            }`}
          >
            {operation.message}
          </div>
        ) : null}

        <section className="grid gap-4 lg:grid-cols-2">
          <BackendCard
            countLabel="向量数"
            stats={overview?.milvus ?? { exists: false }}
            title="Milvus"
          />
          <BackendCard
            countLabel="文档数"
            stats={overview?.elasticsearch ?? { exists: false }}
            title="Elasticsearch"
          />
        </section>

        <section className="mt-6 rounded-lg border border-stone-200 bg-white p-4">
          <div className="flex flex-wrap items-end gap-3">
            <label className="min-w-72 flex-1 text-sm">
              <span className="mb-1 block text-xs font-medium text-stone-500">
                文档 ID
              </span>
              <input
                className="w-full rounded-md border border-stone-200 bg-white px-3 py-2 text-sm outline-none focus:border-cyan-500"
                list="index-documents"
                onChange={(event) => setDocIdDraft(event.target.value)}
                placeholder="EN1990_2002"
                value={docIdDraft}
              />
              <datalist id="index-documents">
                {docOptions.map((document) => (
                  <option key={document.id} value={document.id}>
                    {document.name}
                  </option>
                ))}
              </datalist>
            </label>
            <button
              className="inline-flex items-center gap-2 rounded-md bg-stone-900 px-3 py-2 text-sm font-medium text-white hover:bg-stone-800 disabled:cursor-not-allowed disabled:opacity-60"
              disabled={busy || !docIdDraft.trim()}
              onClick={handleInspect}
              type="button"
            >
              <Search className="h-4 w-4" />
              查询
            </button>
            <button
              className="inline-flex items-center gap-2 rounded-md border border-stone-200 bg-white px-3 py-2 text-sm font-medium text-stone-700 hover:bg-stone-50 disabled:cursor-not-allowed disabled:opacity-60"
              disabled={busy || !docIdDraft.trim()}
              onClick={handleRebuild}
              type="button"
            >
              <RotateCcw className="h-4 w-4" />
              重建
            </button>
            <button
              className="inline-flex items-center gap-2 rounded-md border border-rose-200 bg-white px-3 py-2 text-sm font-medium text-rose-700 hover:bg-rose-50 disabled:cursor-not-allowed disabled:opacity-60"
              disabled={busy || !docIdDraft.trim()}
              onClick={handleDelete}
              type="button"
            >
              <Trash2 className="h-4 w-4" />
              删除索引
            </button>
          </div>
        </section>

        <section className="mt-6 grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(320px,420px)]">
          <div className="rounded-lg border border-stone-200 bg-white p-4">
            <div className="mb-3 flex items-center gap-2">
              <FileSearch className="h-4 w-4 text-cyan-700" />
              <h2 className="text-sm font-semibold text-stone-800">
                文档索引详情
              </h2>
            </div>
            {inspection ? (
              <div className="space-y-4">
                <div className="grid grid-cols-3 gap-3 text-sm">
                  <div className="rounded-md bg-stone-50 p-3">
                    <p className="text-xs text-stone-400">doc_id</p>
                    <p className="mt-1 truncate font-medium">{inspection.doc_id}</p>
                  </div>
                  <div className="rounded-md bg-stone-50 p-3">
                    <p className="text-xs text-stone-400">Milvus</p>
                    <p className="mt-1 font-medium">
                      {inspection.milvus_count.toLocaleString("zh-CN")}
                    </p>
                  </div>
                  <div className="rounded-md bg-stone-50 p-3">
                    <p className="text-xs text-stone-400">Elasticsearch</p>
                    <p className="mt-1 font-medium">
                      {inspection.elasticsearch_count.toLocaleString("zh-CN")}
                    </p>
                  </div>
                </div>
                <div className="space-y-3">
                  {inspection.samples.map((sample) => (
                    <article
                      className="rounded-md border border-stone-200 bg-stone-50 p-3"
                      key={sample.chunk_id}
                    >
                      <div className="flex items-center justify-between gap-2 text-xs text-stone-500">
                        <span className="truncate font-mono">{sample.chunk_id}</span>
                        <span className="shrink-0 rounded bg-white px-1.5 py-0.5">
                          {sample.element_type || "text"}
                        </span>
                      </div>
                      <p className="mt-2 text-xs text-stone-500">
                        {sample.source_title || sample.source}
                        {sample.page_numbers.length > 0
                          ? ` · 页 ${sample.page_numbers.join(", ")}`
                          : ""}
                      </p>
                      <p className="mt-2 line-clamp-4 text-sm leading-6 text-stone-700">
                        {sample.content_preview}
                      </p>
                    </article>
                  ))}
                  {inspection.samples.length === 0 ? (
                    <div className="rounded-md border border-dashed border-stone-200 p-4 text-sm text-stone-400">
                      没有 sample chunks。
                    </div>
                  ) : null}
                </div>
              </div>
            ) : (
              <div className="rounded-md border border-dashed border-stone-200 p-6 text-sm text-stone-400">
                输入 doc_id 后点击查询。
              </div>
            )}
          </div>

          <div className="rounded-lg border border-stone-200 bg-white p-4">
            <div className="mb-3 flex items-center gap-2">
              <AlertTriangle className="h-4 w-4 text-amber-600" />
              <h2 className="text-sm font-semibold text-stone-800">索引 sources</h2>
            </div>
            <div className="max-h-[520px] space-y-2 overflow-y-auto">
              {(overview?.sources ?? []).map((source) => (
                <button
                  className="flex w-full items-center justify-between gap-3 rounded-md px-2 py-2 text-left text-sm hover:bg-stone-50"
                  key={source.source}
                  onClick={() => setDocIdDraft(source.source)}
                  type="button"
                >
                  <span className="min-w-0 truncate text-stone-700">
                    {source.source}
                  </span>
                  <span className="shrink-0 rounded bg-stone-100 px-2 py-0.5 text-xs text-stone-500">
                    {source.elasticsearch_count.toLocaleString("zh-CN")}
                  </span>
                </button>
              ))}
              {!overview?.sources?.length ? (
                <div className="rounded-md border border-dashed border-stone-200 p-4 text-sm text-stone-400">
                  暂无 source 聚合数据。
                </div>
              ) : null}
            </div>
          </div>
        </section>
      </div>
    </main>
  );
});
