import type { ReferenceRecord } from "./types";

export const REFERENCE_LINK_PREFIX = "reference://";
export const UNMATCHED_CITATION_PREFIX = "citation://";

/**
 * 匹配 LLM 输出中的 [Ref-N] 引用标记。
 * 全局匹配，每次调用前自动重置 lastIndex。
 */
const REF_CITATION_PATTERN = /\[Ref-(\d+)\]/g;

/**
 * 将 Markdown 中的 [Ref-N] 标记转换为可点击的引用链接。
 * N 直接对应 references 数组的 1-based 索引。
 */
export function linkifyReferenceCitations(
  markdown: string,
  references: ReferenceRecord[]
): string {
  if (!markdown.trim()) {
    return markdown;
  }

  return markdown.replace(REF_CITATION_PATTERN, (full, indexStr) => {
    const index = Number(indexStr);
    const reference = references[index - 1];

    if (!reference) {
      // LLM 引用了不存在的编号，标记为 unmatched
      const label = `Ref-${indexStr}`;
      return `[${label}](${UNMATCHED_CITATION_PREFIX}${encodeURIComponent(label)})`;
    }

    return `[${full}](${REFERENCE_LINK_PREFIX}${reference.id})`;
  });
}

export function getReferenceIdFromHref(href?: string | null): string | null {
  if (!href?.startsWith(REFERENCE_LINK_PREFIX)) {
    return null;
  }

  return href.slice(REFERENCE_LINK_PREFIX.length) || null;
}

/**
 * 提取 Eurocode 标准标识符的核心部分（如 "EN 1990"、"EN 1991-2"）。
 * 返回小写的标准号用于比较，去除年份后缀。
 */
function extractStandardId(value: string): string | null {
  // 匹配 EN + 4位基础号 + 可选的 part 号（仅连字符分隔：-N 或 -N-N）
  const match = value.match(/EN\s*(\d{4})(?:-(\d{1,2})(?:-(\d{1,2}))?)?/i);
  if (!match) {
    return null;
  }

  let id = `en${match[1]}`;
  if (match[2]) {
    id += `-${match[2]}`;
  }
  if (match[3]) {
    id += `-${match[3]}`;
  }
  return id;
}

/**
 * 将 relatedRef 字符串（如 "EN 1991-2"、"Annex C"）匹配到已有的 references 中。
 * 返回第一个标准号匹配的 reference，或 null。
 */
export function matchRelatedRefToReference(
  relatedRef: string,
  references: ReferenceRecord[]
): ReferenceRecord | null {
  const refId = extractStandardId(relatedRef);
  if (!refId) {
    return null;
  }

  // 精确匹配标准号（忽略年份后缀如 ":2002"）
  return references.find((r) => {
    const sourceId = extractStandardId(r.source.file);
    return sourceId !== null && sourceId === refId;
  }) ?? null;
}

export function getUnmatchedCitationLabelFromHref(
  href?: string | null
): string | null {
  if (!href?.startsWith(UNMATCHED_CITATION_PREFIX)) {
    return null;
  }

  const encoded = href.slice(UNMATCHED_CITATION_PREFIX.length);
  return encoded ? decodeURIComponent(encoded) : null;
}
