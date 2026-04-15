import type { ChatTurn, LlmSettings } from "./types";

export const DEMO_SESSION_STORAGE_KEY = "euro_qa_demo_session";

export type StorageLike = Pick<Storage, "getItem" | "setItem" | "removeItem">;

export type PersistedDemoSession = {
  conversationId: string | null;
  activeReferenceId: string | null;
  draftQuestion: string;
  messages: ChatTurn[];
  sourceTranslationEnabled: boolean;
  llmSettings: LlmSettings | null;
};

function getBrowserStorage(storage?: StorageLike): StorageLike | null {
  if (storage) {
    return storage;
  }

  if (typeof window === "undefined" || !window.localStorage) {
    return null;
  }

  return window.localStorage;
}

export function loadPersistedDemoSession(
  storage?: StorageLike
): PersistedDemoSession | null {
  void storage;
  return null;
}

export function savePersistedDemoSession(
  session: PersistedDemoSession,
  storage?: StorageLike
): void {
  void session;
  const targetStorage = getBrowserStorage(storage);
  if (!targetStorage) {
    return;
  }

  targetStorage.removeItem(DEMO_SESSION_STORAGE_KEY);
}

export function clearPersistedDemoSession(storage?: StorageLike): void {
  const targetStorage = getBrowserStorage(storage);
  if (!targetStorage) {
    return;
  }

  targetStorage.removeItem(DEMO_SESSION_STORAGE_KEY);
}
