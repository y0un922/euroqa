import {
  startTransition,
  useEffect,
  useMemo,
  useRef,
  useState,
  type Dispatch,
  type SetStateAction
} from "react";

import {
  buildChatQueryPayload,
  buildDocumentFileUrl,
  buildReferenceRecords,
  getPreferredReferenceIndex,
  getLlmSettings,
  getSuggestions,
  listDocuments,
  listGlossary,
  query,
  queryStream,
  translateSource,
  type DemoDocumentInfo
} from "../lib/api";
import {
  loadPersistedDemoSession,
  savePersistedDemoSession,
  type PersistedSessionRecord
} from "../lib/session";
import type {
  ChatTurn,
  DocumentInfo,
  GlossaryEntry,
  LlmRequestOverride,
  LlmSettings,
  LlmSettingsResponse,
  QueryProgressEvent,
  ReferenceRecord
} from "../lib/types";

type ApiState = "loading" | "ready" | "degraded";
type PdfLocationStatus = "idle" | "highlighted" | "page_only" | "error";
type HistorySessionSummary = {
  id: string;
  title: string;
  messageCount: number;
  lastUpdatedLabel: string;
};

const DEFAULT_BOOT_ERROR = "正在连接后端服务，请稍后重试。";
const FALLBACK_LLM_SETTINGS: LlmSettings = {
  apiKey: "",
  baseUrl: "https://api.deepseek.com/v1",
  model: "deepseek-chat",
  enableThinking: true
};
let fallbackIdCounter = 0;

function toEditableLlmSettings(
  defaults: LlmSettingsResponse | null
): LlmSettings {
  return {
    apiKey: "",
    baseUrl: defaults?.base_url?.trim() || FALLBACK_LLM_SETTINGS.baseUrl,
    model: defaults?.model?.trim() || FALLBACK_LLM_SETTINGS.model,
    enableThinking: defaults?.enable_thinking ?? FALLBACK_LLM_SETTINGS.enableThinking
  };
}

function normalizeLlmSettings(settings: LlmSettings): LlmSettings {
  return {
    apiKey: settings.apiKey.trim(),
    baseUrl: settings.baseUrl.trim(),
    model: settings.model.trim(),
    enableThinking: settings.enableThinking
  };
}

function shouldClearLlmOverride(
  settings: LlmSettings,
  defaults: LlmSettings
): boolean {
  return (
    settings.apiKey === "" &&
    settings.baseUrl === defaults.baseUrl &&
    settings.model === defaults.model &&
    settings.enableThinking === defaults.enableThinking
  );
}

function toLlmRequestOverride(
  settings: LlmSettings | null
): LlmRequestOverride | undefined {
  if (!settings) {
    return undefined;
  }

  return {
    ...(settings.apiKey ? { api_key: settings.apiKey } : {}),
    ...(settings.baseUrl ? { base_url: settings.baseUrl } : {}),
    ...(settings.model ? { model: settings.model } : {}),
    enable_thinking: settings.enableThinking
  };
}

function createSessionId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }

  fallbackIdCounter = (fallbackIdCounter + 1) % 1000000;
  return `session-${Date.now()}-${fallbackIdCounter}-${Math.random()
    .toString(36)
    .slice(2, 10)}`;
}

function createEmptySessionRecord(): PersistedSessionRecord {
  return {
    id: createSessionId(),
    conversationId: null,
    activeReferenceId: null,
    draftQuestion: "",
    messages: [],
    updatedAt: new Date().toISOString()
  };
}

function isMeaningfulSession(session: PersistedSessionRecord): boolean {
  return session.messages.length > 0 || session.draftQuestion.trim().length > 0;
}

function formatUpdatedAt(value: string): string {
  const timestamp = new Date(value);
  if (Number.isNaN(timestamp.getTime())) {
    return "刚刚";
  }

  const now = new Date();
  const isSameDay = timestamp.toDateString() === now.toDateString();
  return isSameDay
    ? timestamp.toLocaleTimeString("zh-CN", {
        hour: "2-digit",
        minute: "2-digit"
      })
    : timestamp.toLocaleDateString("zh-CN", {
        month: "2-digit",
        day: "2-digit"
      });
}

function buildHistorySessionSummary(
  session: PersistedSessionRecord
): HistorySessionSummary {
  const title =
    session.messages[0]?.question?.trim() ||
    session.draftQuestion.trim() ||
    "未命名会话";

  return {
    id: session.id,
    title,
    messageCount: session.messages.length,
    lastUpdatedLabel: formatUpdatedAt(session.updatedAt)
  };
}

function upsertProgressEvent(
  events: QueryProgressEvent[] | undefined,
  nextEvent: QueryProgressEvent
): QueryProgressEvent[] {
  const current = events ?? [];
  const index = current.findIndex((event) => event.stage === nextEvent.stage);
  if (index === -1) {
    return [...current, nextEvent];
  }

  return current.map((event, eventIndex) =>
    eventIndex === index ? nextEvent : event
  );
}

export function useEuroQaDemo() {
  const restoredSession = useMemo(() => loadPersistedDemoSession(), []);
  const initialSession = useMemo(
    () => restoredSession?.currentSession ?? createEmptySessionRecord(),
    [restoredSession]
  );
  const [apiState, setApiState] = useState<ApiState>("loading");
  const [bootError, setBootError] = useState<string | null>(null);
  const [documents, setDocuments] = useState<DocumentInfo[]>([]);
  const [glossary, setGlossary] = useState<GlossaryEntry[]>([]);
  const [hotQuestions, setHotQuestions] = useState<string[]>([]);
  const [activeSessionId, setActiveSessionId] = useState(initialSession.id);
  const [draftQuestion, setDraftQuestion] = useState(initialSession.draftQuestion);
  const [messages, setMessages] = useState<ChatTurn[]>(initialSession.messages);
  const [history, setHistory] = useState<PersistedSessionRecord[]>(
    restoredSession?.history ?? []
  );
  const [sourceTranslationEnabled, setSourceTranslationEnabled] = useState(
    restoredSession?.sourceTranslationEnabled ?? false
  );
  const [llmSettings, setLlmSettings] = useState<LlmSettings | null>(
    restoredSession?.llmSettings ?? null
  );
  const [llmSettingsDefaults, setLlmSettingsDefaults] =
    useState<LlmSettingsResponse | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [conversationId, setConversationId] = useState<string | null>(
    initialSession.conversationId
  );
  const [activeReferenceId, setActiveReferenceId] = useState<string | null>(
    initialSession.activeReferenceId
  );
  const [pdfLocationStatus, setPdfLocationStatus] =
    useState<PdfLocationStatus>("idle");
  const [sourceTranslationCache, setSourceTranslationCache] = useState<
    Record<string, string>
  >({});
  const [sourceTranslationLoadingKey, setSourceTranslationLoadingKey] = useState<
    string | null
  >(null);
  const [sourceTranslationErrors, setSourceTranslationErrors] = useState<
    Record<string, string | null>
  >({});
  const sourceTranslationRequestIdRef = useRef(0);
  const streamAbortControllerRef = useRef<AbortController | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setApiState("loading");
      setBootError(null);

      const [documentsResult, glossaryResult, suggestResult, llmSettingsResult] =
        await Promise.allSettled([
          listDocuments(),
          listGlossary(),
          getSuggestions(),
          getLlmSettings()
        ]);

      if (cancelled) {
        return;
      }

      const nextDocuments =
        documentsResult.status === "fulfilled" ? documentsResult.value : [];
      const nextGlossary =
        glossaryResult.status === "fulfilled" ? glossaryResult.value : [];
      const nextHotQuestions =
        suggestResult.status === "fulfilled"
          ? suggestResult.value.hot_questions
          : [];
      const nextLlmSettingsDefaults =
        llmSettingsResult.status === "fulfilled" ? llmSettingsResult.value : null;

      startTransition(() => {
        setDocuments(nextDocuments);
        setGlossary(nextGlossary);
        setHotQuestions(nextHotQuestions);
        setLlmSettingsDefaults(nextLlmSettingsDefaults);
      });

      const failed =
        documentsResult.status === "rejected" ||
        glossaryResult.status === "rejected" ||
        suggestResult.status === "rejected";

      if (failed) {
        setApiState(nextDocuments.length > 0 ? "degraded" : "degraded");
        const firstReason =
          (documentsResult.status === "rejected" && documentsResult.reason) ||
          (glossaryResult.status === "rejected" && glossaryResult.reason) ||
          (suggestResult.status === "rejected" && suggestResult.reason);
        setBootError(
          firstReason instanceof Error ? firstReason.message : DEFAULT_BOOT_ERROR
        );
        return;
      }

      setApiState("ready");
    }

    void load();
    return () => {
      cancelled = true;
    };
  }, []);

  function buildCurrentSessionSnapshot(): PersistedSessionRecord {
    return {
      id: activeSessionId,
      conversationId,
      activeReferenceId,
      draftQuestion,
      messages,
      updatedAt: new Date().toISOString()
    };
  }

  function restoreSession(session: PersistedSessionRecord) {
    setActiveSessionId(session.id);
    setConversationId(session.conversationId);
    setActiveReferenceId(session.activeReferenceId);
    setDraftQuestion(session.draftQuestion);
    setMessages(session.messages);
  }

  useEffect(() => {
    savePersistedDemoSession({
      currentSession: buildCurrentSessionSnapshot(),
      history,
      sourceTranslationEnabled,
      llmSettings
    });
  }, [
    activeSessionId,
    activeReferenceId,
    conversationId,
    draftQuestion,
    history,
    llmSettings,
    messages,
    sourceTranslationEnabled
  ]);

  const llmDefaultSettings = useMemo(
    () => toEditableLlmSettings(llmSettingsDefaults),
    [llmSettingsDefaults]
  );
  const historySessions = useMemo(
    () => history.map((session) => buildHistorySessionSummary(session)),
    [history]
  );

  const references = useMemo(() => {
    return messages.flatMap((message) =>
      buildReferenceRecords(
        message.sources,
        documents as DemoDocumentInfo[],
        message.confidence,
        message.relatedRefs,
        message.id
      )
    );
  }, [documents, messages]);

  const activeReference =
    references.find((reference) => reference.id === activeReferenceId) ?? null;

  const activeReferenceLocatorText =
    activeReference?.source.locator_text?.trim() ||
    activeReference?.source.original_text?.trim() ||
    "";
  const activeReferencePdfUrl = activeReference?.documentId
    ? buildDocumentFileUrl(activeReference.documentId)
    : null;
  const activeSourceTranslationCacheKey =
    activeReference?.documentId && activeReferenceLocatorText
      ? [
          activeReference.documentId,
          String(activeReference.source.page),
          activeReferenceLocatorText
        ].join("|")
      : null;

  useEffect(() => {
    setPdfLocationStatus("idle");
  }, [activeReferenceId]);

  useEffect(() => {
    if (!sourceTranslationEnabled || !activeReference || !activeSourceTranslationCacheKey) {
      setSourceTranslationLoadingKey(null);
      return;
    }

    if (!activeReference.documentId) {
      setSourceTranslationLoadingKey(null);
      return;
    }

    const cachedTranslation =
      sourceTranslationCache[activeSourceTranslationCacheKey]?.trim() || "";
    if (cachedTranslation) {
      setSourceTranslationErrors((current) => {
        if (!current[activeSourceTranslationCacheKey]) {
          return current;
        }
        return { ...current, [activeSourceTranslationCacheKey]: null };
      });
      setSourceTranslationLoadingKey((current) =>
        current === activeSourceTranslationCacheKey ? null : current
      );
      return;
    }

    const existingTranslation = activeReference.source.translation?.trim() || "";
    if (existingTranslation) {
      setSourceTranslationCache((current) => ({
        ...current,
        [activeSourceTranslationCacheKey]: existingTranslation
      }));
      setSourceTranslationErrors((current) => ({
        ...current,
        [activeSourceTranslationCacheKey]: null
      }));
      setSourceTranslationLoadingKey((current) =>
        current === activeSourceTranslationCacheKey ? null : current
      );
      return;
    }

    const requestId = sourceTranslationRequestIdRef.current + 1;
    sourceTranslationRequestIdRef.current = requestId;
    setSourceTranslationLoadingKey(activeSourceTranslationCacheKey);
    setSourceTranslationErrors((current) => ({
      ...current,
      [activeSourceTranslationCacheKey]: null
    }));

    let cancelled = false;
    void translateSource({
      document_id: activeReference.documentId,
      file: activeReference.source.file,
      title: activeReference.source.title,
      section: activeReference.source.section,
      page: activeReference.source.page,
      clause: activeReference.source.clause,
      original_text: activeReference.source.original_text,
      locator_text: activeReferenceLocatorText
    })
      .then((response) => {
        if (cancelled || sourceTranslationRequestIdRef.current !== requestId) {
          return;
        }

        const translated = response.translation?.trim() || "";
        setSourceTranslationCache((current) => ({
          ...current,
          [activeSourceTranslationCacheKey]: translated
        }));
        setSourceTranslationErrors((current) => ({
          ...current,
          [activeSourceTranslationCacheKey]: null
        }));
        setSourceTranslationLoadingKey((current) =>
          current === activeSourceTranslationCacheKey ? null : current
        );
      })
      .catch((error) => {
        if (cancelled || sourceTranslationRequestIdRef.current !== requestId) {
          return;
        }
        const reason =
          error instanceof Error ? error.message : "引用翻译请求失败";
        setSourceTranslationErrors((current) => ({
          ...current,
          [activeSourceTranslationCacheKey]: reason
        }));
        setSourceTranslationLoadingKey((current) =>
          current === activeSourceTranslationCacheKey ? null : current
        );
      });

    return () => {
      cancelled = true;
    };
  }, [
    activeReference,
    activeReferenceLocatorText,
    activeSourceTranslationCacheKey,
    sourceTranslationCache,
    sourceTranslationEnabled
  ]);

  const activeSourceTranslation = useMemo(() => {
    if (!sourceTranslationEnabled || !activeReference || !activeSourceTranslationCacheKey) {
      return null;
    }
    const cached = sourceTranslationCache[activeSourceTranslationCacheKey]?.trim();
    if (cached) {
      return cached;
    }
    const existing = activeReference.source.translation?.trim();
    return existing || null;
  }, [
    activeReference,
    activeSourceTranslationCacheKey,
    sourceTranslationCache,
    sourceTranslationEnabled
  ]);

  const sourceTranslationLoading = Boolean(
    sourceTranslationEnabled &&
      activeSourceTranslationCacheKey &&
      sourceTranslationLoadingKey === activeSourceTranslationCacheKey
  );
  const sourceTranslationError =
    sourceTranslationEnabled && activeSourceTranslationCacheKey
      ? sourceTranslationErrors[activeSourceTranslationCacheKey] ?? null
      : null;

  /**
   * 流式回答的核心逻辑，askQuestion 和 regenerateAnswer 共用。
   * abort 后静默返回，不抛错。
   */
  async function runStreamingTurn(
    turnId: string,
    normalizedQuestion: string,
    nextConversationId: string,
    signal: AbortSignal
  ) {
    const requestPayload = buildChatQueryPayload({
      question: normalizedQuestion,
      conversationId: nextConversationId,
      llm: toLlmRequestOverride(llmSettings)
    });

    try {
      await queryStream(
        requestPayload,
        {
          onReasoning: (text) => {
            setMessages((current) =>
              current.map((message) =>
                message.id === turnId
                  ? { ...message, reasoning: `${message.reasoning}${text}` }
                  : message
              )
            );
          },
          onChunk: (text) => {
            setMessages((current) =>
              current.map((message) =>
                message.id === turnId
                  ? { ...message, answer: `${message.answer}${text}` }
                  : message
              )
            );
          },
          onProgress: (payload) => {
            setMessages((current) =>
              current.map((message) =>
                message.id === turnId
                  ? {
                      ...message,
                      progressEvents: upsertProgressEvent(
                        message.progressEvents,
                        payload
                      )
                    }
                  : message
              )
            );
          },
          onDone: (payload) => {
            setMessages((current) =>
              current.map((message) =>
                message.id === turnId
                  ? {
                      ...message,
                      confidence: payload.confidence,
                      relatedRefs: payload.related_refs ?? [],
                      retrievalContext: payload.retrieval_context ?? null,
                      sources: payload.sources ?? [],
                      questionType: payload.question_type ?? null,
                      engineeringContext: payload.engineering_context ?? null,
                      status: "done",
                      errorMessage: undefined
                    }
                  : message
              )
            );
            if ((payload.sources ?? []).length > 0) {
              const preferredIndex = getPreferredReferenceIndex(payload.sources ?? []);
              setActiveReferenceId(`${turnId}-ref-${preferredIndex + 1}`);
            }
          }
        },
        signal
      );

      // 用户主动中断：保留已生成内容，标记为 done
      if (signal.aborted) {
        setMessages((current) =>
          current.map((message) =>
            message.id === turnId
              ? { ...message, status: "done", errorMessage: undefined }
              : message
          )
        );
        return;
      }
    } catch (error) {
      // 用户主动中断产生的 AbortError
      if (signal.aborted) {
        setMessages((current) =>
          current.map((message) =>
            message.id === turnId
              ? { ...message, status: "done", errorMessage: undefined }
              : message
          )
        );
        return;
      }

      // 流式失败，尝试非流式 fallback
      try {
        const response = await query(requestPayload);
        setConversationId(response.conversation_id || nextConversationId);
        setMessages((current) =>
          current.map((message) =>
            message.id === turnId
              ? {
                  ...message,
                  answer: response.answer,
                  reasoning: "",
                  confidence: response.confidence,
                  degraded: Boolean(response.degraded),
                  relatedRefs: response.related_refs ?? [],
                  retrievalContext: response.retrieval_context ?? null,
                  sources: response.sources ?? [],
                  questionType: response.question_type ?? null,
                  engineeringContext: response.engineering_context ?? null,
                  status: "done",
                  errorMessage: undefined,
                  conversationId: response.conversation_id || nextConversationId
                }
              : message
          )
        );
        if ((response.sources ?? []).length > 0) {
          const preferredIndex = getPreferredReferenceIndex(response.sources ?? []);
          setActiveReferenceId(`${turnId}-ref-${preferredIndex + 1}`);
        }
      } catch (fallbackError) {
        const reason =
          fallbackError instanceof Error
            ? fallbackError.message
            : error instanceof Error
              ? error.message
              : "请求失败";
        setMessages((current) =>
          current.map((message) =>
            message.id === turnId
              ? {
                  ...message,
                  answer: message.answer || "当前无法从后端获取回答。",
                  confidence: message.answer ? message.confidence : "low",
                  status: message.answer ? "done" : "error",
                  retrievalContext: null,
                  errorMessage: reason
                }
              : message
          )
        );
      }
    }
  }

  async function askQuestion(question: string) {
    const normalizedQuestion = question.trim();
    if (!normalizedQuestion || isSubmitting) {
      return;
    }

    const nextConversationId = createSessionId();
    const turnId = createSessionId();

    setConversationId(nextConversationId);
    setDraftQuestion("");
    setIsSubmitting(true);
    setActiveReferenceId(null);
    setMessages((current) => [
      ...current,
      {
        id: turnId,
        question: normalizedQuestion,
        answer: "",
        reasoning: "",
        confidence: "none",
        degraded: false,
        relatedRefs: [],
        sources: [],
        status: "streaming",
        conversationId: nextConversationId,
        retrievalContext: null,
        progressEvents: []
      }
    ]);

    const abortController = new AbortController();
    streamAbortControllerRef.current = abortController;

    try {
      await runStreamingTurn(
        turnId,
        normalizedQuestion,
        nextConversationId,
        abortController.signal
      );
    } finally {
      if (streamAbortControllerRef.current === abortController) {
        streamAbortControllerRef.current = null;
      }
      setIsSubmitting(false);
    }
  }

  function stopStreaming() {
    streamAbortControllerRef.current?.abort();
  }

  async function regenerateAnswer(messageId: string) {
    if (isSubmitting) {
      return;
    }

    const targetMessage = messages.find((message) => message.id === messageId);
    if (!targetMessage) {
      return;
    }

    const nextConversationId = createSessionId();

    setConversationId(nextConversationId);
    setIsSubmitting(true);
    setActiveReferenceId(null);
    setMessages((current) =>
      current.map((message) =>
        message.id === messageId
          ? {
              ...message,
              answer: "",
              reasoning: "",
              confidence: "none" as const,
              degraded: false,
              relatedRefs: [],
              sources: [],
              status: "streaming" as const,
              errorMessage: undefined,
              retrievalContext: null,
              conversationId: nextConversationId,
              progressEvents: []
            }
          : message
      )
    );

    const abortController = new AbortController();
    streamAbortControllerRef.current = abortController;

    try {
      await runStreamingTurn(
        messageId,
        targetMessage.question,
        nextConversationId,
        abortController.signal
      );
    } finally {
      if (streamAbortControllerRef.current === abortController) {
        streamAbortControllerRef.current = null;
      }
      setIsSubmitting(false);
    }
  }

  function submitDraftQuestion() {
    void askQuestion(draftQuestion);
  }

  function newSession() {
    if (isSubmitting) {
      return;
    }

    const currentSession = buildCurrentSessionSnapshot();
    setHistory((current) =>
      isMeaningfulSession(currentSession)
        ? [currentSession, ...current.filter((entry) => entry.id !== currentSession.id)]
        : current
    );
    restoreSession(createEmptySessionRecord());
  }

  function selectHistorySession(sessionId: string) {
    if (isSubmitting) {
      return;
    }

    const targetSession = history.find((session) => session.id === sessionId);
    if (!targetSession) {
      return;
    }

    const currentSession = buildCurrentSessionSnapshot();
    setHistory((current) => {
      const remaining = current.filter((entry) => entry.id !== sessionId);
      return isMeaningfulSession(currentSession)
        ? [currentSession, ...remaining]
        : remaining;
    });
    restoreSession(targetSession);
  }

  function saveLlmSettings(nextSettings: LlmSettings) {
    const normalized = normalizeLlmSettings(nextSettings);
    setLlmSettings(
      shouldClearLlmOverride(normalized, llmDefaultSettings) ? null : normalized
    );
  }

  function resetLlmSettings() {
    setLlmSettings(null);
  }

  async function refreshDocuments() {
    try {
      const docs = await listDocuments();
      setDocuments(docs);
    } catch {
      // 静默失败，保持当前列表
    }
  }

  return {
    activeReference,
    activeSessionId,
    activeReferenceId,
    apiState,
    askQuestion,
    bootError,
    conversationId,
    documents,
    draftQuestion,
    glossary,
    historySessions,
    hotQuestions,
    isSubmitting,
    messages,
    newSession,
    llmApiKeyConfigured: llmSettingsDefaults?.api_key_configured ?? false,
    llmDefaultSettings,
    llmSettings,
    regenerateAnswer,
    resetLlmSettings,
    saveLlmSettings,
    selectHistorySession,
    pdfLocationStatus,
    setPdfLocationStatus,
    activeReferencePdfUrl,
    activeReferenceLocatorText,
    activeSourceTranslation,
    sourceTranslationLoading,
    sourceTranslationError,
    setSourceTranslationEnabled,
    sourceTranslationEnabled,
    setActiveReferenceId,
    setDraftQuestion: setDraftQuestion as Dispatch<SetStateAction<string>>,
    refreshDocuments,
    stopStreaming,
    submitDraftQuestion
  };
}
