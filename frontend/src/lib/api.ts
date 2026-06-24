export type SseEventMessage = {
  event: string;
  data: string;
};

export type SseParseResult = {
  events: SseEventMessage[];
  remaining: string;
};

export type DemoDocumentInfo = {
  id: string;
  name: string;
  title: string;
  total_pages: number;
  chunk_count: number;
};

import type {
  ConversationSessionDeleteResponse,
  ConversationSessionListResponse,
  ConversationSessionResponse,
  DocumentInfo,
  DocumentUploadResponse,
  DocumentUploadToMinioResponse,
  GlossaryEntry,
  KnowledgeBaseDeleteResult,
  KnowledgeBaseDetail,
  KnowledgeBaseInfo,
  KnowledgeBaseUploadResult,
  LlmSettingsResponse,
  PipelineProgressEvent,
  QueryRequestPayload,
  QueryResponse,
  QueryProgressEvent,
  Source,
  SourceTranslationRequest,
  SourceTranslationResponse,
  StreamDonePayload,
  StreamCommentaryPayload,
  StreamErrorPayload,
  StreamReasoningPayload,
  SuggestResponse,
  ToolProgressEvent,
} from "./types";

import { clearToken, dispatchAuthExpired, getToken } from "./auth";

const normalize = (value: string): string =>
  value.toLowerCase().replace(/[^a-z0-9]+/g, "");

function isOpaqueDocumentId(value: string): boolean {
  const trimmed = value.trim();
  return /^[a-f0-9]{24,}$/i.test(trimmed) || /^[a-f0-9-]{32,}$/i.test(trimmed);
}

function findDocumentById(
  documentId: string,
  documents: DocumentInfo[],
): DocumentInfo | null {
  if (!documentId) {
    return null;
  }

  return documents.find((document) => document.id === documentId) ?? null;
}

function findDocumentForSource(
  source: Source,
  documents: DocumentInfo[],
): DocumentInfo | null {
  const sourceDocumentId = source.document_id || source.docId || "";
  const exactDocument = findDocumentById(sourceDocumentId, documents);
  if (exactDocument) {
    return exactDocument;
  }

  const matchedDocumentId = matchSourceToDocumentId(source.file, documents);
  return matchedDocumentId
    ? findDocumentById(matchedDocumentId, documents)
    : null;
}

function resolveSourceDisplayTitle(
  source: Source,
  document: DocumentInfo | null,
): string {
  const sourceFile = source.file?.trim();
  const explicitDisplayTitle =
    source.display_title?.trim() ||
    source.displayTitle?.trim() ||
    source.source_title?.trim() ||
    source.sourceTitle?.trim();
  if (sourceFile && !isOpaqueDocumentId(sourceFile)) {
    return sourceFile;
  }

  return (
    explicitDisplayTitle ||
    source.title?.trim() ||
    document?.name?.trim() ||
    document?.title?.trim() ||
    sourceFile ||
    source.document_id?.trim() ||
    source.docId?.trim() ||
    "未命名文档"
  );
}

export function parseSseBuffer(buffer: string): SseParseResult {
  const normalizedBuffer = buffer.replace(/\r\n/g, "\n");
  const segments = normalizedBuffer.split("\n\n");
  const completeSegments = normalizedBuffer.endsWith("\n\n")
    ? segments.filter(Boolean)
    : segments.slice(0, -1).filter(Boolean);
  const remaining = normalizedBuffer.endsWith("\n\n")
    ? ""
    : (segments.at(-1) ?? "");

  const events = completeSegments.map((segment) => {
    const lines = segment.split("\n");
    const event = lines
      .find((line) => line.startsWith("event:"))
      ?.slice("event:".length)
      .trim();
    const data = lines
      .filter((line) => line.startsWith("data:"))
      .map((line) => line.slice("data:".length).trim())
      .join("\n");

    return {
      event: event ?? "message",
      data,
    };
  });

  return { events, remaining };
}

export async function readSseStream(
  stream: ReadableStream<Uint8Array>,
  onMessage: (message: SseEventMessage) => void,
  signal?: AbortSignal,
): Promise<{ receivedDone: boolean }> {
  const reader = stream.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let receivedDone = false;

  // 注册 abort 监听，主动取消 reader
  const cancelReader = () => {
    void reader.cancel();
  };
  signal?.addEventListener("abort", cancelReader);

  // 已经 aborted 则直接返回
  if (signal?.aborted) {
    await reader.cancel();
    signal.removeEventListener("abort", cancelReader);
    return { receivedDone: false };
  }

  try {
    while (true) {
      if (signal?.aborted) {
        await reader.cancel();
        return { receivedDone: false };
      }

      const { done, value } = await reader.read();
      if (done) {
        break;
      }

      if (signal?.aborted) {
        await reader.cancel();
        return { receivedDone: false };
      }

      buffer += decoder.decode(value, { stream: true });
      const parsed = parseSseBuffer(buffer);
      for (const event of parsed.events) {
        if (event.event === "done") {
          receivedDone = true;
        }
        onMessage(event);
      }
      buffer = parsed.remaining;
    }

    if (!signal?.aborted) {
      buffer += decoder.decode();
      const parsed = parseSseBuffer(buffer);
      for (const event of parsed.events) {
        if (event.event === "done") {
          receivedDone = true;
        }
        onMessage(event);
      }
    }
  } catch (error) {
    // 用户主动中断不视为错误
    if (signal?.aborted) {
      return { receivedDone: false };
    }
    throw new Error(error instanceof Error ? error.message : "流式连接中断");
  } finally {
    signal?.removeEventListener("abort", cancelReader);
  }

  return { receivedDone };
}

function getApiBaseUrl(): string {
  return import.meta.env?.VITE_API_BASE_URL?.trim() || "http://localhost:8080";
}

function buildApiUrl(path: string): string {
  return new URL(path, getApiBaseUrl()).toString();
}

function withAuthHeaders(extra?: HeadersInit): Headers {
  const headers = new Headers(extra);
  const token = getToken();
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  return headers;
}

function handleAuthFailure(response: Response, sentToken: string | null): void {
  if (response.status !== 401) return;
  if (sentToken && getToken() !== sentToken) return;
  clearToken();
  dispatchAuthExpired();
}

async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const sentToken = getToken();
  const headers = withAuthHeaders(init?.headers);
  if (!headers.has("Accept")) headers.set("Accept", "application/json");
  if (!headers.has("Content-Type"))
    headers.set("Content-Type", "application/json");

  const response = await fetch(buildApiUrl(path), { ...init, headers });

  if (!response.ok) {
    handleAuthFailure(response, sentToken);
    const detail = await response.text();
    throw new Error(detail || `Request failed: ${response.status}`);
  }

  return (await response.json()) as T;
}

export async function checkAuthRequired(): Promise<boolean> {
  const res = await fetch(buildApiUrl("/api/v1/auth/status"), {
    headers: { Accept: "application/json" },
  });
  const data = (await res.json()) as { required: boolean };
  return data.required;
}

export async function login(password: string): Promise<{ token: string }> {
  return fetchJson<{ token: string }>("/api/v1/auth/login", {
    method: "POST",
    body: JSON.stringify({ password }),
  });
}

function appendTokenParam(url: string): string {
  const token = getToken();
  if (!token) return url;
  const sep = url.includes("?") ? "&" : "?";
  return `${url}${sep}token=${encodeURIComponent(token)}`;
}

export function buildDocumentPreviewUrl(
  documentId: string,
  page: number,
): string {
  return appendTokenParam(
    buildApiUrl(
      `/api/v1/documents/${encodeURIComponent(documentId)}/page/${page}`,
    ),
  );
}

export function buildDocumentFileUrl(documentId: string): string {
  return appendTokenParam(
    buildApiUrl(`/api/v1/documents/${encodeURIComponent(documentId)}/file`),
  );
}

export function buildReferenceRecords(
  sources: Source[],
  documents: DocumentInfo[],
  confidence: StreamDonePayload["confidence"],
  relatedRefs: string[],
  messageId?: string,
) {
  const prefix = messageId ? `${messageId}-ref` : "ref";
  return sources.map((source, index) => {
    const sourceDocumentId = source.document_id || source.docId || "";
    const matchedDocument = findDocumentForSource(source, documents);
    const hasDocumentId = Boolean(
      findDocumentById(sourceDocumentId, documents),
    );
    const displayTitle = resolveSourceDisplayTitle(source, matchedDocument);
    return {
      id: `${prefix}-${index + 1}`,
      source,
      documentId: hasDocumentId
        ? sourceDocumentId
        : matchedDocument?.id || sourceDocumentId || null,
      displayTitle,
      confidence,
      relatedRefs,
    };
  });
}

export function getPreferredReferenceIndex(sources: Source[]): number {
  const clauseIndex = sources.findIndex(
    (source) => source.clause.trim().length > 0,
  );
  return clauseIndex >= 0 ? clauseIndex : 0;
}

export async function listDocuments(): Promise<DocumentInfo[]> {
  return fetchJson<DocumentInfo[]>("/api/v1/documents", { method: "GET" });
}

export async function listGlossary(query?: string): Promise<GlossaryEntry[]> {
  const path = query
    ? `/api/v1/glossary?q=${encodeURIComponent(query)}`
    : "/api/v1/glossary";
  return fetchJson<GlossaryEntry[]>(path, { method: "GET" });
}

export async function getSuggestions(): Promise<SuggestResponse> {
  return fetchJson<SuggestResponse>("/api/v1/suggest", { method: "GET" });
}

export async function getLlmSettings(): Promise<LlmSettingsResponse> {
  return fetchJson<LlmSettingsResponse>("/api/v1/settings/llm", {
    method: "GET",
  });
}

export async function translateSource(
  payload: SourceTranslationRequest,
): Promise<SourceTranslationResponse> {
  return fetchJson<SourceTranslationResponse>("/api/v1/sources/translate", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function buildChatQueryPayload({
  question,
  kbIds,
  sessionId,
  llm,
}: {
  question: string;
  kbIds?: string[];
  sessionId: string;
  llm?: QueryRequestPayload["llm"];
}): QueryRequestPayload {
  return {
    question,
    sessionId,
    ...(kbIds && kbIds.length > 0 ? { kbIds } : {}),
    ...(llm ? { llm } : {}),
  };
}

export async function query(
  payload: QueryRequestPayload,
): Promise<QueryResponse> {
  return fetchJson<QueryResponse>("/api/v1/query", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function listKnowledgeBases(): Promise<KnowledgeBaseInfo[]> {
  return fetchJson<KnowledgeBaseInfo[]>("/api/v1/knowledge-bases", {
    method: "GET",
  });
}

export async function getKnowledgeBase(
  kbId: string,
): Promise<KnowledgeBaseDetail> {
  return fetchJson<KnowledgeBaseDetail>(
    `/api/v1/knowledge-bases/${encodeURIComponent(kbId)}`,
    { method: "GET" },
  );
}

export async function createKnowledgeBase(payload: {
  name: string;
  description?: string;
}): Promise<KnowledgeBaseInfo> {
  return fetchJson<KnowledgeBaseInfo>("/api/v1/knowledge-bases", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function updateKnowledgeBase(
  kbId: string,
  payload: { name?: string; description?: string },
): Promise<KnowledgeBaseInfo> {
  return fetchJson<KnowledgeBaseInfo>(
    `/api/v1/knowledge-bases/${encodeURIComponent(kbId)}`,
    {
      method: "PATCH",
      body: JSON.stringify(payload),
    },
  );
}

export async function deleteKnowledgeBase(
  kbId: string,
  deleteDocuments = false,
): Promise<KnowledgeBaseDeleteResult> {
  return fetchJson<KnowledgeBaseDeleteResult>(
    `/api/v1/knowledge-bases/${encodeURIComponent(kbId)}?delete_documents=${String(
      deleteDocuments,
    )}`,
    { method: "DELETE" },
  );
}

export async function addKnowledgeBaseDocuments(
  kbId: string,
  docIds: string[],
): Promise<KnowledgeBaseDetail> {
  return fetchJson<KnowledgeBaseDetail>(
    `/api/v1/knowledge-bases/${encodeURIComponent(kbId)}/documents`,
    {
      method: "POST",
      body: JSON.stringify({ docIds }),
    },
  );
}

export async function removeKnowledgeBaseDocuments(
  kbId: string,
  docIds: string[],
): Promise<KnowledgeBaseDetail> {
  return fetchJson<KnowledgeBaseDetail>(
    `/api/v1/knowledge-bases/${encodeURIComponent(kbId)}/documents`,
    {
      method: "DELETE",
      body: JSON.stringify({ docIds }),
    },
  );
}

export async function uploadKnowledgeBaseDocuments(
  kbId: string,
  files: File[],
  contextSummaryEnabled = true,
): Promise<KnowledgeBaseUploadResult> {
  const sentToken = getToken();
  const formData = new FormData();
  for (const file of files) {
    formData.append("files", file);
  }
  formData.append("contextSummaryEnabled", String(contextSummaryEnabled));

  const response = await fetch(
    buildApiUrl(`/api/v1/knowledge-bases/${encodeURIComponent(kbId)}/upload`),
    {
      method: "POST",
      headers: withAuthHeaders(),
      body: formData,
    },
  );

  if (!response.ok) {
    handleAuthFailure(response, sentToken);
    const detail = await response.text();
    throw new Error(detail || `Upload failed: ${response.status}`);
  }

  return (await response.json()) as KnowledgeBaseUploadResult;
}

export async function getConversationSession(
  sessionId: string,
): Promise<ConversationSessionResponse> {
  return fetchJson<ConversationSessionResponse>(
    `/api/v1/sessions/${encodeURIComponent(sessionId)}`,
    { method: "GET" },
  );
}

export async function getConversationSessions(
  userId: string,
): Promise<ConversationSessionListResponse> {
  return fetchJson<ConversationSessionListResponse>(
    `/api/v1/sessions?userId=${encodeURIComponent(userId)}`,
    { method: "GET" },
  );
}

export async function deleteConversationSession(
  sessionId: string,
): Promise<ConversationSessionDeleteResponse> {
  return fetchJson<ConversationSessionDeleteResponse>(
    `/api/v1/sessions/${encodeURIComponent(sessionId)}`,
    { method: "DELETE" },
  );
}

export async function queryStream(
  payload: QueryRequestPayload,
  handlers: {
    onReasoning: (text: string) => void;
    onChunk: (text: string) => void;
    onProgress?: (payload: QueryProgressEvent) => void;
    onCommentary?: (text: string) => void;
    onToolProgress?: (payload: ToolProgressEvent) => void;
    onDone: (payload: StreamDonePayload) => void;
  },
  signal?: AbortSignal,
): Promise<void> {
  const sentToken = getToken();
  const response = await fetch(buildApiUrl("/api/v1/query/stream"), {
    method: "POST",
    headers: withAuthHeaders({
      Accept: "text/event-stream",
      "Content-Type": "application/json",
    }),
    body: JSON.stringify({ ...payload, stream: true }),
    signal,
  });

  if (!response.ok) {
    handleAuthFailure(response, sentToken);
    const detail = await response.text();
    throw new Error(detail || `Stream request failed: ${response.status}`);
  }

  if (!response.body) {
    throw new Error("Stream response body is empty");
  }

  let streamError: Error | null = null;
  const { receivedDone } = await readSseStream(
    response.body,
    (message) => {
      if (message.event === "reasoning") {
        const payload = JSON.parse(message.data) as StreamReasoningPayload;
        handlers.onReasoning(payload.text ?? "");
        return;
      }

      if (message.event === "chunk") {
        const payload = JSON.parse(message.data) as { text?: string };
        handlers.onChunk(payload.text ?? "");
        return;
      }

      if (message.event === "progress") {
        handlers.onProgress?.(JSON.parse(message.data) as QueryProgressEvent);
        return;
      }

      if (message.event === "commentary") {
        const payload = JSON.parse(message.data) as StreamCommentaryPayload;
        handlers.onCommentary?.(payload.text ?? "");
        return;
      }

      if (message.event === "tool_progress") {
        handlers.onToolProgress?.(
          JSON.parse(message.data) as ToolProgressEvent,
        );
        return;
      }

      if (message.event === "done") {
        handlers.onDone(JSON.parse(message.data) as StreamDonePayload);
        return;
      }

      if (message.event === "error") {
        const payload = JSON.parse(message.data) as StreamErrorPayload;
        streamError = new Error(payload.message || "LLM 服务暂时不可用");
      }
    },
    signal,
  );

  // 用户主动中断，静默返回
  if (signal?.aborted) {
    return;
  }

  if (streamError) {
    throw streamError;
  }

  if (!receivedDone) {
    throw new Error("流式回答被中断，请重试");
  }
}

export function matchSourceToDocumentId(
  sourceFile: string,
  documents: DemoDocumentInfo[],
): string | null {
  const target = normalize(sourceFile);
  const matched = documents.find((document) =>
    [document.id, document.name, document.title].some(
      (value) =>
        normalize(value).includes(target) || target.includes(normalize(value)),
    ),
  );

  return matched?.id ?? null;
}

// -- 文档导入 API --

export async function uploadDocument(
  file: File,
): Promise<DocumentUploadResponse> {
  const sentToken = getToken();
  const formData = new FormData();
  formData.append("file", file);

  const response = await fetch(buildApiUrl("/api/v1/documents/upload"), {
    method: "POST",
    headers: withAuthHeaders(),
    body: formData,
  });

  if (!response.ok) {
    handleAuthFailure(response, sentToken);
    const detail = await response.text();
    throw new Error(detail || `Upload failed: ${response.status}`);
  }

  return (await response.json()) as DocumentUploadResponse;
}

export async function uploadDocumentToMinio(
  file: File,
  contextSummaryEnabled: boolean = true,
): Promise<DocumentUploadToMinioResponse> {
  const sentToken = getToken();
  const formData = new FormData();
  formData.append("file", file);
  formData.append("contextSummaryEnabled", String(contextSummaryEnabled));

  const response = await fetch(
    buildApiUrl("/api/v1/documents/upload-to-minio"),
    {
      method: "POST",
      headers: withAuthHeaders(),
      body: formData,
    },
  );

  if (!response.ok) {
    handleAuthFailure(response, sentToken);
    const detail = await response.text();
    throw new Error(detail || `Upload failed: ${response.status}`);
  }

  return (await response.json()) as DocumentUploadToMinioResponse;
}

export async function processDocument(docId: string): Promise<void> {
  const sentToken = getToken();
  const response = await fetch(
    buildApiUrl(`/api/v1/documents/${encodeURIComponent(docId)}/process`),
    {
      method: "POST",
      headers: withAuthHeaders({ "Content-Type": "application/json" }),
    },
  );
  if (!response.ok) {
    handleAuthFailure(response, sentToken);
    const detail = await response.text();
    throw new Error(detail || `Process trigger failed: ${response.status}`);
  }
}

export async function deleteDocument(docId: string): Promise<void> {
  const sentToken = getToken();
  const response = await fetch(
    buildApiUrl(`/api/v1/documents/${encodeURIComponent(docId)}`),
    { method: "DELETE", headers: withAuthHeaders() },
  );
  if (!response.ok) {
    handleAuthFailure(response, sentToken);
    const detail = await response.text();
    throw new Error(detail || `Delete failed: ${response.status}`);
  }
}

export function subscribeToPipelineStatus(
  docId: string,
  onProgress: (event: PipelineProgressEvent) => void,
  onDone: (event: PipelineProgressEvent) => void,
  onError: (error: string) => void,
): () => void {
  const url = appendTokenParam(
    buildApiUrl(`/api/v1/documents/${encodeURIComponent(docId)}/status`),
  );
  const source = new EventSource(url);

  source.addEventListener("progress", (e) => {
    try {
      const data = JSON.parse(
        (e as MessageEvent).data,
      ) as PipelineProgressEvent;
      onProgress(data);
    } catch {
      // 忽略解析失败
    }
  });

  source.addEventListener("done", (e) => {
    try {
      const data = JSON.parse(
        (e as MessageEvent).data,
      ) as PipelineProgressEvent;
      onDone(data);
    } catch {
      // 忽略解析失败
    }
    source.close();
  });

  source.onerror = () => {
    onError("Pipeline status connection lost");
    source.close();
  };

  return () => source.close();
}
