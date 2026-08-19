export type UsageCounters = Record<string, number> | null | undefined;

function asRecord(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null
    ? (value as Record<string, unknown>)
    : null;
}

function asFiniteNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

export function formatUsageSummary(usage: UsageCounters): string | null {
  if (!usage) {
    return null;
  }

  const totalTokens = usage.total_tokens ?? usage.totalTokens;
  const inputTokens = usage.input_tokens ?? usage.prompt_tokens;
  const outputTokens = usage.output_tokens ?? usage.completion_tokens;
  const parts: string[] = [];

  if (typeof totalTokens === "number") {
    parts.push(`总 ${totalTokens}`);
  }
  if (typeof inputTokens === "number") {
    parts.push(`输入 ${inputTokens}`);
  }
  if (typeof outputTokens === "number") {
    parts.push(`输出 ${outputTokens}`);
  }

  return parts.length > 0 ? parts.join(" · ") : null;
}

export function formatCostSummary(cost: unknown): string | null {
  const payload = asRecord(cost);
  if (!payload) {
    return null;
  }

  const total = asFiniteNumber(payload.total);
  const unpriced = Array.isArray(payload.unpriced) ? payload.unpriced : [];
  if (total !== null && total > 0) {
    return `¥${formatYuan(total)}`;
  }
  if (unpriced.length > 0) {
    return "部分未定价";
  }
  return null;
}

function formatYuan(value: number): string {
  if (value >= 1) {
    return value.toFixed(2);
  }
  if (value >= 0.01) {
    return value.toFixed(4);
  }
  return value.toFixed(6).replace(/0+$/, "").replace(/\.$/, "");
}
