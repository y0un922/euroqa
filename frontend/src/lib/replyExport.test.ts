import assert from "node:assert/strict";
import test from "node:test";

import {
  buildConversationExportFilename,
  buildConversationMarkdown,
  buildReplyMarkdown,
  copyMarkdownToClipboard,
  downloadMarkdownFile,
  isChatTurnExportable
} from "./replyExport.ts";
import type { ChatTurn } from "./types.ts";

function createDoneTurn(overrides: Partial<ChatTurn> = {}): ChatTurn {
  return {
    id: "turn-1",
    question: "桥梁设计使用年限是多少？",
    answer: "通常参考 **100 年**。",
    reasoning: "先定位条文，再确认表格范围。",
    status: "done",
    confidence: "medium",
    sources: [
      {
        file: "EN 1990:2002",
        document_id: "EN1990_2002",
        title: "Eurocode - Basis of structural design",
        section: "Section 2 Requirements > 2.3 Design working life",
        page: "28",
        clause: "2.3(1)",
        original_text: "The design working life should be specified.",
        highlight_text: "The design working life should be specified.",
        locator_text: "2.3 Design working life (1) The design working life should be specified.",
        translation: ""
      }
    ],
    relatedRefs: ["EN 1990 Table 2.1"],
    degraded: false,
    conversationId: "conv-1",
    retrievalContext: {
      chunks: [
        {
          chunk_id: "chunk_023",
          document_id: "EN1990_2002",
          file: "EN 1990:2002",
          title: "Eurocode - Basis of structural design",
          section: "Section 2 Requirements > 2.3 Design working life",
          page: "28",
          clause: "2.3(1)",
          content: "The design working life should be specified.",
          score: 0.91
        }
      ],
      parent_chunks: [
        {
          chunk_id: "parent_chunk_002",
          document_id: "EN1990_2002",
          file: "EN 1990:2002",
          title: "Eurocode - Basis of structural design",
          section: "Section 2 Requirements",
          page: "28",
          clause: "2.3",
          content: "Indicative categories for design working life are listed in Table 2.1."
        }
      ]
    },
    ...overrides
  };
}

test("isChatTurnExportable only accepts completed turns with content", () => {
  assert.equal(isChatTurnExportable(createDoneTurn()), true);
  assert.equal(
    isChatTurnExportable(
      createDoneTurn({
        status: "streaming",
        answer: ""
      })
    ),
    false
  );
  assert.equal(
    isChatTurnExportable(
      createDoneTurn({
        answer: "",
        sources: [],
        relatedRefs: [],
        retrievalContext: null
      })
    ),
    false
  );
});

test("buildReplyMarkdown includes answer, citation sources and retrieval context", () => {
  const markdown = buildReplyMarkdown(createDoneTurn(), {
    conversationId: "conv-1",
    exportedAt: "2026-04-01T12:00:00Z"
  });

  assert.match(markdown, /^# Euro_QA Reply Export/m);
  assert.match(markdown, /- Conversation ID: conv-1/);
  assert.match(markdown, /## User Question/);
  assert.match(markdown, /桥梁设计使用年限是多少？/);
  assert.match(markdown, /## Answer Markdown/);
  assert.match(markdown, /通常参考 \*\*100 年\*\*。/);
  assert.match(markdown, /## Citation Sources/);
  assert.match(markdown, /### Source 1/);
  assert.match(markdown, /The design working life should be specified\./);
  assert.match(markdown, /## Related References/);
  assert.match(markdown, /EN 1990 Table 2\.1/);
  assert.match(markdown, /## Retrieval Context/);
  assert.match(markdown, /### Retrieved Chunks/);
  assert.match(markdown, /#### Chunk 1/);
  assert.match(markdown, /- Score: 0\.9100/);
  assert.match(markdown, /### Parent Chunks/);
});

test("buildConversationMarkdown only exports question and answer for completed turns", () => {
  const markdown = buildConversationMarkdown(
    [
      createDoneTurn(),
      createDoneTurn({
        id: "turn-2",
        question: "这一轮还没结束",
        answer: "",
        status: "streaming",
        sources: [],
        relatedRefs: [],
        retrievalContext: null
      }),
      createDoneTurn({
        id: "turn-3",
        question: "地铁结构设计应参考什么？",
        answer: "应结合荷载、耐久性和使用年限要求综合判断。",
        relatedRefs: []
      })
    ],
    {
      conversationId: "conv-1",
      exportedAt: "2026-04-01T12:30:00Z"
    }
  );

  assert.match(markdown, /^# Euro_QA Conversation Export/m);
  assert.match(markdown, /## Turn 1/);
  assert.match(markdown, /## Turn 2/);
  assert.match(markdown, /### User Question/);
  assert.match(markdown, /### Answer Markdown/);
  assert.doesNotMatch(markdown, /这一轮还没结束/);
  assert.match(markdown, /地铁结构设计应参考什么？/);
  assert.doesNotMatch(markdown, /### Citation Sources/);
  assert.doesNotMatch(markdown, /### Related References/);
  assert.doesNotMatch(markdown, /### Retrieval Context/);
  assert.doesNotMatch(markdown, /The design working life should be specified\./);
  assert.doesNotMatch(markdown, /EN 1990 Table 2\.1/);
});

test("buildConversationExportFilename produces a stable markdown filename", () => {
  assert.equal(
    buildConversationExportFilename("conv-1", "2026-04-01T12:30:45Z"),
    "euro-qa-conversation-conv-1-2026-04-01T12-30-45Z.md"
  );
});

test("copyMarkdownToClipboard writes markdown to clipboard", async () => {
  let copied = "";

  await copyMarkdownToClipboard("## Export", {
    writeText: async (value: string) => {
      copied = value;
    }
  });

  assert.equal(copied, "## Export");
});

test("downloadMarkdownFile creates an object URL and clicks the anchor", () => {
  const events: string[] = [];

  downloadMarkdownFile("session.md", "# Export", {
    createObjectURL: (blob) => {
      events.push(`create:${blob.size}`);
      return "blob:reply-export";
    },
    revokeObjectURL: (url) => {
      events.push(`revoke:${url}`);
    },
    createAnchor: () => ({
      href: "",
      download: "",
      click() {
        events.push("click");
      }
    })
  });

  assert.deepEqual(events, ["create:8", "click", "revoke:blob:reply-export"]);
});
