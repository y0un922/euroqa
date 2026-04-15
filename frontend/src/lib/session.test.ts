import assert from "node:assert/strict";
import test from "node:test";

import {
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

test("loadPersistedDemoSession returns null for invalid JSON", () => {
  const storage = createMemoryStorage();
  storage.setItem("euro_qa_demo_session", "{oops");

  const restored = loadPersistedDemoSession(storage);

  assert.equal(restored, null);
});

test("loadPersistedDemoSession ignores previously persisted history", () => {
  const storage = createMemoryStorage();
  storage.setItem(
    "euro_qa_demo_session",
    JSON.stringify({
      conversationId: "conv-1",
      draftQuestion: "历史草稿",
      messages: [
        {
          id: "turn-1",
          question: "历史问题",
          answer: "历史回答",
          reasoning: "",
          status: "done",
          confidence: "medium",
          sources: [],
          relatedRefs: [],
          degraded: false
        }
      ]
    })
  );

  const restored = loadPersistedDemoSession(storage);

  assert.equal(restored, null);
});

test("savePersistedDemoSession clears any previously persisted history", () => {
  const storage = createMemoryStorage();
  storage.setItem(
    "euro_qa_demo_session",
    JSON.stringify({ draftQuestion: "历史草稿" })
  );

  savePersistedDemoSession(
    {
      conversationId: "conv-2",
      activeReferenceId: "ref-1",
      draftQuestion: "新草稿",
      messages: [],
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

  assert.equal(storage.getItem("euro_qa_demo_session"), null);
});
