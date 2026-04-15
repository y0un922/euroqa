import type { ReferenceRecord } from "./types";

export type InlineReferenceAnchor = {
  badge: string;
  tone: "matched" | "unmatched";
  tooltip: string;
  ariaLabel: string;
};

function buildUnmatchedBadge(label: string): string {
  // [Ref-N] 格式：LLM 引用了不存在的编号
  if (/^Ref-\d+$/i.test(label)) {
    return "?";
  }

  // 兜底：尝试从自由文本中提取条款号
  const segments = label
    .split("·")
    .map((segment) => segment.trim())
    .filter(Boolean);
  const clauseSegment = segments.find(
    (segment) =>
      /\d/.test(segment) &&
      !/^en\s*199\d/i.test(segment) &&
      !/^p\.?/i.test(segment)
  );

  if (!clauseSegment) {
    return "?";
  }

  const normalizedClause = clauseSegment
    .replace(/\s+NOTE\d*$/i, "")
    .replace(/\(\d+\)(?:[a-z])?$/i, "");

  return normalizedClause || "?";
}

export function getReferenceOrdinal(
  referenceId: string | null | undefined,
  references: ReferenceRecord[]
): number | null {
  if (!referenceId) {
    return null;
  }

  const index = references.findIndex((reference) => reference.id === referenceId);
  return index >= 0 ? index + 1 : null;
}

export function buildInlineReferenceAnchor(
  label: string,
  referenceId: string | null,
  references: ReferenceRecord[]
): InlineReferenceAnchor {
  const ordinal = getReferenceOrdinal(referenceId, references);
  if (ordinal) {
    const reference = references[ordinal - 1];
    const sourceLabel = `${reference.source.file} · ${reference.source.clause}`;
    return {
      badge: String(ordinal),
      tone: "matched",
      tooltip: `引用 ${ordinal} · ${sourceLabel}`,
      ariaLabel: `查看引用 ${ordinal}：${reference.source.file} ${reference.source.clause}`
    };
  }

  const normalizedLabel = label.trim() || "未命名引用";
  return {
    badge: buildUnmatchedBadge(normalizedLabel),
    tone: "unmatched",
    tooltip: `未命中引用 · ${normalizedLabel}`,
    ariaLabel: `未命中引用：${normalizedLabel}`
  };
}
