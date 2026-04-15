import assert from "node:assert/strict";
import test from "node:test";

import {
  bboxToOverlayStyle,
  canHighlightTextItem,
  clampPdfPage,
  findPdfHighlightItemIndexes,
  hasUsableLocatorText,
  hasUsablePdfBbox,
  normalizePdfText,
  resolvePdfHighlightMatch,
  resolvePdfLocationStatus
} from "./pdfLocator.ts";

test("normalizePdfText flattens whitespace and square brackets", () => {
  const normalized = normalizePdfText("  [Design   working]\nlife  ");

  assert.equal(normalized, "design working life");
});

test("normalizePdfText collapses hyphenated line breaks from PDF text", () => {
  const normalized = normalizePdfText("dura-\n bility of struc-\n tures");

  assert.equal(normalized, "durability of structures");
});

test("hasUsableLocatorText returns true for normal locator text", () => {
  assert.equal(
    hasUsableLocatorText("2.3 Design working life should be specified."),
    true
  );
  assert.equal(hasUsableLocatorText("设计使用年限应按规范规定"), true);
});

test("hasUsableLocatorText returns false for empty or weak locator text", () => {
  assert.equal(hasUsableLocatorText(""), false);
  assert.equal(hasUsableLocatorText("  [] "), false);
  assert.equal(hasUsableLocatorText("ab"), false);
});

test("canHighlightTextItem matches normalized locator content", () => {
  assert.equal(
    canHighlightTextItem(
      "Design working life should be specified",
      "  [Design working life]   should be specified. "
    ),
    true
  );
});

test("canHighlightTextItem accepts a longer PDF text item that contains the locator", () => {
  assert.equal(
    canHighlightTextItem(
      "Design working life should be specified in the annex",
      "working life should be specified"
    ),
    true
  );
});

test("canHighlightTextItem returns false when locator is unusable", () => {
  assert.equal(canHighlightTextItem("Design", "[]"), false);
});

test("canHighlightTextItem rejects short single-token false positives", () => {
  assert.equal(
    canHighlightTextItem(
      "Design",
      "Design working life should be specified."
    ),
    false
  );
  assert.equal(
    canHighlightTextItem(
      "should",
      "Design working life should be specified."
    ),
    false
  );
});

test("canHighlightTextItem rejects short generic repeated phrases", () => {
  assert.equal(
    canHighlightTextItem(
      "shall be specified",
      "Design working life shall be specified."
    ),
    false
  );
});

test("findPdfHighlightItemIndexes matches a continuous paragraph across multiple text items", () => {
  const indexes = findPdfHighlightItemIndexes(
    [
      "(1) Depending on the character of the individual clauses,",
      "distinction is made in EN 1990 between Principles",
      "and Application Rules."
    ],
    "(1) Depending on the character of the individual clauses, distinction is made in EN 1990 between Principles and Application Rules."
  );

  assert.deepEqual(indexes, [0, 1, 2]);
});

test("findPdfHighlightItemIndexes matches text split by PDF hyphenation", () => {
  const indexes = findPdfHighlightItemIndexes(
    [
      "EN 1990 describes the Principles and requirements for safety, serviceability and dura-",
      "bility of structures. It is based on the limit state concept used in conjunction with a par-",
      "tial factor method."
    ],
    "EN 1990 describes the Principles and requirements for safety, serviceability and durability of structures. It is based on the limit state concept used in conjunction with a partial factor method."
  );

  assert.deepEqual(indexes, [0, 1, 2]);
});

test("resolvePdfHighlightMatch keeps highlighting the page-local overlap when the chunk extends beyond the page", () => {
  const match = resolvePdfHighlightMatch({
    textItems: [
      "(1) Depending on the character of the individual clauses,",
      "distinction is made in EN 1990 between Principles",
      "and Application Rules."
    ],
    highlightText:
      "(1) Depending on the character of the individual clauses, distinction is made in EN 1990 between Principles and Application Rules. Extra trailing sentence.",
    locatorText:
      "Depending on the character of the individual clauses distinction is made"
  });

  assert.equal(match.status, "highlighted");
  assert.deepEqual(match.itemIndexes, [0, 1, 2]);
});

test("resolvePdfHighlightMatch returns highlighted with all matched indexes for full paragraph text", () => {
  const match = resolvePdfHighlightMatch({
    textItems: [
      "(1) Depending on the character of the individual clauses,",
      "distinction is made in EN 1990 between Principles",
      "and Application Rules."
    ],
    highlightText:
      "(1) Depending on the character of the individual clauses, distinction is made in EN 1990 between Principles and Application Rules.",
    locatorText: "Depending on the character of the individual clauses"
  });

  assert.equal(match.status, "highlighted");
  assert.deepEqual(match.itemIndexes, [0, 1, 2]);
});

test("resolvePdfLocationStatus returns highlighted only for strong matches", () => {
  assert.equal(
    resolvePdfLocationStatus({
      locatorText: "Design working life should be specified.",
      matchedTextItems: ["Design working life should be specified"]
    }),
    "highlighted"
  );
});

test("resolvePdfLocationStatus falls back to page_only for weak or empty locator", () => {
  assert.equal(
    resolvePdfLocationStatus({
      locatorText: "Design working life should be specified.",
      matchedTextItems: ["Design"]
    }),
    "page_only"
  );
  assert.equal(
    resolvePdfLocationStatus({
      locatorText: "",
      matchedTextItems: []
    }),
    "page_only"
  );
});

test("resolvePdfLocationStatus returns error when render failed", () => {
  assert.equal(
    resolvePdfLocationStatus({
      locatorText: "Design working life should be specified.",
      matchedTextItems: [],
      hasError: true
    }),
    "error"
  );
});

test("hasUsablePdfBbox accepts four-number table boxes and rejects invalid values", () => {
  assert.equal(hasUsablePdfBbox([186, 591, 858, 768]), true);
  assert.equal(hasUsablePdfBbox([186, 591, 858]), false);
  assert.equal(hasUsablePdfBbox([186, 591, Number.NaN, 768]), false);
});

test("clampPdfPage keeps page numbers within document bounds", () => {
  assert.equal(clampPdfPage(4, null), 4);
  assert.equal(clampPdfPage(0, 12), 1);
  assert.equal(clampPdfPage(20, 12), 12);
});

test("bboxToOverlayStyle converts 0-1000 bbox to CSS percentages", () => {
  const style = bboxToOverlayStyle([100, 200, 500, 600]);
  assert.deepEqual(style, {
    left: "10%",
    top: "20%",
    width: "40%",
    height: "40%",
  });
});

test("bboxToOverlayStyle returns null for invalid bbox", () => {
  assert.equal(bboxToOverlayStyle([100, 200]), null);
  assert.equal(bboxToOverlayStyle([]), null);
  assert.equal(bboxToOverlayStyle(undefined as any), null);
});

test("bboxToOverlayStyle clamps negative values to zero", () => {
  const style = bboxToOverlayStyle([-10, -20, 500, 600]);
  assert.equal(style?.left, "0%");
  assert.equal(style?.top, "0%");
});

test("bboxToOverlayStyle handles swapped coordinates", () => {
  const style = bboxToOverlayStyle([500, 600, 100, 200]);
  assert.deepEqual(style, {
    left: "10%",
    top: "20%",
    width: "40%",
    height: "40%",
  });
});

// --- 锚点测试：Phase 2 修复后变绿 ---

test("canHighlightTextItem accepts short Eurocode clause heading (FM-9 anchor)", () => {
  // FM-9: isStrongHighlightCandidate 阈值过高 (12 chars, 3 tokens>=4)
  // "6.1 actions" = 11 chars，只有 1 个 4+字符 token → 被拒绝
  // P2-T2 将阈值降低到 (6 chars, 2 tokens>=4) 后应变绿
  assert.equal(
    canHighlightTextItem(
      "6.1 Actions shall be classified according to their variation in time",
      "6.1 Actions"
    ),
    true,
    "short clause heading should be accepted after P2-T2 threshold fix"
  );
});

test("findPdfHighlightItemIndexes finds highlight when indexOf fails but window contains it (FM-10 anchor)", () => {
  // FM-10: findBestContainedWindow 只做正向包含检查
  // 当 chunk 高亮文本跨页时，indexOf 可能因额外前缀/后缀失败
  // 此时 page 上的文本窗口包含了 highlightText 的一部分
  // P2-T3 增加反向检查后应变绿
  //
  // 构造场景：highlightText 首部带有上一页的残余文本，导致 indexOf 失败
  // 而 page 上的单条目包含了去掉残余后的核心文本
  const pageItems = [
    "The partial factor for permanent actions in the accidental design situation should be 1.0."
  ];
  // highlightText 含有上一页的前导内容（"... For the design. "）
  // 拼接后整体不是 pageItems 文本的子串，indexOf 失败
  const highlightWithPreamble =
    "in accordance with the preceding clause. The partial factor for permanent actions in the accidental design situation should be 1.0.";

  const indexes = findPdfHighlightItemIndexes(pageItems, highlightWithPreamble);

  // 当前：indexOf 失败 → findBestContainedWindow 检查正向（highlight 包含窗口）
  // 窗口 "the partial factor..." (89 chars) 在 highlight (130 chars) 中 → 正向匹配应该成功
  // 但如果窗口长度 > highlight 长度（反向场景），则需 P2-T3 修复
  // 此测试确保基本的跨页高亮场景工作
  assert.ok(indexes.length > 0, "cross-page highlight should find page-local match");
});
