import assert from "node:assert/strict";
import test from "node:test";

import {
  getPdfNavigationState,
  resolvePdfPageState,
  stepPdfPage,
  syncRequestedPdfPage
} from "./pdfViewerPage.ts";

test("syncRequestedPdfPage clamps requested page into document bounds", () => {
  assert.equal(syncRequestedPdfPage(83, 12, 225), 83);
  assert.equal(syncRequestedPdfPage(999, 12, 225), 225);
  assert.equal(syncRequestedPdfPage(0, 12, 225), 1);
});

test("syncRequestedPdfPage keeps requested page when total pages are not known yet", () => {
  assert.equal(syncRequestedPdfPage(83, 12, null), 83);
});

test("stepPdfPage respects prev/next bounds", () => {
  assert.equal(stepPdfPage(1, "prev", 225), 1);
  assert.equal(stepPdfPage(1, "next", 225), 2);
  assert.equal(stepPdfPage(225, "next", 225), 225);
  assert.equal(stepPdfPage(225, "prev", 225), 224);
});

test("resolvePdfPageState keeps displayed page input in sync with navigation", () => {
  assert.deepEqual(resolvePdfPageState(84, 83, 225), {
    currentPage: 84,
    pageInput: "84",
  });
  assert.deepEqual(resolvePdfPageState(999, 83, 225), {
    currentPage: 225,
    pageInput: "225",
  });
});

test("getPdfNavigationState reports whether prev/next buttons should be enabled", () => {
  assert.deepEqual(getPdfNavigationState(1, 225), {
    canGoPrev: false,
    canGoNext: true,
  });
  assert.deepEqual(getPdfNavigationState(225, 225), {
    canGoPrev: true,
    canGoNext: false,
  });
});
