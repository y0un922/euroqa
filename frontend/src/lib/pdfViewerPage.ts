export function syncRequestedPdfPage(
  requestedPage: number,
  _currentPage: number,
  totalPages: number | null
): number {
  const safePage = Number.isFinite(requestedPage) && requestedPage >= 1
    ? Math.floor(requestedPage)
    : 1;

  if (typeof totalPages !== "number" || !Number.isFinite(totalPages) || totalPages < 1) {
    return safePage;
  }

  return Math.min(safePage, Math.floor(totalPages));
}

export function resolvePdfPageState(
  requestedPage: number,
  currentPage: number,
  totalPages: number | null
): {
  currentPage: number;
  pageInput: string;
} {
  const nextPage = syncRequestedPdfPage(requestedPage, currentPage, totalPages);
  return {
    currentPage: nextPage,
    pageInput: String(nextPage),
  };
}

export function stepPdfPage(
  currentPage: number,
  direction: "prev" | "next",
  totalPages: number | null
): number {
  const delta = direction === "prev" ? -1 : 1;
  return syncRequestedPdfPage(currentPage + delta, currentPage, totalPages);
}

export function getPdfNavigationState(
  currentPage: number,
  totalPages: number | null
): {
  canGoPrev: boolean;
  canGoNext: boolean;
} {
  return {
    canGoPrev: currentPage > 1,
    canGoNext:
      typeof totalPages === "number" && Number.isFinite(totalPages)
        ? currentPage < totalPages
        : true,
  };
}
