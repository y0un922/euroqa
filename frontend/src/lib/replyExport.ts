import type { ChatTurn, RetrievalContext, RetrievalContextItem, Source } from "./types";

type ExportMetadata = {
  conversationId?: string | null;
  exportedAt?: string;
};

type ClipboardLike = Pick<Clipboard, "writeText">;

type DownloadAnchor = {
  href: string;
  download: string;
  click: () => void;
};

type DownloadDeps = {
  createObjectURL: (blob: Blob) => string;
  revokeObjectURL: (url: string) => void;
  createAnchor: () => DownloadAnchor;
};

function buildHeading(level: number, title: string): string {
  return `${"#".repeat(level)} ${title}`;
}

function buildSection(level: number, title: string, content: string): string {
  return [buildHeading(level, title), "", content.trim() || "> No data recorded."].join("\n");
}

function buildMetadataLines(metadata: ExportMetadata): string {
  const lines: string[] = [];

  if (metadata.exportedAt) {
    lines.push(`- Exported At: ${metadata.exportedAt}`);
  }

  if (metadata.conversationId) {
    lines.push(`- Conversation ID: ${metadata.conversationId}`);
  }

  return lines.join("\n");
}

function formatBulletList(items: string[], emptyLabel: string): string {
  if (items.length === 0) {
    return `> ${emptyLabel}`;
  }

  return items.map((item) => `- ${item}`).join("\n");
}

function formatTextBlock(text: string, emptyLabel: string): string {
  const normalized = text.trim();
  if (!normalized) {
    return `> ${emptyLabel}`;
  }

  return ["```text", normalized, "```"].join("\n");
}

function formatSource(source: Source, index: number): string {
  const lines = [
    buildHeading(3, `Source ${index + 1}`),
    "",
    `- File: ${source.file}`,
    `- Document ID: ${source.document_id?.trim() || "-"}`,
    `- Title: ${source.title || "-"}`,
    `- Section: ${source.section || "-"}`,
    `- Page: ${String(source.page || "-")}`,
    `- Clause: ${source.clause || "-"}`,
    "- Original Text:",
    formatTextBlock(source.original_text, "No source text recorded.")
  ];

  const translation = source.translation?.trim();
  if (translation) {
    lines.push("- Translation:");
    lines.push(translation);
  }

  return lines.join("\n");
}

function formatSources(sources: Source[]): string {
  if (sources.length === 0) {
    return "> No citation sources recorded.";
  }

  return sources.map((source, index) => formatSource(source, index)).join("\n\n");
}

function formatRetrievalContextItem(item: RetrievalContextItem, index: number): string {
  const lines = [
    buildHeading(4, `Chunk ${index + 1}`),
    "",
    `- File: ${item.file}`,
    `- Document ID: ${item.document_id || "-"}`,
    `- Title: ${item.title || "-"}`,
    `- Section: ${item.section || "-"}`,
    `- Page: ${String(item.page || "-")}`,
    `- Clause: ${item.clause || "-"}`,
  ];

  if (typeof item.score === "number") {
    lines.push(`- Score: ${item.score.toFixed(4)}`);
  }

  lines.push("- Content:");
  lines.push(formatTextBlock(item.content, "No retrieval content recorded."));
  return lines.join("\n");
}

function formatRetrievalContextGroup(
  title: string,
  items: RetrievalContextItem[]
): string {
  return [
    buildHeading(3, title),
    "",
    items.length === 0
      ? "> No entries recorded."
      : items.map((item, index) => formatRetrievalContextItem(item, index)).join("\n\n")
  ].join("\n");
}

function formatRetrievalContext(context: RetrievalContext | null | undefined): string {
  if (!context || (context.chunks.length === 0 && context.parent_chunks.length === 0)) {
    return "> No retrieval context recorded.";
  }

  return [
    formatRetrievalContextGroup("Retrieved Chunks", context.chunks),
    "",
    formatRetrievalContextGroup("Parent Chunks", context.parent_chunks)
  ].join("\n");
}

function buildTurnSections(turn: ChatTurn, sectionLevel: number): string {
  return [
    buildSection(
      sectionLevel,
      "User Question",
      turn.question.trim() || "> No question recorded."
    ),
    "",
    buildSection(
      sectionLevel,
      "Answer Markdown",
      turn.answer.trim() || "> No answer markdown recorded."
    ),
    "",
    buildSection(sectionLevel, "Citation Sources", formatSources(turn.sources)),
    "",
    buildSection(
      sectionLevel,
      "Related References",
      formatBulletList(turn.relatedRefs, "No related references recorded.")
    ),
    "",
    buildSection(
      sectionLevel,
      "Retrieval Context",
      formatRetrievalContext(turn.retrievalContext)
    )
  ].join("\n");
}

function buildConversationTurnSections(
  turn: ChatTurn,
  sectionLevel: number
): string {
  return [
    buildSection(
      sectionLevel,
      "User Question",
      turn.question.trim() || "> No question recorded."
    ),
    "",
    buildSection(
      sectionLevel,
      "Answer Markdown",
      turn.answer.trim() || "> No answer markdown recorded."
    )
  ].join("\n");
}

export function isChatTurnExportable(turn: ChatTurn): boolean {
  const hasRetrievalContext = Boolean(
    turn.retrievalContext &&
      (turn.retrievalContext.chunks.length > 0 ||
        turn.retrievalContext.parent_chunks.length > 0)
  );

  return (
    turn.status === "done" &&
    Boolean(
      turn.answer.trim() ||
        turn.sources.length > 0 ||
        turn.relatedRefs.length > 0 ||
        hasRetrievalContext
    )
  );
}

export function buildReplyMarkdown(
  turn: ChatTurn,
  metadata: ExportMetadata = {}
): string {
  if (!isChatTurnExportable(turn)) {
    throw new Error("Only completed replies can be exported.");
  }

  const effectiveMetadata = {
    conversationId: metadata.conversationId ?? turn.conversationId ?? null,
    exportedAt: metadata.exportedAt
  };
  const metadataLines = buildMetadataLines(effectiveMetadata);

  return [
    buildHeading(1, "Euro_QA Reply Export"),
    "",
    metadataLines,
    metadataLines ? "" : undefined,
    buildTurnSections(turn, 2)
  ]
    .filter((part): part is string => typeof part === "string")
    .join("\n");
}

export function buildConversationMarkdown(
  messages: ChatTurn[],
  metadata: ExportMetadata = {}
): string {
  const exportableTurns = messages.filter(isChatTurnExportable);
  const metadataLines = buildMetadataLines(metadata);

  const turnSections =
    exportableTurns.length === 0
      ? ["> No completed replies are available for export."]
      : exportableTurns.map((turn, index) =>
          [
            buildHeading(2, `Turn ${index + 1}`),
            "",
            buildConversationTurnSections(turn, 3)
          ].join("\n")
        );

  return [
    buildHeading(1, "Euro_QA Conversation Export"),
    "",
    metadataLines,
    metadataLines ? "" : undefined,
    ...turnSections
  ]
    .filter((part): part is string => typeof part === "string")
    .join("\n");
}

export function buildConversationExportFilename(
  conversationId?: string | null,
  exportedAt?: string
): string {
  const sanitizedId = (conversationId || "session").replace(/[^a-zA-Z0-9_-]+/g, "-");
  const sanitizedTimestamp = (exportedAt || "exported")
    .replace(/:/g, "-")
    .replace(/\.\d+Z$/, "Z");

  return `euro-qa-conversation-${sanitizedId}-${sanitizedTimestamp}.md`;
}

function copyMarkdownWithTextarea(markdown: string): boolean {
  if (typeof document === "undefined" || typeof document.execCommand !== "function") {
    return false;
  }

  const textarea = document.createElement("textarea");
  textarea.value = markdown;
  textarea.setAttribute("readonly", "");
  textarea.style.position = "fixed";
  textarea.style.top = "-1000px";
  textarea.style.left = "-1000px";
  textarea.style.opacity = "0";
  document.body.appendChild(textarea);
  textarea.focus();
  textarea.select();

  try {
    return document.execCommand("copy");
  } finally {
    document.body.removeChild(textarea);
  }
}

export async function copyMarkdownToClipboard(
  markdown: string,
  clipboard: ClipboardLike | null = globalThis.navigator?.clipboard ?? null
): Promise<void> {
  if (!markdown.trim()) {
    throw new Error("Nothing to copy.");
  }

  if (clipboard?.writeText) {
    try {
      await clipboard.writeText(markdown);
      return;
    } catch (error) {
      if (copyMarkdownWithTextarea(markdown)) {
        return;
      }
      throw error;
    }
  }

  if (copyMarkdownWithTextarea(markdown)) {
    return;
  }

  throw new Error("Clipboard API is unavailable.");
}

export function downloadMarkdownFile(
  filename: string,
  markdown: string,
  deps: DownloadDeps = {
    createObjectURL: (blob) => URL.createObjectURL(blob),
    revokeObjectURL: (url) => URL.revokeObjectURL(url),
    createAnchor: () => document.createElement("a")
  }
): void {
  if (!markdown.trim()) {
    throw new Error("Nothing to download.");
  }

  const blob = new Blob([markdown], { type: "text/markdown;charset=utf-8" });
  const objectUrl = deps.createObjectURL(blob);
  const anchor = deps.createAnchor();

  anchor.href = objectUrl;
  anchor.download = filename;
  anchor.click();
  deps.revokeObjectURL(objectUrl);
}
