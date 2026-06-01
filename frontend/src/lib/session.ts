import type { ChatTurn, LlmSettings } from "./types";

export const DEMO_SESSION_STORAGE_KEY = "euro_qa_demo_session";

export type StorageLike = Pick<Storage, "getItem" | "setItem" | "removeItem">;

export type PersistedSessionRecord = {
  id: string;
  conversationId: string | null;
  activeReferenceId: string | null;
  draftQuestion: string;
  messages: ChatTurn[];
  updatedAt: string;
};

export type PersistedDemoSession = {
  currentSession: PersistedSessionRecord;
  history: PersistedSessionRecord[];
  sourceTranslationEnabled: boolean;
  llmSettings: LlmSettings | null;
};

export type PersistedDemoSessionPointer = {
  currentSession: Omit<PersistedSessionRecord, "messages">;
  sourceTranslationEnabled: boolean;
  llmSettings: LlmSettings | null;
};

export const INTERRUPTED_STREAM_MESSAGE =
  "上次回答在生成过程中中断，已保留已收到的内容。";

function getBrowserStorage(storage?: StorageLike): StorageLike | null {
  if (storage) {
    return storage;
  }

  if (typeof window === "undefined" || !window.localStorage) {
    return null;
  }

  return window.localStorage;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function asString(value: unknown, fallback = ""): string {
  return typeof value === "string" ? value : fallback;
}

function asNullableString(value: unknown): string | null {
  return typeof value === "string" ? value : null;
}

function normalizeMessage(value: unknown): ChatTurn | null {
  if (!isRecord(value)) {
    return null;
  }

  const message = value as ChatTurn;
  if (message.status !== "streaming") {
    return message;
  }

  return {
    ...message,
    status: "error",
    errorMessage: INTERRUPTED_STREAM_MESSAGE
  };
}

function asMessages(value: unknown): ChatTurn[] {
  if (!Array.isArray(value)) {
    return [];
  }

  return value
    .map(normalizeMessage)
    .filter((message): message is ChatTurn => message !== null);
}

function normalizeSessionRecord(
  value: unknown,
  fallbackId: string
): PersistedSessionRecord | null {
  if (!isRecord(value)) {
    return null;
  }

  return {
    id: asString(value.id, fallbackId),
    conversationId: asNullableString(value.conversationId),
    activeReferenceId: asNullableString(value.activeReferenceId),
    draftQuestion: asString(value.draftQuestion),
    messages: asMessages(value.messages),
    updatedAt: asString(value.updatedAt, new Date().toISOString())
  };
}

function normalizeCurrentSession(value: unknown): PersistedSessionRecord | null {
  return normalizeSessionRecord(value, "current");
}

function normalizeHistory(value: unknown): PersistedSessionRecord[] {
  if (!Array.isArray(value)) {
    return [];
  }

  return value
    .map((entry, index) => normalizeSessionRecord(entry, `history-${index + 1}`))
    .filter((entry): entry is PersistedSessionRecord => entry !== null);
}

export function loadPersistedDemoSession(
  storage?: StorageLike
): PersistedDemoSession | null {
  const targetStorage = getBrowserStorage(storage);
  if (!targetStorage) {
    return null;
  }

  const raw = targetStorage.getItem(DEMO_SESSION_STORAGE_KEY);
  if (!raw) {
    return null;
  }

  try {
    const parsed = JSON.parse(raw) as unknown;
    if (!isRecord(parsed)) {
      return null;
    }

    const currentSession =
      normalizeCurrentSession(parsed.currentSession) ??
      normalizeSessionRecord(parsed, "current");

    if (!currentSession) {
      return null;
    }

    return {
      currentSession,
      history: normalizeHistory(parsed.history),
      sourceTranslationEnabled: Boolean(parsed.sourceTranslationEnabled),
      llmSettings: isRecord(parsed.llmSettings)
        ? (parsed.llmSettings as LlmSettings)
        : null
    };
  } catch {
    return null;
  }
}

export function savePersistedDemoSession(
  session: PersistedDemoSession,
  storage?: StorageLike
): boolean {
  const targetStorage = getBrowserStorage(storage);
  if (!targetStorage) {
    return false;
  }

  const payload: PersistedDemoSessionPointer = {
    currentSession: {
      id: session.currentSession.id,
      conversationId: session.currentSession.conversationId,
      activeReferenceId: session.currentSession.activeReferenceId,
      draftQuestion: session.currentSession.draftQuestion,
      updatedAt: session.currentSession.updatedAt
    },
    sourceTranslationEnabled: session.sourceTranslationEnabled,
    llmSettings: session.llmSettings
  };

  try {
    targetStorage.setItem(DEMO_SESSION_STORAGE_KEY, JSON.stringify(payload));
    return true;
  } catch {
    return false;
  }
}

export function clearPersistedDemoSession(storage?: StorageLike): void {
  const targetStorage = getBrowserStorage(storage);
  if (!targetStorage) {
    return;
  }

  targetStorage.removeItem(DEMO_SESSION_STORAGE_KEY);
}
