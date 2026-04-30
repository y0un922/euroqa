import test from "node:test";
import assert from "node:assert/strict";

import {
  buildChatQueryPayload,
  buildDocumentFileUrl,
  buildReferenceRecords,
  getPreferredReferenceIndex,
  getLlmSettings,
  matchSourceToDocumentId,
  parseSseBuffer,
  query,
  queryStream,
  readSseStream,
  translateSource
} from "./api.ts";

test("buildChatQueryPayload keeps cross-document retrieval enabled by omitting domain", () => {
  const payload = buildChatQueryPayload({
    question: "设计使用年限是多少？",
    conversationId: "conv-1",
    llm: {
      model: "qwen3.5-plus"
    }
  });

  assert.deepEqual(payload, {
    question: "设计使用年限是多少？",
    conversation_id: "conv-1",
    llm: {
      model: "qwen3.5-plus"
    }
  });
  assert.equal("domain" in payload, false);
});

test("parseSseBuffer parses complete SSE messages and clears buffer", () => {
  const input =
    'event: chunk\ndata: {"text":"桥"}\n\n' +
    'event: done\ndata: {"confidence":"low"}\n\n';

  const result = parseSseBuffer(input);

  assert.deepEqual(result.events, [
    { event: "chunk", data: '{"text":"桥"}' },
    { event: "done", data: '{"confidence":"low"}' }
  ]);
  assert.equal(result.remaining, "");
});

test("parseSseBuffer keeps incomplete trailing message in remaining buffer", () => {
  const input =
    'event: chunk\ndata: {"text":"桥"}\n\n' +
    'event: chunk\ndata: {"text":"梁"';

  const result = parseSseBuffer(input);

  assert.deepEqual(result.events, [{ event: "chunk", data: '{"text":"桥"}' }]);
  assert.equal(result.remaining, 'event: chunk\ndata: {"text":"梁"');
});

test("parseSseBuffer supports CRLF-delimited SSE messages", () => {
  const input =
    'event: chunk\r\ndata: {"text":"桥"}\r\n\r\n' +
    'event: done\r\ndata: {"confidence":"low"}\r\n\r\n';

  const result = parseSseBuffer(input);

  assert.deepEqual(result.events, [
    { event: "chunk", data: '{"text":"桥"}' },
    { event: "done", data: '{"confidence":"low"}' }
  ]);
  assert.equal(result.remaining, "");
});

test("matchSourceToDocumentId normalizes eurocode source labels", () => {
  const documents = [
    {
      id: "EN1990_2002",
      name: "EN1990 2002",
      title: "Eurocode - Basis of structural design",
      total_pages: 120,
      chunk_count: 0
    }
  ];

  const match = matchSourceToDocumentId("EN 1990:2002", documents);

  assert.equal(match, "EN1990_2002");
});

test("buildDocumentFileUrl returns raw PDF endpoint", () => {
  const url = buildDocumentFileUrl("EN1990_2002");

  assert.equal(url, "http://localhost:8080/api/v1/documents/EN1990_2002/file");
});

test("translateSource posts a single citation payload", async () => {
  const seenBodies: string[] = [];
  const originalFetch = globalThis.fetch;
  const payload = {
    document_id: "EN1990_2002",
    file: "EN 1990:2002",
    title: "Eurocode - Basis of structural design",
    section: "Section 2 Requirements > 2.3 Design working life",
    page: "28",
    clause: "2.3(1)",
    original_text: "The design working life should be specified.",
    locator_text: "2.3 Design working life (1) The design working life should be specified."
  };

  try {
    globalThis.fetch = async (_input, init) => {
      seenBodies.push(String(init?.body ?? ""));
      return new Response(JSON.stringify({ translation: "设计使用年限应予规定。" }), {
        status: 200,
        headers: { "Content-Type": "application/json" }
      });
    };

    const result = await translateSource(payload);

    assert.deepEqual(result, { translation: "设计使用年限应予规定。" });
  } finally {
    globalThis.fetch = originalFetch;
  }

  assert.equal(seenBodies.length, 1);
  assert.deepEqual(JSON.parse(seenBodies[0] ?? "{}"), payload);
});

test("buildReferenceRecords prefers source document_id over fuzzy matching", () => {
  const references = buildReferenceRecords(
    [
      {
        file: "EN 1990:2002",
        document_id: "EXACT_DOC_ID",
        title: "Basis",
        section: "2.3",
        page: "28",
        clause: "2.3(1)",
        original_text: "The design working life should be specified.",
        highlight_text: "The design working life should be specified.",
        locator_text: "2.3 Design working life (1) The design working life should be specified.",
        translation: ""
      }
    ],
    [
      {
        id: "FUZZY_MATCH_ID",
        name: "EN1990 2002",
        title: "Eurocode - Basis of structural design",
        total_pages: 120,
        chunk_count: 0
      }
    ],
    "high",
    []
  );

  assert.equal(references[0]?.documentId, "EXACT_DOC_ID");
  assert.equal(
    references[0]?.source.highlight_text,
    "The design working life should be specified."
  );
});

test("getPreferredReferenceIndex prefers the first source with a clause", () => {
  const index = getPreferredReferenceIndex([
    {
      file: "EN 1990:2002",
      document_id: "EN1990_2002",
      title: "Basis",
      section: "Additional information",
      page: "10",
      clause: "",
      original_text: "General introduction.",
      highlight_text: "General introduction.",
      locator_text: "General introduction.",
      translation: ""
    },
    {
      file: "EN 1990:2002",
      document_id: "EN1990_2002",
      title: "Basis",
      section: "1.1 Scope",
      page: "12",
      clause: "1.1",
      original_text: "Scope paragraph.",
      highlight_text: "Scope paragraph.",
      locator_text: "Scope paragraph.",
      translation: ""
    }
  ]);

  assert.equal(index, 1);
});

test("readSseStream emits parsed events from a ReadableStream body", async () => {
  const encoder = new TextEncoder();
  const seen: Array<{ event: string; data: string }> = [];
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      controller.enqueue(
        encoder.encode('event: chunk\ndata: {"text":"桥"}\n\n')
      );
      controller.enqueue(
        encoder.encode('event: done\ndata: {"confidence":"low"}\n\n')
      );
      controller.close();
    }
  });

  await readSseStream(stream, (message) => {
    seen.push(message);
  });

  assert.deepEqual(seen, [
    { event: "chunk", data: '{"text":"桥"}' },
    { event: "done", data: '{"confidence":"low"}' }
  ]);
});

test("readSseStream handles CRLF chunks produced by sse-starlette", async () => {
  const encoder = new TextEncoder();
  const seen: Array<{ event: string; data: string }> = [];
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      controller.enqueue(
        encoder.encode('event: chunk\r\ndata: {"text":"桥"}\r\n\r\n')
      );
      controller.enqueue(
        encoder.encode('event: done\r\ndata: {"confidence":"low"}\r\n\r\n')
      );
      controller.close();
    }
  });

  await readSseStream(stream, (message) => {
    seen.push(message);
  });

  assert.deepEqual(seen, [
    { event: "chunk", data: '{"text":"桥"}' },
    { event: "done", data: '{"confidence":"low"}' }
  ]);
});

test("queryStream forwards reasoning events to the caller", async () => {
  const encoder = new TextEncoder();
  const reasoning: string[] = [];
  const chunks: string[] = [];
  const donePayloads: Array<{
    confidence: string;
    retrieval_context?: {
      chunks: Array<{ chunk_id: string; score?: number }>;
      parent_chunks: Array<{ chunk_id: string }>;
    } | null;
  }> = [];
  const originalFetch = globalThis.fetch;

  try {
    globalThis.fetch = async () =>
      new Response(
        new ReadableStream<Uint8Array>({
          start(controller) {
            controller.enqueue(
              encoder.encode('event: reasoning\ndata: {"text":"先定位条款。"}\n\n')
            );
            controller.enqueue(
              encoder.encode('event: chunk\ndata: {"text":"结论"}\n\n')
            );
            controller.enqueue(
              encoder.encode(
                'event: done\ndata: {"confidence":"low","sources":[],"related_refs":[],"retrieval_context":{"chunks":[{"chunk_id":"chunk_023","score":0.91}],"parent_chunks":[]}}\n\n'
              )
            );
            controller.close();
          }
        }),
        { status: 200 }
      );

    await queryStream(
      {
        question: "桥梁设计使用年限是多少？",
        stream: true
      },
      {
        onReasoning: (text) => {
          reasoning.push(text);
        },
        onChunk: (text) => {
          chunks.push(text);
        },
        onDone: (payload) => {
          donePayloads.push({
            confidence: payload.confidence,
            retrieval_context: payload.retrieval_context
          });
        }
      }
    );
  } finally {
    globalThis.fetch = originalFetch;
  }

  assert.deepEqual(reasoning, ["先定位条款。"]);
  assert.deepEqual(chunks, ["结论"]);
  assert.deepEqual(donePayloads, [
    {
      confidence: "low",
      retrieval_context: {
        chunks: [{ chunk_id: "chunk_023", score: 0.91 }],
        parent_chunks: []
      }
    }
  ]);
});

test("queryStream forwards retrieval progress events to the caller", async () => {
  const encoder = new TextEncoder();
  const progressEvents: Array<{ title: string; summary: string }> = [];
  const originalFetch = globalThis.fetch;

  try {
    globalThis.fetch = async () =>
      new Response(
        new ReadableStream<Uint8Array>({
          start(controller) {
            controller.enqueue(
              encoder.encode(
                'event: progress\ndata: {"stage":"retrieving","status":"completed","title":"检索规范条文","summary":"找到 8 条相关规范证据。"}\n\n'
              )
            );
            controller.enqueue(
              encoder.encode(
                'event: done\ndata: {"confidence":"low","sources":[],"related_refs":[]}\n\n'
              )
            );
            controller.close();
          }
        }),
        { status: 200 }
      );

    await queryStream(
      {
        question: "桥梁设计使用年限是多少？",
        stream: true
      },
      {
        onReasoning: () => {},
        onChunk: () => {},
        onProgress: (payload) => {
          progressEvents.push({
            title: payload.title,
            summary: payload.summary
          });
        },
        onDone: () => {}
      }
    );
  } finally {
    globalThis.fetch = originalFetch;
  }

  assert.deepEqual(progressEvents, [
    {
      title: "检索规范条文",
      summary: "找到 8 条相关规范证据。"
    }
  ]);
});

test("query sends llm overrides in the request body", async () => {
  const seenBodies: string[] = [];
  const originalFetch = globalThis.fetch;

  try {
    globalThis.fetch = async (_input, init) => {
      seenBodies.push(String(init?.body ?? ""));
      return new Response(
        JSON.stringify({
          answer: "ok",
          sources: [],
          related_refs: [],
          confidence: "low",
          conversation_id: "conv-1"
        }),
        { status: 200, headers: { "Content-Type": "application/json" } }
      );
    };

    await query({
      question: "什么是设计使用年限？",
      llm: {
        api_key: "override-key",
        base_url: "https://dashscope.aliyuncs.com/compatible-mode/v1",
        model: "qwen3.5-plus",
        enable_thinking: true
      }
    });
  } finally {
    globalThis.fetch = originalFetch;
  }

  assert.equal(seenBodies.length, 1);
  assert.deepEqual(JSON.parse(seenBodies[0] ?? "{}"), {
    question: "什么是设计使用年限？",
    llm: {
      api_key: "override-key",
      base_url: "https://dashscope.aliyuncs.com/compatible-mode/v1",
      model: "qwen3.5-plus",
      enable_thinking: true
    }
  });
});

test("queryStream sends llm overrides in the stream request body", async () => {
  const encoder = new TextEncoder();
  const seenBodies: string[] = [];
  const originalFetch = globalThis.fetch;

  try {
    globalThis.fetch = async (_input, init) => {
      seenBodies.push(String(init?.body ?? ""));
      return new Response(
        new ReadableStream<Uint8Array>({
          start(controller) {
            controller.enqueue(
              encoder.encode('event: done\ndata: {"confidence":"low","sources":[],"related_refs":[]}\n\n')
            );
            controller.close();
          }
        }),
        { status: 200 }
      );
    };

    await queryStream(
      {
        question: "什么是设计使用年限？",
        llm: {
          base_url: "https://api.deepseek.com/v1",
          model: "deepseek-chat",
          enable_thinking: false
        }
      },
      {
        onReasoning: () => {},
        onChunk: () => {},
        onDone: () => {}
      }
    );
  } finally {
    globalThis.fetch = originalFetch;
  }

  assert.equal(seenBodies.length, 1);
  assert.deepEqual(JSON.parse(seenBodies[0] ?? "{}"), {
    question: "什么是设计使用年限？",
    llm: {
      base_url: "https://api.deepseek.com/v1",
      model: "deepseek-chat",
      enable_thinking: false
    },
    stream: true
  });
});

test("getLlmSettings fetches masked server defaults", async () => {
  const originalFetch = globalThis.fetch;

  try {
    globalThis.fetch = async () =>
      new Response(
        JSON.stringify({
          base_url: "https://api.deepseek.com/v1",
          model: "deepseek-chat",
          enable_thinking: true,
          api_key_configured: false
        }),
        { status: 200, headers: { "Content-Type": "application/json" } }
      );

    const result = await getLlmSettings();

    assert.deepEqual(result, {
      base_url: "https://api.deepseek.com/v1",
      model: "deepseek-chat",
      enable_thinking: true,
      api_key_configured: false
    });
  } finally {
    globalThis.fetch = originalFetch;
  }
});
