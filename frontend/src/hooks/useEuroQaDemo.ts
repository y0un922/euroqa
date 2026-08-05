import {
  startTransition,
  useEffect,
  useMemo,
  useRef,
  useState,
  type Dispatch,
  type SetStateAction,
} from "react";

import {
  buildChatQueryPayload,
  buildDocumentFileUrl,
  buildReferenceRecords,
  deleteConversationSession,
  getConversationSession,
  getConversationSessions,
  getPreferredReferenceIndex,
  getLlmSettings,
  getSuggestions,
  listDocuments,
  listGlossary,
  query,
  queryStream,
  translateSource,
  type DemoDocumentInfo,
} from "../lib/api";
import {
  loadPersistedDemoSession,
  savePersistedDemoSession,
  type PersistedSessionRecord,
} from "../lib/session";
import type {
  ChatTurn,
  ConversationSessionResponse,
  ConversationSessionSummaryResponse,
  DocumentInfo,
  GlossaryEntry,
  LlmRequestOverride,
  LlmSettings,
  LlmSettingsResponse,
  QueryProgressEvent,
  ReferenceRecord,
} from "../lib/types";

type ApiState = "loading" | "ready" | "degraded";
type PdfLocationStatus = "idle" | "highlighted" | "page_only" | "error";
type HistorySessionSummary = {
  id: string;
  title: string;
  messageCount: number;
  updatedAt: string;
  lastUpdatedLabel: string;
};

const DEFAULT_BOOT_ERROR = "正在连接后端服务，请稍后重试。";
const FALLBACK_LLM_SETTINGS: LlmSettings = {
  apiKey: "",
  baseUrl: "https://api.deepseek.com/v1",
  model: "deepseek-chat",
  enableThinking: true,
};
const EXTERNAL_SESSION_USER_ID = "1001";
let fallbackIdCounter = 0;

function toEditableLlmSettings(
  defaults: LlmSettingsResponse | null,
): LlmSettings {
  return {
    apiKey: "",
    baseUrl: defaults?.base_url?.trim() || FALLBACK_LLM_SETTINGS.baseUrl,
    model: defaults?.model?.trim() || FALLBACK_LLM_SETTINGS.model,
    enableThinking:
      defaults?.enable_thinking ?? FALLBACK_LLM_SETTINGS.enableThinking,
  };
}

function normalizeLlmSettings(settings: LlmSettings): LlmSettings {
  return {
    apiKey: settings.apiKey.trim(),
    baseUrl: settings.baseUrl.trim(),
    model: settings.model.trim(),
    enableThinking: settings.enableThinking,
  };
}

function shouldClearLlmOverride(
  settings: LlmSettings,
  defaults: LlmSettings,
): boolean {
  return (
    settings.apiKey === "" &&
    settings.baseUrl === defaults.baseUrl &&
    settings.model === defaults.model &&
    settings.enableThinking === defaults.enableThinking
  );
}

function toLlmRequestOverride(
  settings: LlmSettings | null,
): LlmRequestOverride | undefined {
  if (!settings) {
    return undefined;
  }

  return {
    ...(settings.apiKey ? { api_key: settings.apiKey } : {}),
    ...(settings.baseUrl ? { base_url: settings.baseUrl } : {}),
    ...(settings.model ? { model: settings.model } : {}),
    enable_thinking: settings.enableThinking,
  };
}

function createUuidToken(): string {
  if (
    typeof crypto !== "undefined" &&
    typeof crypto.randomUUID === "function"
  ) {
    return crypto.randomUUID().replace(/-/g, "");
  }

  fallbackIdCounter = (fallbackIdCounter + 1) % 1000000;
  return `${Date.now()}${fallbackIdCounter}${Math.random()
    .toString(36)
    .slice(2, 14)}`.replace(/[^A-Za-z0-9]/g, "");
}

function createSessionId(): string {
  return `${EXTERNAL_SESSION_USER_ID}_${createUuidToken()}`;
}

function getSessionUserId(sessionId: string): string {
  const [userId] = sessionId.split("_");
  return userId || EXTERNAL_SESSION_USER_ID;
}

function createTurnId(): string {
  return `turn_${createUuidToken()}`;
}

function createEmptySessionRecord(): PersistedSessionRecord {
  return {
    id: createSessionId(),
    conversationId: null,
    activeReferenceId: null,
    draftQuestion: "",
    messages: [],
    updatedAt: new Date().toISOString(),
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
        minute: "2-digit",
      })
    : timestamp.toLocaleDateString("zh-CN", {
        month: "2-digit",
        day: "2-digit",
      });
}

function buildHistorySessionSummary(
  session: PersistedSessionRecord,
): HistorySessionSummary {
  const title =
    session.messages[0]?.question?.trim() ||
    session.draftQuestion.trim() ||
    "未命名会话";

  return {
    id: session.id,
    title,
    messageCount: session.messages.length,
    updatedAt: session.updatedAt,
    lastUpdatedLabel: formatUpdatedAt(session.updatedAt),
  };
}

function buildHistorySessionSummaryFromResponse(
  session: ConversationSessionSummaryResponse,
): HistorySessionSummary {
  const updatedAt = session.updatedAt || new Date().toISOString();
  return {
    id: session.sessionId,
    title: session.title?.trim() || "未命名会话",
    messageCount: session.messageCount,
    updatedAt,
    lastUpdatedLabel: formatUpdatedAt(updatedAt),
  };
}

function buildSessionRecordFromResponse(
  session: ConversationSessionResponse,
): PersistedSessionRecord {
  return {
    id: session.sessionId,
    conversationId: session.conversationId,
    activeReferenceId: null,
    draftQuestion: "",
    messages: session.messages,
    updatedAt: session.updatedAt || new Date().toISOString(),
  };
}

function sortHistorySummaries(
  sessions: HistorySessionSummary[],
): HistorySessionSummary[] {
  return [...sessions].sort((left, right) =>
    right.updatedAt.localeCompare(left.updatedAt),
  );
}

function upsertHistorySummary(
  sessions: HistorySessionSummary[],
  nextSession: HistorySessionSummary,
): HistorySessionSummary[] {
  return sortHistorySummaries([
    nextSession,
    ...sessions.filter((session) => session.id !== nextSession.id),
  ]);
}

function upsertProgressEvent(
  events: QueryProgressEvent[] | undefined,
  nextEvent: QueryProgressEvent,
): QueryProgressEvent[] {
  const current = events ?? [];
  const index = current.findIndex((event) => event.stage === nextEvent.stage);
  if (index === -1) {
    return [...current, nextEvent];
  }

  return current.map((event, eventIndex) =>
    eventIndex === index ? nextEvent : event,
  );
}

function upsertToolSubStep(
  steps: ChatTurn["toolSubSteps"] | undefined,
  nextStep: NonNullable<ChatTurn["toolSubSteps"]>[number],
): NonNullable<ChatTurn["toolSubSteps"]> {
  const current = steps ?? [];
  const index = current.findIndex((step) => step.step_id === nextStep.step_id);
  if (index === -1) {
    return [...current, nextStep];
  }

  return current.map((step, stepIndex) =>
    stepIndex === index ? nextStep : step,
  );
}

export function useEuroQaDemo() {
  const restoredSession = useMemo(() => loadPersistedDemoSession(), []);
  const initialSession = useMemo(
    () => restoredSession?.currentSession ?? createEmptySessionRecord(),
    [restoredSession],
  );
  const [apiState, setApiState] = useState<ApiState>("loading");
  const [bootError, setBootError] = useState<string | null>(null);
  const [documents, setDocuments] = useState<DocumentInfo[]>([]);
  const [glossary, setGlossary] = useState<GlossaryEntry[]>([]);
  const [hotQuestions, setHotQuestions] = useState<string[]>([]);
  const [selectedKbIds, setSelectedKbIds] = useState<string[]>([]);
  const [activeSessionId, setActiveSessionId] = useState(initialSession.id);
  const [draftQuestion, setDraftQuestion] = useState(
    initialSession.draftQuestion,
  );
  const [messages, setMessages] = useState<ChatTurn[]>([]);
  const [historySessions, setHistorySessions] = useState<
    HistorySessionSummary[]
  >([]);
  const [sourceTranslationEnabled, setSourceTranslationEnabled] = useState(
    restoredSession?.sourceTranslationEnabled ?? false,
  );
  const [llmSettings, setLlmSettings] = useState<LlmSettings | null>(
    restoredSession?.llmSettings ?? null,
  );
  const [llmSettingsDefaults, setLlmSettingsDefaults] =
    useState<LlmSettingsResponse | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [conversationId, setConversationId] = useState<string | null>(
    initialSession.conversationId,
  );
  const [activeReferenceId, setActiveReferenceId] = useState<string | null>(
    initialSession.activeReferenceId,
  );
  const [pdfLocationStatus, setPdfLocationStatus] =
    useState<PdfLocationStatus>("idle");
  const [sourceTranslationCache, setSourceTranslationCache] = useState<
    Record<string, string>
  >({});
  const [sourceTranslationLoadingKey, setSourceTranslationLoadingKey] =
    useState<string | null>(null);
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

      const [
        documentsResult,
        glossaryResult,
        suggestResult,
        llmSettingsResult,
        sessionsResult,
      ] = await Promise.allSettled([
        listDocuments(),
        listGlossary(),
        getSuggestions(),
        getLlmSettings(),
        getConversationSessions(getSessionUserId(activeSessionId)),
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
        llmSettingsResult.status === "fulfilled"
          ? llmSettingsResult.value
          : null;
      const nextHistorySessions =
        sessionsResult.status === "fulfilled"
          ? sessionsResult.value.sessions.map(buildHistorySessionSummaryFromResponse)
          : [];
      const restoredConversationResult = await getConversationSession(
        activeSessionId,
      )
        .then((session) => ({ status: "fulfilled" as const, value: session }))
        .catch((reason) => ({ status: "rejected" as const, reason }));

      if (cancelled) {
        return;
      }

      startTransition(() => {
        setDocuments(nextDocuments);
        setGlossary(nextGlossary);
        setHotQuestions(nextHotQuestions);
        setLlmSettingsDefaults(nextLlmSettingsDefaults);
        setHistorySessions(nextHistorySessions);
        if (restoredConversationResult.status === "fulfilled") {
          setConversationId(restoredConversationResult.value.conversationId);
          setMessages(restoredConversationResult.value.messages);
        }
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
          firstReason instanceof Error
            ? firstReason.message
            : DEFAULT_BOOT_ERROR,
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
      updatedAt: new Date().toISOString(),
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
      history: [],
      sourceTranslationEnabled,
      llmSettings,
    });
  }, [
    activeSessionId,
    activeReferenceId,
    conversationId,
    draftQuestion,
    llmSettings,
    sourceTranslationEnabled,
  ]);

  const llmDefaultSettings = useMemo(
    () => toEditableLlmSettings(llmSettingsDefaults),
    [llmSettingsDefaults],
  );

  const references = useMemo(() => {
    return messages.flatMap((message) =>
      buildReferenceRecords(
        message.sources,
        documents as DemoDocumentInfo[],
        message.confidence,
        message.relatedRefs,
        message.id,
      ),
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
          activeReferenceLocatorText,
        ].join("|")
      : null;

  useEffect(() => {
    setPdfLocationStatus("idle");
  }, [activeReferenceId]);

  useEffect(() => {
    if (
      !sourceTranslationEnabled ||
      !activeReference ||
      !activeSourceTranslationCacheKey
    ) {
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
        current === activeSourceTranslationCacheKey ? null : current,
      );
      return;
    }

    const existingTranslation =
      activeReference.source.translation?.trim() || "";
    if (existingTranslation) {
      setSourceTranslationCache((current) => ({
        ...current,
        [activeSourceTranslationCacheKey]: existingTranslation,
      }));
      setSourceTranslationErrors((current) => ({
        ...current,
        [activeSourceTranslationCacheKey]: null,
      }));
      setSourceTranslationLoadingKey((current) =>
        current === activeSourceTranslationCacheKey ? null : current,
      );
      return;
    }

    const requestId = sourceTranslationRequestIdRef.current + 1;
    sourceTranslationRequestIdRef.current = requestId;
    setSourceTranslationLoadingKey(activeSourceTranslationCacheKey);
    setSourceTranslationErrors((current) => ({
      ...current,
      [activeSourceTranslationCacheKey]: null,
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
      locator_text: activeReferenceLocatorText,
    })
      .then((response) => {
        if (cancelled || sourceTranslationRequestIdRef.current !== requestId) {
          return;
        }

        const translated = response.translation?.trim() || "";
        setSourceTranslationCache((current) => ({
          ...current,
          [activeSourceTranslationCacheKey]: translated,
        }));
        setSourceTranslationErrors((current) => ({
          ...current,
          [activeSourceTranslationCacheKey]: null,
        }));
        setSourceTranslationLoadingKey((current) =>
          current === activeSourceTranslationCacheKey ? null : current,
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
          [activeSourceTranslationCacheKey]: reason,
        }));
        setSourceTranslationLoadingKey((current) =>
          current === activeSourceTranslationCacheKey ? null : current,
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
    sourceTranslationEnabled,
  ]);

  const activeSourceTranslation = useMemo(() => {
    if (
      !sourceTranslationEnabled ||
      !activeReference ||
      !activeSourceTranslationCacheKey
    ) {
      return null;
    }
    const cached =
      sourceTranslationCache[activeSourceTranslationCacheKey]?.trim();
    if (cached) {
      return cached;
    }
    const existing = activeReference.source.translation?.trim();
    return existing || null;
  }, [
    activeReference,
    activeSourceTranslationCacheKey,
    sourceTranslationCache,
    sourceTranslationEnabled,
  ]);

  const sourceTranslationLoading = Boolean(
    sourceTranslationEnabled &&
    activeSourceTranslationCacheKey &&
    sourceTranslationLoadingKey === activeSourceTranslationCacheKey,
  );
  const sourceTranslationError =
    sourceTranslationEnabled && activeSourceTranslationCacheKey
      ? (sourceTranslationErrors[activeSourceTranslationCacheKey] ?? null)
      : null;

  /**
   * 流式回答的核心逻辑，askQuestion 和 regenerateAnswer 共用。
   * abort 后静默返回，不抛错。
   */
  async function runStreamingTurn(
    turnId: string,
    normalizedQuestion: string,
    sessionId: string,
    signal: AbortSignal,
  ) {
    // /query/stream requires a retrieval scope (docIds or kbIds). When the
    // demo has no KB selected, pin the scope to currently loaded documents
    // so streaming + agent progress stay on the SSE path instead of falling
    // back to non-streaming /query.
    const scopedDocIds =
      selectedKbIds.length > 0
        ? undefined
        : documents
            .map((document) => document.id)
            .filter((docId) => docId.trim().length > 0)
            .slice(0, 100);
    const requestPayload = buildChatQueryPayload({
      question: normalizedQuestion,
      docIds: scopedDocIds,
      kbIds: selectedKbIds,
      sessionId,
      llm: toLlmRequestOverride(llmSettings),
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
                  : message,
              ),
            );
          },
          onChunk: (text) => {
            setMessages((current) =>
              current.map((message) =>
                message.id === turnId
                  ? { ...message, answer: `${message.answer}${text}` }
                  : message,
              ),
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
                        payload,
                      ),
                    }
                  : message,
              ),
            );
          },
          onCommentary: (text) => {
            if (!text) {
              return;
            }
            setMessages((current) =>
              current.map((message) =>
                message.id === turnId
                  ? {
                      ...message,
                      commentaries: [...(message.commentaries ?? []), text],
                    }
                  : message,
              ),
            );
          },
          onToolProgress: (payload) => {
            setMessages((current) =>
              current.map((message) =>
                message.id === turnId
                  ? {
                      ...message,
                      toolSubSteps: upsertToolSubStep(message.toolSubSteps, {
                        ...payload.step,
                        tool_name: payload.tool_name,
                      }),
                    }
                  : message,
              ),
            );
          },
          onDone: (payload) => {
            const usage = payload.usage ?? null;
            const elapsedMs = payload.elapsed_ms ?? null;
            setMessages((current) =>
              current.map((message) =>
                message.id === turnId
                  ? {
                      ...message,
                      ...(payload.normalized_answer
                        ? { answer: payload.normalized_answer }
                        : {}),
                      confidence: payload.confidence,
                      relatedRefs: payload.related_refs ?? [],
                      retrievalContext: payload.retrieval_context ?? null,
                      sources: payload.sources ?? [],
                      questionType: payload.question_type ?? null,
                      engineeringContext: payload.engineering_context ?? null,
                      usage,
                      elapsed_ms: elapsedMs,
                      status: "done",
                      errorMessage: undefined,
                    }
                  : message,
              ),
            );
            if ((payload.sources ?? []).length > 0) {
              const preferredIndex = getPreferredReferenceIndex(
                payload.sources ?? [],
              );
              setActiveReferenceId(`${turnId}-ref-${preferredIndex + 1}`);
            }
          },
        },
        signal,
      );

      // 用户主动中断：保留已生成内容，标记为 done
      if (signal.aborted) {
        setMessages((current) =>
          current.map((message) =>
            message.id === turnId
              ? { ...message, status: "done", errorMessage: undefined }
              : message,
          ),
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
              : message,
          ),
        );
        return;
      }

      // 流式失败，尝试非流式 fallback
      try {
        const response = await query(requestPayload);
        setConversationId(response.conversation_id || sessionId);
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
                  usage: response.usage ?? null,
                  elapsed_ms: response.elapsed_ms ?? null,
                  status: "done",
                  errorMessage: undefined,
                  conversationId: response.conversation_id || sessionId,
                }
              : message,
          ),
        );
        if ((response.sources ?? []).length > 0) {
          const preferredIndex = getPreferredReferenceIndex(
            response.sources ?? [],
          );
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
                  usage: null,
                  elapsed_ms: null,
                  errorMessage: reason,
                }
              : message,
          ),
        );
      }
    }
  }

  async function askQuestion(question: string) {
    const normalizedQuestion = question.trim();
    if (!normalizedQuestion || isSubmitting) {
      return;
    }

    const nextSessionId =
      conversationId && conversationId.trim().length > 0
        ? conversationId
        : activeSessionId;
    const turnId = createTurnId();

    setConversationId(nextSessionId);
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
        conversationId: nextSessionId,
        retrievalContext: null,
        usage: null,
        elapsed_ms: null,
        progressEvents: [],
        commentaries: [],
        toolSubSteps: [],
      },
    ]);

    const abortController = new AbortController();
    streamAbortControllerRef.current = abortController;

    try {
      await runStreamingTurn(
        turnId,
        normalizedQuestion,
        nextSessionId,
        abortController.signal,
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

    const nextSessionId =
      conversationId && conversationId.trim().length > 0
        ? conversationId
        : activeSessionId;

    setConversationId(nextSessionId);
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
              usage: null,
              elapsed_ms: null,
              conversationId: nextSessionId,
              progressEvents: [],
              commentaries: [],
              toolSubSteps: [],
            }
          : message,
      ),
    );

    const abortController = new AbortController();
    streamAbortControllerRef.current = abortController;

    try {
      await runStreamingTurn(
        messageId,
        targetMessage.question,
        nextSessionId,
        abortController.signal,
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
    setHistorySessions((current) =>
      isMeaningfulSession(currentSession)
        ? upsertHistorySummary(current, buildHistorySessionSummary(currentSession))
        : current,
    );
    restoreSession(createEmptySessionRecord());
  }

  async function selectHistorySession(sessionId: string) {
    if (isSubmitting || sessionId === activeSessionId) {
      return;
    }

    const currentSession = buildCurrentSessionSnapshot();
    let targetSession: ConversationSessionResponse;
    try {
      targetSession = await getConversationSession(sessionId);
    } catch {
      return;
    }
    setHistorySessions((current) =>
      isMeaningfulSession(currentSession)
        ? upsertHistorySummary(current, buildHistorySessionSummary(currentSession))
        : current,
    );
    restoreSession(buildSessionRecordFromResponse(targetSession));
  }

  async function deleteHistorySession(sessionId: string) {
    if (isSubmitting || sessionId === activeSessionId) {
      return;
    }

    setHistorySessions((current) =>
      current.filter((session) => session.id !== sessionId),
    );
    try {
      await deleteConversationSession(sessionId);
    } catch {
      try {
        const refreshed = await getConversationSessions(getSessionUserId(sessionId));
        setHistorySessions(
          refreshed.sessions.map(buildHistorySessionSummaryFromResponse),
        );
      } catch {
        // 保持乐观删除结果，避免短暂后端错误让 UI 反复闪回。
      }
    }
  }

  function saveLlmSettings(nextSettings: LlmSettings) {
    const normalized = normalizeLlmSettings(nextSettings);
    setLlmSettings(
      shouldClearLlmOverride(normalized, llmDefaultSettings)
        ? null
        : normalized,
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
    deleteHistorySession,
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
    selectedKbIds,
    setActiveReferenceId,
    setDraftQuestion: setDraftQuestion as Dispatch<SetStateAction<string>>,
    setSelectedKbIds: setSelectedKbIds as Dispatch<SetStateAction<string[]>>,
    refreshDocuments,
    stopStreaming,
    submitDraftQuestion,
  };
}
