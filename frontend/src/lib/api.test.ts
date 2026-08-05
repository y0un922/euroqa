import test from "node:test";
import assert from "node:assert/strict";

import {
  buildChatQueryPayload,
  buildDocumentFileUrl,
  buildReferenceRecords,
  deleteConversationSession,
  getConversationSession,
  getConversationSessions,
  getPreferredReferenceIndex,
  getLlmSettings,
  matchSourceToDocumentId,
  parseSseBuffer,
  query,
  queryStream,
  readSseStream,
  translateSource,
  uploadDocumentToMinio,
} from "./api.ts";

test("buildChatQueryPayload uses external sessionId and omits domain", () => {
  const payload = buildChatQueryPayload({
    question: "设计使用年限是多少？",
    sessionId: "1001_abc123",
    llm: {
      model: "qwen3.5-plus",
    },
  });

  assert.deepEqual(payload, {
    question: "设计使用年限是多少？",
    sessionId: "1001_abc123",
    llm: {
      model: "qwen3.5-plus",
    },
  });
  assert.equal("domain" in payload, false);
});

test("buildChatQueryPayload includes docIds and kbIds when provided", () => {
  const payload = buildChatQueryPayload({
    question: "设计使用年限是多少？",
    sessionId: "1001_abc123",
    docIds: ["EN1990_2002", "EN1992-1-1_2004"],
    kbIds: ["kb-1"],
  });

  assert.deepEqual(payload, {
    question: "设计使用年限是多少？",
    sessionId: "1001_abc123",
    docIds: ["EN1990_2002", "EN1992-1-1_2004"],
    kbIds: ["kb-1"],
  });
});

test("parseSseBuffer parses complete SSE messages and clears buffer", () => {
  const input =
    'event: chunk\ndata: {"text":"桥"}\n\n' +
    'event: done\ndata: {"confidence":"low"}\n\n';

  const result = parseSseBuffer(input);

  assert.deepEqual(result.events, [
    { event: "chunk", data: '{"text":"桥"}' },
    { event: "done", data: '{"confidence":"low"}' },
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
    { event: "done", data: '{"confidence":"low"}' },
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
      chunk_count: 0,
    },
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
    locator_text:
      "2.3 Design working life (1) The design working life should be specified.",
  };

  try {
    globalThis.fetch = async (_input, init) => {
      seenBodies.push(String(init?.body ?? ""));
      return new Response(
        JSON.stringify({ translation: "设计使用年限应予规定。" }),
        {
          status: 200,
          headers: { "Content-Type": "application/json" },
        },
      );
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
        display_title: "Eurocode - Basis of structural design",
        title: "Basis",
        section: "2.3",
        page: "28",
        clause: "2.3(1)",
        original_text: "The design working life should be specified.",
        highlight_text: "The design working life should be specified.",
        locator_text:
          "2.3 Design working life (1) The design working life should be specified.",
        translation: "",
      },
    ],
    [
      {
        id: "EXACT_DOC_ID",
        name: "Exact document",
        title: "Exact document",
        total_pages: 1,
        chunk_count: 0,
      },
      {
        id: "FUZZY_MATCH_ID",
        name: "EN1990 2002",
        title: "Eurocode - Basis of structural design",
        total_pages: 120,
        chunk_count: 0,
      },
    ],
    "high",
    [],
  );

  assert.equal(references[0]?.documentId, "EXACT_DOC_ID");
  assert.equal(references[0]?.displayTitle, "EN 1990:2002");
  assert.equal(
    references[0]?.source.highlight_text,
    "The design working life should be specified.",
  );
});

test("buildReferenceRecords falls back to file match when source document_id is stale", () => {
  const references = buildReferenceRecords(
    [
      {
        file: "EN1992-1-1_2004(1).pdf",
        document_id: "EN1992-1-1_2004_1_pdf",
        display_title: "Eurocode 2: Design of concrete structures",
        title: "EN1992-1-1 2004(1).pdf",
        section: "2.4",
        page: "23",
        clause: "2.4.1",
        original_text: "Partial factors are given.",
        highlight_text: "Partial factors are given.",
        locator_text: "Partial factors are given.",
        translation: "",
      },
    ],
    [
      {
        id: "EN1992-1-1_2004(1).pdf",
        name: "EN1992-1-1 2004(1).pdf",
        title: "EN 1992-1-1:2004",
        total_pages: 225,
        chunk_count: 0,
      },
    ],
    "high",
    [],
  );

  assert.equal(references[0]?.documentId, "EN1992-1-1_2004(1).pdf");
});

test("buildReferenceRecords uses display title when source file is an opaque doc id", () => {
  const references = buildReferenceRecords(
    [
      {
        file: "ae71c790b26bdcc126b3be00be4f9825",
        document_id: "ae71c790b26bdcc126b3be00be4f9825",
        display_title: "Structural fire design",
        title: "Structural fire design",
        section: "Detailing",
        page: "199",
        clause: "10.5 Laps",
        original_text: "",
        highlight_text: "",
        locator_text: "",
        translation: "",
      },
    ],
    [],
    "high",
    [],
  );

  assert.equal(references[0]?.displayTitle, "Structural fire design");
});

test("buildReferenceRecords accepts camelCase display title aliases for opaque doc ids", () => {
  const references = buildReferenceRecords(
    [
      {
        file: "ae71c790b26bdcc126b3be00be4f9825",
        document_id: "ae71c790b26bdcc126b3be00be4f9825",
        displayTitle: "DG_EN1992-1-1, -1-2 混凝土设计指南.pdf",
        title: "ae71c790b26bdcc126b3be00be4f9825",
        section: "Detailing",
        page: "199",
        clause: "10.5 Laps",
        original_text: "",
        highlight_text: "",
        locator_text: "",
        translation: "",
      },
    ],
    [],
    "high",
    [],
  );

  assert.equal(
    references[0]?.displayTitle,
    "DG_EN1992-1-1, -1-2 混凝土设计指南.pdf",
  );
});

test("buildReferenceRecords accepts source title aliases for opaque doc ids", () => {
  const references = buildReferenceRecords(
    [
      {
        file: "ae71c790b26bdcc126b3be00be4f9825",
        document_id: "ae71c790b26bdcc126b3be00be4f9825",
        source_title: "DG_EN1992-1-1, -1-2 混凝土设计指南.pdf",
        title: "ae71c790b26bdcc126b3be00be4f9825",
        section: "Detailing",
        page: "199",
        clause: "10.5 Laps",
        original_text: "",
        highlight_text: "",
        locator_text: "",
        translation: "",
      },
    ],
    [],
    "high",
    [],
  );

  assert.equal(
    references[0]?.displayTitle,
    "DG_EN1992-1-1, -1-2 混凝土设计指南.pdf",
  );
});

test("buildReferenceRecords displays the source file instead of parsed titles", () => {
  const references = buildReferenceRecords(
    [
      {
        file: "EN 1992:2004",
        document_id: "EN1992_2004",
        display_title: "Eurocode 2: Design of concrete structures",
        title: "Eurocode 2: Design of concrete structures",
        section: "2.3",
        page: "28",
        clause: "2.3(1)",
        original_text: "",
        highlight_text: "",
        locator_text: "",
        translation: "",
      },
    ],
    [
      {
        id: "EN1992_2004",
        name: "EN1992 2004",
        title: "Eurocode 2: Design of concrete structures",
        total_pages: 225,
        chunk_count: 0,
      },
    ],
    "high",
    [],
  );

  assert.equal(references[0]?.displayTitle, "EN 1992:2004");
});

test("buildReferenceRecords ignores snippet-like source titles in favor of source file", () => {
  const bibliographySnippet =
    "Designers' Guide to EN 1991-1-2, 1992-1-2, 1993-1-2 and EN 1994-1-2. Eurocode 1: Actions on Structures. Eurocode 3: Design of Steel Structures. Eurocode 4: Design of Composite Steel and Concrete Structures. Fire Engineering.";
  const references = buildReferenceRecords(
    [
      {
        file: "DG_EN1992-1-1_-1-2",
        document_id: "DG_EN1992-1-1_-1-2",
        display_title: bibliographySnippet,
        title: bibliographySnippet,
        section: "References",
        page: "1",
        clause: "",
        original_text: bibliographySnippet,
        highlight_text: bibliographySnippet,
        locator_text: bibliographySnippet,
        translation: "",
      },
    ],
    [
      {
        id: "DG_EN1992-1-1_-1-2",
        name: "DG EN1992-1-1 -1-2",
        title: "DG EN1992-1-1 -1-2",
        total_pages: 180,
        chunk_count: 0,
      },
    ],
    "medium",
    [],
  );

  assert.equal(references[0]?.displayTitle, "DG_EN1992-1-1_-1-2");
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
      translation: "",
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
      translation: "",
    },
  ]);

  assert.equal(index, 1);
});

test("readSseStream emits parsed events from a ReadableStream body", async () => {
  const encoder = new TextEncoder();
  const seen: Array<{ event: string; data: string }> = [];
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      controller.enqueue(
        encoder.encode('event: chunk\ndata: {"text":"桥"}\n\n'),
      );
      controller.enqueue(
        encoder.encode('event: done\ndata: {"confidence":"low"}\n\n'),
      );
      controller.close();
    },
  });

  await readSseStream(stream, (message) => {
    seen.push(message);
  });

  assert.deepEqual(seen, [
    { event: "chunk", data: '{"text":"桥"}' },
    { event: "done", data: '{"confidence":"low"}' },
  ]);
});

test("readSseStream handles CRLF chunks produced by sse-starlette", async () => {
  const encoder = new TextEncoder();
  const seen: Array<{ event: string; data: string }> = [];
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      controller.enqueue(
        encoder.encode('event: chunk\r\ndata: {"text":"桥"}\r\n\r\n'),
      );
      controller.enqueue(
        encoder.encode('event: done\r\ndata: {"confidence":"low"}\r\n\r\n'),
      );
      controller.close();
    },
  });

  await readSseStream(stream, (message) => {
    seen.push(message);
  });

  assert.deepEqual(seen, [
    { event: "chunk", data: '{"text":"桥"}' },
    { event: "done", data: '{"confidence":"low"}' },
  ]);
});

test("queryStream forwards reasoning events to the caller", async () => {
  const encoder = new TextEncoder();
  const reasoning: string[] = [];
  const chunks: string[] = [];
  const donePayloads: Array<{
    code?: number;
    confidence: string;
    answerMode?: string;
    questionType?: string | null;
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
              encoder.encode(
                'event: reasoning\ndata: {"text":"先定位条款。"}\n\n',
              ),
            );
            controller.enqueue(
              encoder.encode('event: chunk\ndata: {"text":"结论"}\n\n'),
            );
            controller.enqueue(
              encoder.encode(
                'event: done\ndata: {"code":200,"confidence":"low","answerMode":"fallback","questionType":"parameter","sources":[],"related_refs":[],"retrieval_context":{"chunks":[{"chunk_id":"chunk_023","score":0.91}],"parent_chunks":[]}}\n\n',
              ),
            );
            controller.close();
          },
        }),
        { status: 200 },
      );

    await queryStream(
      {
        question: "桥梁设计使用年限是多少？",
        stream: true,
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
            code: payload.code,
            confidence: payload.confidence,
            answerMode: payload.answerMode,
            questionType: payload.questionType,
            retrieval_context: payload.retrieval_context,
          });
        },
      },
    );
  } finally {
    globalThis.fetch = originalFetch;
  }

  assert.deepEqual(reasoning, ["先定位条款。"]);
  assert.deepEqual(chunks, ["结论"]);
  assert.deepEqual(donePayloads, [
    {
      code: 200,
      confidence: "low",
      answerMode: "fallback",
      questionType: "parameter",
      retrieval_context: {
        chunks: [{ chunk_id: "chunk_023", score: 0.91 }],
        parent_chunks: [],
      },
    },
  ]);
});

test("queryStream forwards usage and elapsed time in done payloads", async () => {
  const encoder = new TextEncoder();
  const donePayloads: Array<{
    usage?: Record<string, number> | null;
    elapsed_ms?: number | null;
  }> = [];
  const originalFetch = globalThis.fetch;

  try {
    globalThis.fetch = async () =>
      new Response(
        new ReadableStream<Uint8Array>({
          start(controller) {
            controller.enqueue(
              encoder.encode(
                'event: done\ndata: {"confidence":"low","sources":[],"related_refs":[],"usage":{"input_tokens":11,"output_tokens":22,"total_tokens":33},"elapsed_ms":987}\n\n',
              ),
            );
            controller.close();
          },
        }),
        { status: 200 },
      );

    await queryStream(
      {
        question: "桥梁设计使用年限是多少？",
        stream: true,
      },
      {
        onReasoning: () => {},
        onChunk: () => {},
        onDone: (payload) => {
          donePayloads.push({
            usage: payload.usage ?? null,
            elapsed_ms: payload.elapsed_ms ?? null,
          });
        },
      },
    );
  } finally {
    globalThis.fetch = originalFetch;
  }

  assert.deepEqual(donePayloads, [
    {
      usage: { input_tokens: 11, output_tokens: 22, total_tokens: 33 },
      elapsed_ms: 987,
    },
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
                'event: progress\ndata: {"stage":"retrieving","status":"completed","title":"检索规范条文","summary":"找到 8 条相关规范证据。"}\n\n',
              ),
            );
            controller.enqueue(
              encoder.encode(
                'event: done\ndata: {"confidence":"low","sources":[],"related_refs":[]}\n\n',
              ),
            );
            controller.close();
          },
        }),
        { status: 200 },
      );

    await queryStream(
      {
        question: "桥梁设计使用年限是多少？",
        stream: true,
      },
      {
        onReasoning: () => {},
        onChunk: () => {},
        onProgress: (payload) => {
          progressEvents.push({
            title: payload.title,
            summary: payload.summary,
          });
        },
        onDone: () => {},
      },
    );
  } finally {
    globalThis.fetch = originalFetch;
  }

  assert.deepEqual(progressEvents, [
    {
      title: "检索规范条文",
      summary: "找到 8 条相关规范证据。",
    },
  ]);
});

test("queryStream forwards commentary events to the caller", async () => {
  const encoder = new TextEncoder();
  const commentaries: string[] = [];
  const originalFetch = globalThis.fetch;

  try {
    globalThis.fetch = async () =>
      new Response(
        new ReadableStream<Uint8Array>({
          start(controller) {
            controller.enqueue(
              encoder.encode(
                'event: commentary\ndata: {"text":"正在搜索规范知识库：「预应力钢筋」..."}\n\n',
              ),
            );
            controller.enqueue(
              encoder.encode(
                'event: done\ndata: {"confidence":"low","sources":[],"related_refs":[]}\n\n',
              ),
            );
            controller.close();
          },
        }),
        { status: 200 },
      );

    await queryStream(
      {
        question: "预应力钢筋松弛系数是多少？",
        stream: true,
      },
      {
        onReasoning: () => {},
        onChunk: () => {},
        onCommentary: (text) => {
          commentaries.push(text);
        },
        onDone: () => {},
      },
    );
  } finally {
    globalThis.fetch = originalFetch;
  }

  assert.deepEqual(commentaries, ["正在搜索规范知识库：「预应力钢筋」..."]);
});

test("queryStream forwards tool progress events to the caller", async () => {
  const encoder = new TextEncoder();
  const toolSteps: Array<{ stepId: string; summary: string }> = [];
  const originalFetch = globalThis.fetch;

  try {
    globalThis.fetch = async () =>
      new Response(
        new ReadableStream<Uint8Array>({
          start(controller) {
            controller.enqueue(
              encoder.encode(
                'event: tool_progress\ndata: {"tool_name":"retrieve","step":{"step_id":"query_understanding","status":"completed","title":"理解问题","summary":"扩展 3 条查询","metadata":{"was_rewritten":false},"elapsed_ms":12,"parent_step_id":null},"elapsed_ms":20,"request_id":"req-1"}\n\n',
              ),
            );
            controller.enqueue(
              encoder.encode(
                'event: done\ndata: {"confidence":"low","sources":[],"related_refs":[]}\n\n',
              ),
            );
            controller.close();
          },
        }),
        { status: 200 },
      );

    await queryStream(
      {
        question: "保护层厚度怎么确定？",
        stream: true,
      },
      {
        onReasoning: () => {},
        onChunk: () => {},
        onToolProgress: (payload) => {
          toolSteps.push({
            stepId: payload.step.step_id,
            summary: payload.step.summary,
          });
        },
        onDone: () => {},
      },
    );
  } finally {
    globalThis.fetch = originalFetch;
  }

  assert.deepEqual(toolSteps, [
    {
      stepId: "query_understanding",
      summary: "扩展 3 条查询",
    },
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
          conversation_id: "conv-1",
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      );
    };

    await query({
      question: "什么是设计使用年限？",
      llm: {
        api_key: "override-key",
        base_url: "https://dashscope.aliyuncs.com/compatible-mode/v1",
        model: "qwen3.5-plus",
        enable_thinking: true,
      },
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
      enable_thinking: true,
    },
  });
});

test("getConversationSession fetches redis-backed session history", async () => {
  const seenUrls: string[] = [];
  const originalFetch = globalThis.fetch;

  try {
    globalThis.fetch = async (input) => {
      seenUrls.push(String(input));
      return new Response(
        JSON.stringify({
          sessionId: "1001_abc123",
          conversationId: "1001_abc123",
          messages: [
            {
              id: "1001_abc123-1",
              question: "设计使用年限是什么？",
              answer: "应规定设计使用年限。",
              reasoning: "",
              status: "done",
              confidence: "high",
              sources: [],
              relatedRefs: [],
              degraded: false,
              conversationId: "1001_abc123",
              retrievalContext: null,
              progressEvents: [],
              commentaries: [],
            },
          ],
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      );
    };

    const session = await getConversationSession("1001_abc123");

    assert.equal(session.conversationId, "1001_abc123");
    assert.equal(session.messages[0]?.question, "设计使用年限是什么？");
  } finally {
    globalThis.fetch = originalFetch;
  }

  assert.match(seenUrls[0] ?? "", /\/api\/v1\/sessions\/1001_abc123$/);
});

test("getConversationSessions fetches redis-backed session summaries", async () => {
  const seenUrls: string[] = [];
  const originalFetch = globalThis.fetch;

  try {
    globalThis.fetch = async (input) => {
      seenUrls.push(String(input));
      return new Response(
        JSON.stringify({
          sessions: [
            {
              sessionId: "1001_abc123",
              conversationId: "1001_abc123",
              title: "设计使用年限",
              updatedAt: "2026-05-31T10:00:00Z",
              messageCount: 2,
            },
          ],
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      );
    };

    const response = await getConversationSessions("1001");

    assert.equal(response.sessions[0]?.sessionId, "1001_abc123");
    assert.equal(response.sessions[0]?.messageCount, 2);
  } finally {
    globalThis.fetch = originalFetch;
  }

  assert.match(seenUrls[0] ?? "", /\/api\/v1\/sessions\?userId=1001$/);
});

test("deleteConversationSession deletes one redis-backed session", async () => {
  const seen: Array<{ url: string; method?: string }> = [];
  const originalFetch = globalThis.fetch;

  try {
    globalThis.fetch = async (input, init) => {
      seen.push({ url: String(input), method: init?.method });
      return new Response(
        JSON.stringify({
          sessionId: "1001_abc123",
          deleted: true,
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      );
    };

    const response = await deleteConversationSession("1001_abc123");

    assert.equal(response.sessionId, "1001_abc123");
    assert.equal(response.deleted, true);
  } finally {
    globalThis.fetch = originalFetch;
  }

  assert.match(seen[0]?.url ?? "", /\/api\/v1\/sessions\/1001_abc123$/);
  assert.equal(seen[0]?.method, "DELETE");
});

test("queryStream rejects JSON error envelopes instead of treating them as SSE", async () => {
  const originalFetch = globalThis.fetch;

  try {
    globalThis.fetch = async () =>
      new Response(
        JSON.stringify({
          code: 400,
          message: "docIds 不能为空，请传入本次允许检索的文档 ID 列表",
          detail: null,
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      );

    await assert.rejects(
      () =>
        queryStream(
          {
            question: "设计使用年限是多少？",
            stream: true,
          },
          {
            onReasoning: () => {},
            onChunk: () => {},
            onDone: () => {},
          },
        ),
      /docIds 不能为空/,
    );
  } finally {
    globalThis.fetch = originalFetch;
  }
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
              encoder.encode(
                'event: done\ndata: {"confidence":"low","sources":[],"related_refs":[]}\n\n',
              ),
            );
            controller.close();
          },
        }),
        { status: 200 },
      );
    };

    await queryStream(
      {
        question: "什么是设计使用年限？",
        llm: {
          base_url: "https://api.deepseek.com/v1",
          model: "deepseek-chat",
          enable_thinking: false,
        },
      },
      {
        onReasoning: () => {},
        onChunk: () => {},
        onDone: () => {},
      },
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
      enable_thinking: false,
    },
    stream: true,
  });
});

test("queryStream forwards sessionId in the stream request body", async () => {
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
              encoder.encode(
                'event: done\ndata: {"confidence":"low","sources":[],"related_refs":[]}\n\n',
              ),
            );
            controller.close();
          },
        }),
        { status: 200 },
      );
    };

    await queryStream(
      {
        question: "什么是设计使用年限？",
        sessionId: "1001_abc123",
      },
      {
        onReasoning: () => {},
        onChunk: () => {},
        onDone: () => {},
      },
    );
  } finally {
    globalThis.fetch = originalFetch;
  }

  assert.equal(seenBodies.length, 1);
  assert.deepEqual(JSON.parse(seenBodies[0] ?? "{}"), {
    question: "什么是设计使用年限？",
    sessionId: "1001_abc123",
    stream: true,
  });
});

test("uploadDocumentToMinio posts PDF and summary flag to backend proxy endpoint", async () => {
  const seenUrls: string[] = [];
  const seenMethods: string[] = [];
  const seenBodies: unknown[] = [];
  const originalFetch = globalThis.fetch;

  try {
    globalThis.fetch = async (input, init) => {
      seenUrls.push(String(input));
      seenMethods.push(String(init?.method ?? ""));
      seenBodies.push(init?.body);
      return new Response(
        JSON.stringify({
          code: 200,
          docId: "EN_1992_1_1",
          fileName: "EN 1992-1-1.pdf",
          minioPath: "eurocode/uploads/EN_1992_1_1.pdf",
          status: "processing",
          message: "已加入解析队列",
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      );
    };

    const file = new File(["%PDF-1.4"], "EN 1992-1-1.pdf", {
      type: "application/pdf",
    });
    const result = await uploadDocumentToMinio(file, false);

    assert.equal(result.docId, "EN_1992_1_1");
    assert.equal(result.minioPath, "eurocode/uploads/EN_1992_1_1.pdf");
  } finally {
    globalThis.fetch = originalFetch;
  }

  assert.equal(
    seenUrls[0],
    "http://localhost:8080/api/v1/documents/upload-to-minio",
  );
  assert.equal(seenMethods[0], "POST");
  assert.ok(seenBodies[0] instanceof FormData);
  const formData = seenBodies[0] as FormData;
  assert.equal(formData.get("contextSummaryEnabled"), "false");
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
          api_key_configured: false,
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      );

    const result = await getLlmSettings();

    assert.deepEqual(result, {
      base_url: "https://api.deepseek.com/v1",
      model: "deepseek-chat",
      enable_thinking: true,
      api_key_configured: false,
    });
  } finally {
    globalThis.fetch = originalFetch;
  }
});
