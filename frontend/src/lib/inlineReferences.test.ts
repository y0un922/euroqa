import assert from "node:assert/strict";
import test from "node:test";

import { buildInlineReferenceAnchor, getReferenceOrdinal } from "./inlineReferences.ts";
import type { ReferenceRecord } from "./types.ts";

const references: ReferenceRecord[] = [
  {
    id: "m5-ref-1",
    source: {
      file: "EN1990 2002",
      title: "Basis",
      section: "Section 3",
      page: "12",
      clause: "3.1",
      original_text: "",
      translation: ""
    },
    documentId: "EN1990_2002",
    confidence: "high",
    relatedRefs: []
  },
  {
    id: "m5-ref-2",
    source: {
      file: "EN1991-1-4",
      title: "Actions on structures",
      section: "Section 2",
      page: "44",
      clause: "4.2.1",
      original_text: "",
      translation: ""
    },
    documentId: "EN1991_1_4",
    confidence: "medium",
    relatedRefs: []
  }
];

test("getReferenceOrdinal maps reference ids to stable one-based indices", () => {
  assert.equal(getReferenceOrdinal("m5-ref-1", references), 1);
  assert.equal(getReferenceOrdinal("m5-ref-2", references), 2);
  assert.equal(getReferenceOrdinal("missing-ref", references), null);
});

test("buildInlineReferenceAnchor returns compact metadata for matched citations", () => {
  const anchor = buildInlineReferenceAnchor(
    "EN 1991-1-4 · 4.2.1",
    "m5-ref-2",
    references
  );

  assert.deepEqual(anchor, {
    badge: "2",
    tone: "matched",
    tooltip: "引用 2 · EN1991-1-4 · 4.2.1",
    ariaLabel: "查看引用 2：EN1991-1-4 4.2.1"
  });
});

test("buildInlineReferenceAnchor shows ? badge for unmatched Ref-N citations", () => {
  const anchor = buildInlineReferenceAnchor(
    "Ref-99",
    null,
    references
  );

  assert.deepEqual(anchor, {
    badge: "?",
    tone: "unmatched",
    tooltip: "未命中引用 · Ref-99",
    ariaLabel: "未命中引用：Ref-99"
  });
});

test("buildInlineReferenceAnchor extracts clause from legacy freeform labels", () => {
  const anchor = buildInlineReferenceAnchor(
    "EN 1990:2002 · A1.2.1(4)",
    null,
    references
  );

  assert.deepEqual(anchor, {
    badge: "A1.2.1",
    tone: "unmatched",
    tooltip: "未命中引用 · EN 1990:2002 · A1.2.1(4)",
    ariaLabel: "未命中引用：EN 1990:2002 · A1.2.1(4)"
  });
});
