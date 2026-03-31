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
