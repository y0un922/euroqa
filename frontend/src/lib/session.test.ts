import assert from "node:assert/strict";
import test from "node:test";

import {
  clearPersistedDemoSession,
  loadPersistedDemoSession,
  savePersistedDemoSession
} from "./session.ts";

function createMemoryStorage() {
  const store = new Map<string, string>();
  return {
    getItem(key: string) {
      return store.get(key) ?? null;
    },
    setItem(key: string, value: string) {
      store.set(key, value);
    },
    removeItem(key: string) {
      store.delete(key);
    }
  };
}

function createTurn(id: string, question: string) {
  return {
    id,
    question,
    answer: `${question} 的回答`,
    reasoning: "",
    status: "done" as const,
    confidence: "medium" as const,
    sources: [],
    relatedRefs: [],
    degraded: false,
    retrievalContext: null
  };
}

test("loadPersistedDemoSession returns null for invalid JSON", () => {
  const storage = createMemoryStorage();
  storage.setItem("euro_qa_demo_session", "{oops");

  const restored = loadPersistedDemoSession(storage);

  assert.equal(restored, null);
});

test("savePersistedDemoSession persists current session with history", () => {
  const storage = createMemoryStorage();

  savePersistedDemoSession(
    {
      currentSession: {
        id: "current",
        conversationId: "conv-current",
        activeReferenceId: "ref-current",
        draftQuestion: "当前草稿",
        messages: [createTurn("turn-current", "当前问题")],
        updatedAt: "2026-04-19T12:20:00.000Z"
      },
      history: [
        {
          id: "archived-1",
          conversationId: "conv-archived-1",
          activeReferenceId: null,
          draftQuestion: "",
          messages: [createTurn("turn-1", "历史问题 1")],
          updatedAt: "2026-04-19T10:00:00.000Z"
        },
        {
          id: "archived-2",
          conversationId: "conv-archived-2",
          activeReferenceId: "ref-archived-2",
          draftQuestion: "历史草稿",
          messages: [createTurn("turn-2", "历史问题 2")],
          updatedAt: "2026-04-18T09:00:00.000Z"
        }
      ],
      sourceTranslationEnabled: true,
      llmSettings: {
        apiKey: "override-key",
        baseUrl: "https://dashscope.aliyuncs.com/compatible-mode/v1",
        model: "qwen3.5-plus",
        enableThinking: true
      }
    },
    storage
  );

  const restored = loadPersistedDemoSession(storage);

  assert.ok(restored);
  assert.equal(restored.currentSession.id, "current");
  assert.equal(restored.currentSession.messages[0]?.question, "当前问题");
  assert.equal(restored.history.length, 2);
  assert.equal(restored.history[0]?.messages[0]?.question, "历史问题 1");
  assert.equal(restored.history[1]?.activeReferenceId, "ref-archived-2");
  assert.equal(restored.sourceTranslationEnabled, true);
  assert.equal(restored.llmSettings?.model, "qwen3.5-plus");
});

test("loadPersistedDemoSession tolerates legacy payload by restoring a current session", () => {
  const storage = createMemoryStorage();
  storage.setItem(
    "euro_qa_demo_session",
    JSON.stringify({
      conversationId: "legacy-conv",
      activeReferenceId: "legacy-ref",
      draftQuestion: "旧草稿",
      messages: [createTurn("legacy-turn", "旧问题")],
      sourceTranslationEnabled: false,
      llmSettings: null
    })
  );

  const restored = loadPersistedDemoSession(storage);

  assert.ok(restored);
  assert.equal(restored.currentSession.conversationId, "legacy-conv");
  assert.equal(restored.currentSession.messages[0]?.question, "旧问题");
  assert.equal(restored.history.length, 0);
});

test("clearPersistedDemoSession removes persisted payload", () => {
  const storage = createMemoryStorage();

  savePersistedDemoSession(
    {
      currentSession: {
        id: "current",
        conversationId: null,
        activeReferenceId: null,
        draftQuestion: "",
        messages: [],
        updatedAt: "2026-04-19T12:20:00.000Z"
      },
      history: [],
      sourceTranslationEnabled: false,
      llmSettings: null
    },
    storage
  );

  clearPersistedDemoSession(storage);

  assert.equal(storage.getItem("euro_qa_demo_session"), null);
});
