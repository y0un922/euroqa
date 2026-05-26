import assert from "node:assert/strict";
import test from "node:test";

import {
  getReferenceIdFromHref,
  getUnmatchedCitationLabelFromHref,
  linkifyReferenceCitations,
  matchRelatedRefToReference,
  REFERENCE_LINK_PREFIX,
  UNMATCHED_CITATION_PREFIX
} from "./citations.ts";
import type { ReferenceRecord } from "./types.ts";

const references: ReferenceRecord[] = [
  {
    id: "m1-ref-1",
    displayTitle: "Eurocode - Basis of structural design",
    source: {
      file: "EN 1990:2002",
      display_title: "Eurocode - Basis of structural design",
      title: "Basis",
      section: "2.3",
      page: "28",
      clause: "2.3(1)",
      original_text: "",
      translation: ""
    },
    documentId: "EN1990_2002",
    confidence: "high",
    relatedRefs: []
  },
  {
    id: "m1-ref-2",
    displayTitle: "Eurocode 2: Design of concrete structures",
    source: {
      file: "EN 1992-1-1:2004",
      display_title: "Eurocode 2: Design of concrete structures",
      title: "Concrete",
      section: "3.1",
      page: "45",
      clause: "3.1.2(3)",
      original_text: "",
      translation: ""
    },
    documentId: "EN1992_1_1_2004",
    confidence: "high",
    relatedRefs: []
  }
];

// --- linkifyReferenceCitations ---

test("linkifyReferenceCitations turns [Ref-N] into reference links", () => {
  const markdown = "根据 [Ref-1] 的规定，设计使用年限应予规定。";
  const result = linkifyReferenceCitations(markdown, references);

  assert.equal(
    result,
    "根据 [[Ref-1]](reference://m1-ref-1) 的规定，设计使用年限应予规定。"
  );
});

test("linkifyReferenceCitations maps multiple references correctly", () => {
  const markdown = "[Ref-1] 和 [Ref-2] 均有说明。";
  const result = linkifyReferenceCitations(markdown, references);

  assert.equal(
    result,
    "[[Ref-1]](reference://m1-ref-1) 和 [[Ref-2]](reference://m1-ref-2) 均有说明。"
  );
});

test("linkifyReferenceCitations expands grouped ref markers", () => {
  const markdown = "搭接长度取值见 [Ref-1, Ref-2]。";
  const result = linkifyReferenceCitations(markdown, references);

  assert.equal(
    result,
    "搭接长度取值见 [[Ref-1]](reference://m1-ref-1), [[Ref-2]](reference://m1-ref-2)。"
  );
});

test("linkifyReferenceCitations renders parent markers as unmatched citations", () => {
  const markdown = "国家附录差异需结合 [Ref-1, Parent-3] 判断。";
  const result = linkifyReferenceCitations(markdown, references);

  assert.equal(
    result,
    "国家附录差异需结合 [[Ref-1]](reference://m1-ref-1), [Parent-3](citation://Parent-3) 判断。"
  );
});

test("linkifyReferenceCitations renders standalone parent markers", () => {
  const markdown = "适用范围见 [Parent-2]。";
  const result = linkifyReferenceCitations(markdown, references);

  assert.equal(result, "适用范围见 [Parent-2](citation://Parent-2)。");
});

test("linkifyReferenceCitations normalizes uppercase ref markers", () => {
  const markdown = "DG 证据也通过 [REF-2] 统一引用。";
  const result = linkifyReferenceCitations(markdown, references);

  assert.equal(
    result,
    "DG 证据也通过 [[Ref-2]](reference://m1-ref-2) 统一引用。"
  );
});

test("linkifyReferenceCitations does not create guide-specific links", () => {
  const markdown = "旧格式 [Guide-1] 只作为普通文本保留。";
  const result = linkifyReferenceCitations(markdown, references);

  assert.equal(result, markdown);
});

test("linkifyReferenceCitations marks out-of-range index as unmatched", () => {
  const markdown = "参见 [Ref-99] 的详细说明。";
  const result = linkifyReferenceCitations(markdown, references);

  assert.equal(
    result,
    "参见 [Ref-99](citation://Ref-99) 的详细说明。"
  );
});

test("linkifyReferenceCitations preserves normal markdown links", () => {
  const markdown =
    "参考 [Eurocode 官网](https://eurocodes.jrc.ec.europa.eu/) 与 [Ref-1]。";
  const result = linkifyReferenceCitations(markdown, references);

  assert.match(result, /\[Eurocode 官网\]\(https:\/\/eurocodes\.jrc\.ec\.europa\.eu\/\)/);
  assert.match(result, /\[\[Ref-1\]\]\(reference:\/\/m1-ref-1\)/);
});

test("linkifyReferenceCitations does not match numbered steps or plain brackets", () => {
  const markdown = "Step [1]: 首先确定材料设计值。\n[2] 再计算受压区高度。";
  const result = linkifyReferenceCitations(markdown, references);

  // [1] 和 [2] 不应被替换（不是 [Ref-N] 格式）
  assert.equal(result, markdown);
});

test("linkifyReferenceCitations handles repeated citations to the same reference", () => {
  const markdown = "根据 [Ref-1]，以及再次引用 [Ref-1]。";
  const result = linkifyReferenceCitations(markdown, references);

  assert.equal(
    result,
    "根据 [[Ref-1]](reference://m1-ref-1)，以及再次引用 [[Ref-1]](reference://m1-ref-1)。"
  );
});

test("linkifyReferenceCitations returns empty string for whitespace-only input", () => {
  assert.equal(linkifyReferenceCitations("  \n  ", references), "  \n  ");
});

test("linkifyReferenceCitations leaves text without [Ref-N] unchanged", () => {
  const markdown = "这是一段没有引用的普通文本。";
  const result = linkifyReferenceCitations(markdown, references);

  assert.equal(result, markdown);
});

// --- getReferenceIdFromHref ---

test("getReferenceIdFromHref extracts internal reference ids", () => {
  assert.equal(
    getReferenceIdFromHref(`${REFERENCE_LINK_PREFIX}m1-ref-1`),
    "m1-ref-1"
  );
  assert.equal(getReferenceIdFromHref("https://example.com"), null);
  assert.equal(getReferenceIdFromHref(null), null);
  assert.equal(getReferenceIdFromHref(undefined), null);
});

// --- getUnmatchedCitationLabelFromHref ---

test("getUnmatchedCitationLabelFromHref extracts unmatched citation labels", () => {
  assert.equal(
    getUnmatchedCitationLabelFromHref(
      `${UNMATCHED_CITATION_PREFIX}Ref-99`
    ),
    "Ref-99"
  );
  assert.equal(getUnmatchedCitationLabelFromHref("https://example.com"), null);
  assert.equal(getUnmatchedCitationLabelFromHref(null), null);
});

// --- matchRelatedRefToReference ---

test("matchRelatedRefToReference matches related standard ids", () => {
  const matched = matchRelatedRefToReference("EN 1990:2002", references);
  assert.equal(matched?.id, "m1-ref-1");
});

test("matchRelatedRefToReference returns null for non-matching standards", () => {
  const matched = matchRelatedRefToReference("EN 1991-2", references);
  assert.equal(matched, null);
});

test("matchRelatedRefToReference returns null for non-standard strings", () => {
  const matched = matchRelatedRefToReference("Annex C", references);
  assert.equal(matched, null);
});
