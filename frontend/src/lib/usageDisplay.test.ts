import assert from "node:assert/strict";
import test from "node:test";

import {
  formatCostSummary,
  formatUsageSummary,
} from "./usageDisplay.ts";

test("formatUsageSummary prefers total input and output tokens", () => {
  assert.equal(
    formatUsageSummary({
      input_tokens: 12,
      output_tokens: 34,
      total_tokens: 46,
    }),
    "总 46 · 输入 12 · 输出 34",
  );
});

test("formatUsageSummary returns null when usage is missing", () => {
  assert.equal(formatUsageSummary(null), null);
  assert.equal(formatUsageSummary({}), null);
});

test("formatCostSummary shows official CNY total", () => {
  assert.equal(
    formatCostSummary({
      currency: "CNY",
      total: 0.001234,
      items: [{ model: "qwen3.6-flash", cny: 0.001234 }],
      unpriced: [],
    }),
    "¥0.001234",
  );
});

test("formatCostSummary notes unpriced tokens when total is zero", () => {
  assert.equal(
    formatCostSummary({
      currency: "CNY",
      total: 0,
      items: [],
      unpriced: [{ model: "BAAI/bge-m3", input_tokens: 12 }],
    }),
    "部分未定价",
  );
});

test("formatCostSummary returns null without a cost payload", () => {
  assert.equal(formatCostSummary(null), null);
  assert.equal(formatCostSummary({ currency: "CNY" }), null);
});
