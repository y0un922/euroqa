import assert from "node:assert/strict";
import test from "node:test";

import {
  buildEvidenceDebugFields,
  getDefaultEvidenceDebugSectionKey,
  resolveActiveEvidenceDebugField
} from "./evidenceDebug.ts";

test("buildEvidenceDebugFields includes chunk and locator when they differ", () => {
  const fields = buildEvidenceDebugFields({
    highlight_text:
      "Depending on the character of the individual clauses distinction is made in EN 1990.",
    locator_text: "2.3 Design working life",
    original_text: "The design working life should be specified for the structure."
  });

  assert.deepEqual(fields, [
    {
      contentClassName: "max-h-[160px]",
      description: "检索命中的原始 chunk。",
      label: "Chunk",
      length: 62,
      panelClassName: "border-cyan-200 bg-cyan-50/40",
      sectionKey: "chunk",
      title: "PDF 原文",
      value: "The design working life should be specified for the structure."
    },
    {
      contentClassName: "max-h-[128px]",
      description: "PDF 高亮实际使用的文本。",
      label: "Highlight",
      length: 84,
      panelClassName: "border-emerald-200 bg-emerald-50/40",
      sectionKey: "highlight",
      title: "Highlight 文本",
      value:
        "Depending on the character of the individual clauses distinction is made in EN 1990."
    },
    {
      contentClassName: "max-h-[128px]",
      description: "高亮失败时的定位回退文本。",
      label: "Locator",
      length: 23,
      panelClassName: "border-amber-200 bg-amber-50/40",
      sectionKey: "locator",
      title: "Locator 文本",
      value: "2.3 Design working life"
    }
  ]);
});

test("buildEvidenceDebugFields omits locator when it matches the chunk text", () => {
  const fields = buildEvidenceDebugFields({
    highlight_text: "same content",
    locator_text: "  same content  ",
    original_text: "same content"
  });

  assert.deepEqual(fields, [
    {
      contentClassName: "max-h-[160px]",
      description: "检索命中的原始 chunk。",
      label: "Chunk",
      length: 12,
      panelClassName: "border-cyan-200 bg-cyan-50/40",
      sectionKey: "chunk",
      title: "PDF 原文",
      value: "same content"
    }
  ]);
});

test("resolveActiveEvidenceDebugField prefers the requested tab and falls back to the first field", () => {
  const fields = buildEvidenceDebugFields({
    highlight_text: "highlight text",
    locator_text: "locator text",
    original_text: "chunk text"
  });

  assert.equal(getDefaultEvidenceDebugSectionKey(fields), "chunk");
  assert.equal(
    resolveActiveEvidenceDebugField(fields, "locator")?.sectionKey,
    "locator"
  );
  assert.equal(
    resolveActiveEvidenceDebugField(fields, "bbox")?.sectionKey,
    "chunk"
  );
  assert.equal(resolveActiveEvidenceDebugField([], "chunk"), null);
});
