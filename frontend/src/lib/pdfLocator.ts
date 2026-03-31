export type PdfLocationStatus = "idle" | "highlighted" | "page_only" | "error";

export type BboxOverlayStyle = {
  left: string;
  top: string;
  width: string;
  height: string;
};

export function bboxToOverlayStyle(
  bbox: number[] | null | undefined
): BboxOverlayStyle | null {
  if (!Array.isArray(bbox) || bbox.length !== 4) {
    return null;
  }
  if (!bbox.every((v) => Number.isFinite(v))) {
    return null;
  }

  const [x0, y0, x1, y1] = bbox;
  const left = Math.max(0, Math.min(x0, x1)) / 1000;
  const top = Math.max(0, Math.min(y0, y1)) / 1000;
  const right = Math.min(1000, Math.max(x0, x1)) / 1000;
  const bottom = Math.min(1000, Math.max(y0, y1)) / 1000;

  return {
    left: `${(left * 100).toFixed()}%`,
    top: `${(top * 100).toFixed()}%`,
    width: `${((right - left) * 100).toFixed()}%`,
    height: `${((bottom - top) * 100).toFixed()}%`,
  };
}

type PdfLocationResolutionInput = {
  locatorText: string;
  matchedTextItems: string[];
  hasError?: boolean;
};

type PdfHighlightMatchInput = {
  textItems: string[];
  highlightText: string;
  locatorText?: string;
};

export type PdfHighlightMatch = {
  itemIndexes: number[];
  status: PdfLocationStatus;
};

const SEARCHABLE_TOKEN_PATTERN = /[\p{L}\p{N}]/u;

export function hasUsablePdfBbox(
  bbox: number[] | null | undefined
): bbox is [number, number, number, number] {
  return (
    Array.isArray(bbox) &&
    bbox.length === 4 &&
    bbox.every((value) => Number.isFinite(value))
  );
}

export function normalizePdfText(value: string): string {
  return value
    .normalize("NFKC")
    .replace(/[\u00ad\u200b-\u200d\u2060]/g, "")
    .replace(/[‐‑‒–—−]+/g, "-")
    .replace(/([\p{L}\p{N}])-\s+([\p{L}\p{N}])/gu, "$1$2")
    .replace(/[\[\]]+/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .toLowerCase();
}

export function clampPdfPage(
  page: number,
  totalPages: number | null | undefined
): number {
  const safePage = Number.isFinite(page) && page >= 1 ? Math.floor(page) : 1;
  if (typeof totalPages !== "number" || !Number.isFinite(totalPages) || totalPages < 1) {
    return safePage;
  }

  return Math.min(safePage, Math.floor(totalPages));
}

export function hasUsableLocatorText(locatorText: string): boolean {
  const normalized = normalizePdfText(locatorText);
  return normalized.length >= 3 && SEARCHABLE_TOKEN_PATTERN.test(normalized);
}

function buildNormalizedTextItemMap(textItems: string[]): {
  text: string;
  ranges: Array<{ index: number; start: number; end: number }>;
} {
  let combined = "";
  const ranges: Array<{ index: number; start: number; end: number }> = [];

  textItems.forEach((item, index) => {
    const normalized = normalizePdfText(item);
    if (!normalized) {
      return;
    }

    const previousRange = ranges.at(-1);
    const canMergeBrokenWord =
      combined.endsWith("-") && SEARCHABLE_TOKEN_PATTERN.test(normalized[0] ?? "");

    if (canMergeBrokenWord) {
      combined = combined.slice(0, -1);
      if (previousRange) {
        previousRange.end = Math.max(previousRange.start, previousRange.end - 1);
      }
    } else if (combined) {
      combined += " ";
    }

    const start = combined.length;
    combined += normalized;
    ranges.push({ index, start, end: combined.length });
  });

  return { text: combined, ranges };
}

function findBestContainedWindow(
  text: string,
  ranges: Array<{ index: number; start: number; end: number }>,
  normalizedHighlight: string
): number[] {
  let bestStart = -1;
  let bestEnd = -1;
  let bestLength = 0;

  for (let startIndex = 0; startIndex < ranges.length; startIndex += 1) {
    for (let endIndex = startIndex; endIndex < ranges.length; endIndex += 1) {
      const candidate = text
        .slice(ranges[startIndex].start, ranges[endIndex].end)
        .trim();
      if (candidate.length <= bestLength || !isStrongHighlightCandidate(candidate)) {
        continue;
      }
      if (!normalizedHighlight.includes(candidate)) {
        continue;
      }
      bestStart = startIndex;
      bestEnd = endIndex;
      bestLength = candidate.length;
    }
  }

  if (bestStart < 0 || bestEnd < 0) {
    return [];
  }

  return ranges.slice(bestStart, bestEnd + 1).map((range) => range.index);
}

function isStrongHighlightCandidate(text: string): boolean {
  const normalized = normalizePdfText(text);
  if (normalized.length < 12) {
    return false;
  }

  const tokens = normalized.split(" ").filter(Boolean);
  if (tokens.length === 1) {
    return normalized.length >= 10;
  }

  return tokens.filter((token) => token.length >= 4).length >= 3;
}

export function canHighlightTextItem(
  textItem: string,
  locatorText: string
): boolean {
  if (!hasUsableLocatorText(locatorText)) {
    return false;
  }

  const normalizedItem = normalizePdfText(textItem);
  const normalizedLocator = normalizePdfText(locatorText);
  const locatorContainsItem = normalizedLocator.includes(normalizedItem);
  const itemContainsLocator = normalizedItem.includes(normalizedLocator);

  if (!locatorContainsItem && !itemContainsLocator) {
    return false;
  }

  const candidate =
    normalizedItem.length <= normalizedLocator.length
      ? normalizedItem
      : normalizedLocator;
  return isStrongHighlightCandidate(candidate);
}

export function findPdfHighlightItemIndexes(
  textItems: string[],
  highlightText: string
): number[] {
  if (!hasUsableLocatorText(highlightText)) {
    return [];
  }

  const normalizedHighlight = normalizePdfText(highlightText);
  const { text, ranges } = buildNormalizedTextItemMap(textItems);
  if (!text) {
    return [];
  }

  const matchStart = text.indexOf(normalizedHighlight);
  if (matchStart >= 0) {
    const matchEnd = matchStart + normalizedHighlight.length;
    return ranges
      .filter((range) => range.end > matchStart && range.start < matchEnd)
      .map((range) => range.index);
  }

  return findBestContainedWindow(text, ranges, normalizedHighlight);
}

export function resolvePdfHighlightMatch({
  textItems,
  highlightText,
  locatorText = ""
}: PdfHighlightMatchInput): PdfHighlightMatch {
  const preferredText = highlightText.trim();
  if (hasUsableLocatorText(preferredText)) {
    const itemIndexes = findPdfHighlightItemIndexes(textItems, preferredText);
    return {
      itemIndexes,
      status: itemIndexes.length > 0 ? "highlighted" : "page_only"
    };
  }

  if (!hasUsableLocatorText(locatorText)) {
    return { itemIndexes: [], status: "page_only" };
  }

  const fallbackIndexes = findPdfHighlightItemIndexes(textItems, locatorText);
  return {
    itemIndexes: fallbackIndexes,
    status: fallbackIndexes.length > 0 ? "highlighted" : "page_only"
  };
}

export function resolvePdfLocationStatus({
  locatorText,
  matchedTextItems,
  hasError = false
}: PdfLocationResolutionInput): PdfLocationStatus {
  if (hasError) {
    return "error";
  }

  if (!hasUsableLocatorText(locatorText)) {
    return "page_only";
  }

  return matchedTextItems.some((item) => canHighlightTextItem(item, locatorText))
    ? "highlighted"
    : "page_only";
}
