import {
  Check,
  ChevronDown,
  Copy,
  CornerDownLeft,
  FileText,
  LoaderCircle,
  RotateCcw,
  Search,
  Sparkles,
  Square
} from "lucide-react";
import { motion } from "motion/react";
import { Component, type ReactNode, useMemo, useState } from "react";
import ReactMarkdown from "react-markdown";
import type { Components } from "react-markdown";

import { buildReferenceRecords, type DemoDocumentInfo } from "../lib/api";
import {
  getUnmatchedCitationLabelFromHref,
  getReferenceIdFromHref,
  linkifyReferenceCitations,
  matchRelatedRefToReference
} from "../lib/citations";
import {
  buildInlineReferenceAnchor,
  getReferenceOrdinal
} from "../lib/inlineReferences";
import {
  markdownRehypePlugins,
  markdownRemarkPlugins,
  markdownUrlTransform
} from "../lib/markdown";
import {
  copyMarkdownToClipboard,
  isChatTurnExportable
} from "../lib/replyExport";
import type { ChatTurn, QueryProgressEvent } from "../lib/types";

type MainWorkspaceProps = {
  activeReferenceId: string | null;
  apiState: "loading" | "ready" | "degraded";
  bootError: string | null;
  documents: DemoDocumentInfo[];
  draftQuestion: string;
  hotQuestions: string[];
  isSubmitting: boolean;
  messages: ChatTurn[];
  onDraftQuestionChange: (value: string) => void;
  onReferenceClick: (referenceId: string | null) => void;
  onRegenerateAnswer?: (messageId: string) => void;
  onSelectHotQuestion: (question: string) => void;
  onStop?: () => void;
  onSubmit: () => void;
};

type MarkdownRenderBoundaryProps = {
  children: ReactNode;
  content: string;
};

type MarkdownRenderBoundaryState = {
  hasError: boolean;
};

class MarkdownRenderBoundary extends Component<
  MarkdownRenderBoundaryProps,
  MarkdownRenderBoundaryState
> {
  state: MarkdownRenderBoundaryState = { hasError: false };

  static getDerivedStateFromError(): MarkdownRenderBoundaryState {
    return { hasError: true };
  }

  componentDidUpdate(prevProps: MarkdownRenderBoundaryProps) {
    if (prevProps.content !== this.props.content && this.state.hasError) {
      this.setState({ hasError: false });
    }
  }

  render() {
    if (this.state.hasError) {
      return (
        <pre className="whitespace-pre-wrap rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 font-sans text-[15px] leading-relaxed text-stone-800">
          {this.props.content}
        </pre>
      );
    }

    return this.props.children;
  }
}

/**
 * 如果 answer 是 LLM 输出的 JSON（旧非流式路径 fallback），
 * 尝试提取 .answer 字段；否则原样返回。
 */
function extractDisplayAnswer(answer: string): string {
  const trimmed = answer.trim();
  if (!trimmed) return answer;

  const candidate = trimmed.startsWith("```json")
    ? trimmed.replace(/^```json\s*/, "").replace(/\s*```$/, "")
    : trimmed;

  if (!candidate.startsWith("{")) return answer;

  try {
    const parsed = JSON.parse(candidate) as { answer?: unknown };
    return typeof parsed.answer === "string" && parsed.answer.trim()
      ? parsed.answer
      : answer;
  } catch {
    return answer;
  }
}

function getCitationText(children: ReactNode): string {
  if (typeof children === "string") {
    return children;
  }

  if (Array.isArray(children)) {
    return children.map((child) => getCitationText(child)).join("");
  }

  return String(children ?? "");
}

/** Tailwind 内联样式——替代 @tailwindcss/typography 的 prose 类 */
const markdownClassName = [
  "max-w-none text-[15px] leading-7 text-stone-800",
  "[&_h1]:mb-4 [&_h1]:font-serif [&_h1]:text-2xl [&_h1]:text-stone-900",
  "[&_h2]:mb-3 [&_h2]:mt-8 [&_h2]:text-xl [&_h2]:font-semibold [&_h2]:text-stone-900",
  "[&_h3]:mb-3 [&_h3]:mt-6 [&_h3]:text-lg [&_h3]:font-semibold [&_h3]:text-stone-900",
  "[&_p]:mb-4 [&_p:last-child]:mb-0",
  "[&_ul]:mb-4 [&_ul]:list-disc [&_ul]:pl-5",
  "[&_ol]:mb-4 [&_ol]:list-decimal [&_ol]:pl-5",
  "[&_li]:mb-1.5",
  "[&_strong]:font-semibold [&_strong]:text-stone-900",
  "[&_blockquote]:mb-4 [&_blockquote]:border-l-2 [&_blockquote]:border-cyan-200 [&_blockquote]:bg-cyan-50/50 [&_blockquote]:py-1 [&_blockquote]:pl-4",
  "[&_code]:rounded [&_code]:bg-stone-100 [&_code]:px-1.5 [&_code]:py-0.5 [&_code]:font-mono [&_code]:text-[13px]",
  "[&_pre]:mb-4 [&_pre]:overflow-x-auto [&_pre]:rounded-xl [&_pre]:bg-stone-900 [&_pre]:p-4 [&_pre_code]:bg-transparent [&_pre_code]:p-0 [&_pre_code]:text-stone-100",
  "[&_table]:mb-4 [&_table]:w-full [&_table]:border-collapse [&_table]:text-sm",
  "[&_th]:border [&_th]:border-stone-200 [&_th]:bg-stone-100 [&_th]:px-3 [&_th]:py-2 [&_th]:text-left [&_th]:font-semibold",
  "[&_td]:border [&_td]:border-stone-200 [&_td]:px-3 [&_td]:py-2 [&_td]:align-top",
  "[&_.katex-display]:my-4 [&_.katex-display]:overflow-x-auto [&_.katex]:text-[1.02em]",
].join(" ");

type ToolCallStatus = "running" | "completed" | "skipped";

type ToolCallCard = {
  id: string;
  tool: string;
  title: string;
  status: ToolCallStatus;
  summary: string;
  input: Record<string, unknown>;
  result: Record<string, unknown> | string;
};

function compactRecord(record: Record<string, unknown>): Record<string, unknown> {
  return Object.fromEntries(
    Object.entries(record).filter(([, value]) => {
      if (value === null || value === undefined || value === "") {
        return false;
      }
      return !Array.isArray(value) || value.length > 0;
    })
  );
}

function renderJson(value: Record<string, unknown> | string): string {
  return typeof value === "string" ? value : JSON.stringify(value, null, 2);
}

function resolveProgressStatus(
  event: QueryProgressEvent,
  messageStatus: ChatTurn["status"]
): ToolCallStatus {
  if (
    messageStatus === "done" &&
    (event.stage === "generating" ||
      event.stage === "composing" ||
      event.stage === "chat")
  ) {
    return "completed";
  }
  return event.status;
}

function mergeToolStatus(
  current: ToolCallStatus | undefined,
  next: ToolCallStatus
): ToolCallStatus {
  if (current === "running" || next === "running") {
    return "running";
  }
  if (current === "completed" || next === "completed") {
    return "completed";
  }
  return "skipped";
}

function getToolDefinition(event: QueryProgressEvent) {
  if (event.stage.startsWith("tool:")) {
    const factsToolName =
      typeof event.facts?.tool_name === "string" ? event.facts.tool_name : "";
    const toolName = factsToolName || event.stage.slice("tool:".length);
    return {
      id: `tool:${toolName}`,
      tool: toolName,
      title: event.title || "调用外部工具"
    };
  }

  return null;
}

function buildToolInput(
  events: QueryProgressEvent[]
): Record<string, unknown> {
  const latestFacts = [...events].reverse().find((event) => event.facts?.tool_args)
    ?.facts;
  return compactRecord(latestFacts?.tool_args ?? {});
}

function buildToolResult(
  events: QueryProgressEvent[]
): Record<string, unknown> | string {
  const facts = [...events].reverse().find(
    (event) => event.facts?.tool_result || event.facts?.tool_trace
  )?.facts;

  if (!facts) {
    return "工具尚未返回结果。";
  }

  return compactRecord({
    output: facts.tool_result,
    trace: facts.tool_trace
  });
}

function buildToolCallCards(message: ChatTurn): ToolCallCard[] {
  const grouped = new Map<
    string,
    {
      tool: string;
      title: string;
      status?: ToolCallStatus;
      events: QueryProgressEvent[];
    }
  >();

  for (const event of message.progressEvents ?? []) {
    const definition = getToolDefinition(event);
    if (!definition) {
      continue;
    }
    const current =
      grouped.get(definition.id) ?? {
        tool: definition.tool,
        title: definition.title,
        events: []
      };
    current.status = mergeToolStatus(
      current.status,
      resolveProgressStatus(event, message.status)
    );
    current.events.push(event);
    grouped.set(definition.id, current);
  }

  const cards: ToolCallCard[] = Array.from(grouped.entries()).map(([id, item]) => ({
    id,
    tool: item.tool,
    title: item.title,
    status: item.status ?? "completed",
    summary:
      item.events.at(-1)?.summary ||
      item.events.at(-1)?.title ||
      "工具调用已记录。",
    input: buildToolInput(item.events),
    result: buildToolResult(item.events)
  }));

  return cards;
}

function ToolCallTimeline({ message }: { message: ChatTurn }) {
  const cards = buildToolCallCards(message);
  if (cards.length === 0) {
    return null;
  }

  return (
    <div className="space-y-3">
      {cards.map((card) => (
        <details
          className="group overflow-hidden rounded-lg border border-stone-200 bg-white shadow-sm"
          key={card.id}
        >
          <summary className="flex cursor-pointer list-none items-center justify-between gap-4 px-4 py-3 [&::-webkit-details-marker]:hidden">
            <div className="flex min-w-0 items-center gap-3">
              <span className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-stone-900 text-[12px] font-semibold text-white">
                AI
              </span>
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="rounded bg-stone-100 px-2 py-1 font-mono text-[11px] font-semibold uppercase tracking-wide text-stone-500">
                    TOOL
                  </span>
                  <span className="font-mono text-sm font-semibold text-stone-800">
                    {card.tool}
                  </span>
                  {card.status === "running" ? (
                    <LoaderCircle className="h-3.5 w-3.5 animate-spin text-cyan-600" />
                  ) : card.status === "completed" ? (
                    <Check className="h-3.5 w-3.5 text-emerald-600" />
                  ) : (
                    <span className="h-2 w-2 rounded-full bg-stone-300" />
                  )}
                </div>
                <div className="mt-1 truncate text-sm text-stone-600">
                  {card.title}
                </div>
              </div>
            </div>
            <ChevronDown className="h-4 w-4 shrink-0 text-stone-400 transition-transform group-open:rotate-180" />
          </summary>
          <div className="border-t border-stone-100 bg-stone-50/70 px-4 py-4">
            <div className="mb-4 text-sm font-medium text-stone-700">
              {card.summary}
            </div>
            <div className="space-y-4">
              <div>
                <div className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-stone-400">
                  Input Parameters
                </div>
                <pre className="overflow-x-auto rounded-lg border border-stone-200 bg-white p-3 font-mono text-xs leading-5 text-stone-700 shadow-sm">
                  {renderJson(card.input)}
                </pre>
              </div>
              <div>
                <div className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-stone-400">
                  Return Results
                </div>
                <pre className="overflow-x-auto rounded-lg border border-stone-200 bg-white p-3 font-mono text-xs leading-5 text-stone-700 shadow-sm">
                  {renderJson(card.result)}
                </pre>
              </div>
            </div>
          </div>
        </details>
      ))}
    </div>
  );
}

export default function MainWorkspace({
  activeReferenceId,
  apiState,
  bootError,
  documents,
  draftQuestion,
  hotQuestions,
  isSubmitting,
  messages,
  onDraftQuestionChange,
  onReferenceClick,
  onRegenerateAnswer,
  onSelectHotQuestion,
  onStop,
  onSubmit
}: MainWorkspaceProps) {
  const [copyFeedback, setCopyFeedback] = useState<{
    messageId: string | null;
    tone: "idle" | "success" | "error";
  }>({
    messageId: null,
    tone: "idle"
  });
  const latestMessage = messages.at(-1) ?? null;
  const latestReferences = useMemo(() => {
    if (!latestMessage) {
      return [];
    }

    return buildReferenceRecords(
      latestMessage.sources,
      documents,
      latestMessage.confidence,
      latestMessage.relatedRefs,
      latestMessage.id
    );
  }, [documents, latestMessage]);

  async function handleCopyMessage(message: ChatTurn) {
    if (!isChatTurnExportable(message)) {
      return;
    }

    try {
      await copyMarkdownToClipboard(message.answer);
      setCopyFeedback({ messageId: message.id, tone: "success" });
    } catch {
      setCopyFeedback({ messageId: message.id, tone: "error" });
    }

    window.setTimeout(() => {
      setCopyFeedback((current) =>
        current.messageId === message.id
          ? { messageId: null, tone: "idle" }
          : current
      );
    }, 1800);
  }

  return (
    <main className="relative flex h-full flex-1 flex-col overflow-hidden bg-white">
      <div
        className="pointer-events-none absolute inset-0 opacity-[0.02]"
        style={{
          backgroundImage:
            "linear-gradient(#000 1px, transparent 1px), linear-gradient(90deg, #000 1px, transparent 1px)",
          backgroundSize: "20px 20px"
        }}
      />

      <div className="flex-1 overflow-y-auto px-6 py-8 lg:px-8 lg:py-10">
        <div className="mx-auto max-w-4xl space-y-10">
          {messages.length === 0 ? (
            <section className="space-y-8">
              <div className="space-y-3">
                <div className="flex items-center gap-2 text-sm font-medium text-cyan-800">
                  <Sparkles className="h-4 w-4" />
                  <span>混凝土结构问答工作台</span>
                </div>
                <h1 className="max-w-2xl font-serif text-4xl leading-tight tracking-tight text-stone-900">
                  围绕已载入的 Eurocode 文档，直接提问结构分析、构件分类与构件设计概念。
                </h1>
                <p className="max-w-2xl text-sm leading-6 text-stone-500">
                  提问后会先对已载入文档执行混合检索，再同步展示来源、条款定位和文档页预览。
                </p>
              </div>

              <div className="grid gap-4 md:grid-cols-[1.2fr_0.8fr]">
                <div className="rounded-2xl border border-stone-200 bg-stone-50/70 p-5">
                  <div className="mb-3 text-xs font-semibold uppercase tracking-wider text-stone-400">
                    已载入文档热门问题
                  </div>
                  <div className="space-y-2">
                    {hotQuestions.slice(0, 6).map((question) => (
                      <button
                        key={question}
                        className="block w-full rounded-xl border border-stone-200 bg-white px-4 py-3 text-left text-sm text-stone-700 transition-colors hover:border-cyan-300 hover:text-stone-900"
                        onClick={() => onSelectHotQuestion(question)}
                        type="button"
                      >
                        {question}
                      </button>
                    ))}
                  </div>
                </div>

                <div className="rounded-2xl border border-stone-200 bg-stone-900 p-5 text-stone-200">
                  <div className="mb-4 text-xs font-semibold uppercase tracking-wider text-stone-500">
                    当前连接
                  </div>
                  <div className="space-y-3 text-sm">
                    <div className="flex items-center justify-between border-b border-stone-800 pb-2">
                      <span>API 状态</span>
                      <span>{apiState === "ready" ? "在线" : "加载中"}</span>
                    </div>
                    <div className="flex items-center justify-between border-b border-stone-800 pb-2">
                      <span>检索范围</span>
                      <span>{documents.length > 0 ? "全部已载入文档" : "等待文档载入"}</span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span>回答方式</span>
                      <span>POST /query/stream</span>
                    </div>
                  </div>
                </div>
              </div>
            </section>
          ) : null}

          {messages.map((message, index) => {
            const references = buildReferenceRecords(
              message.sources,
              documents,
              message.confidence,
              message.relatedRefs,
              message.id
            );
            const rawAnswer = extractDisplayAnswer(message.answer);
            const displayAnswer = linkifyReferenceCitations(
              rawAnswer,
              references
            );
            const isCopyable = isChatTurnExportable(message);
            const copyTone =
              copyFeedback.messageId === message.id ? copyFeedback.tone : "idle";
            const markdownComponents: Components = {
              a: ({ href, children, ...props }) => {
                const referenceId = getReferenceIdFromHref(href);
                const unmatchedCitation = getUnmatchedCitationLabelFromHref(href);

                if (!referenceId && !unmatchedCitation) {
                  return (
                    <a
                      {...props}
                      href={href}
                      rel="noreferrer"
                      target="_blank"
                    >
                      {children}
                    </a>
                  );
                }

                const isActive = activeReferenceId === referenceId;
                const label = unmatchedCitation ?? getCitationText(children);
                const anchor = buildInlineReferenceAnchor(
                  label,
                  referenceId,
                  references
                );
                return (
                  referenceId ? (
                    <sup className="mx-1 inline-flex align-super">
                      <button
                        aria-label={anchor.ariaLabel}
                        className={`inline-flex h-5 min-w-5 cursor-pointer items-center justify-center rounded-full border text-[11px] font-semibold leading-none shadow-sm transition-all ${
                          isActive
                            ? "border-cyan-700 bg-cyan-700 text-white shadow-[0_10px_22px_rgba(14,116,144,0.28)]"
                            : "border-cyan-200 bg-white text-cyan-700 hover:-translate-y-px hover:border-cyan-300 hover:bg-cyan-50"
                        }`}
                        onClick={() => onReferenceClick(referenceId)}
                        title={anchor.tooltip}
                        type="button"
                      >
                        {anchor.badge}
                      </button>
                    </sup>
                  ) : (
                    <sup className="mx-1 inline-flex align-super">
                      <span
                        aria-label={anchor.ariaLabel}
                        className="inline-flex h-5 items-center justify-center rounded-md border border-stone-200 bg-stone-100 px-1.5 font-mono text-[10px] font-semibold leading-none text-stone-500 shadow-sm"
                        title={anchor.tooltip}
                      >
                        {anchor.badge}
                      </span>
                    </sup>
                  )
                );
              }
            };

            return (
              <div className="space-y-6" key={message.id}>
                {/* 用户问题气泡 */}
                <motion.div
                  animate={{ opacity: 1, y: 0 }}
                  className="flex flex-col items-end"
                  initial={{ opacity: 0, y: 10 }}
                >
                  <div className="max-w-[85%] rounded-2xl rounded-tr-sm border border-stone-200/50 bg-stone-100 px-5 py-4 shadow-sm">
                    <p className="text-[15px] leading-relaxed">{message.question}</p>
                  </div>
                </motion.div>

                {/* AI 回答 */}
                <motion.div
                  animate={{ opacity: 1, y: 0 }}
                  className="flex flex-col items-start"
                  initial={{ opacity: 0, y: 10 }}
                  transition={{ delay: index === 0 ? 0.08 : 0 }}
                >
                  <div className="mb-3 flex flex-wrap items-center gap-3 text-sm font-medium text-cyan-800">
                    <div className="flex items-center gap-2">
                      {message.status === "streaming" ? (
                        <LoaderCircle className="h-4 w-4 animate-spin" />
                      ) : (
                        <Sparkles className="h-4 w-4" />
                      )}
                      <span>Euro_QA 智能综合解答</span>
                      <span className="ml-2 text-xs font-normal text-stone-400">
                        {message.status === "streaming"
                          ? "流式生成中…"
                          : message.sources.length > 0
                            ? `基于 ${message.sources.length} 条引用综合生成`
                            : message.degraded
                              ? "已降级到非流式"
                              : "已完成"}
                      </span>
                    </div>
                  </div>

                  <div className="w-full max-w-[95%] space-y-6 text-[15px] leading-relaxed text-stone-800">
                    <ToolCallTimeline message={message} />

                    {displayAnswer ? (
                      <div className={markdownClassName}>
                        <MarkdownRenderBoundary
                          content={displayAnswer}
                        >
                          <ReactMarkdown
                            components={markdownComponents}
                            rehypePlugins={markdownRehypePlugins}
                            remarkPlugins={markdownRemarkPlugins}
                            urlTransform={markdownUrlTransform}
                          >
                            {displayAnswer}
                          </ReactMarkdown>
                        </MarkdownRenderBoundary>
                      </div>
                    ) : null}

                    {message.errorMessage ? (
                      <div className="rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
                        {message.errorMessage}
                      </div>
                    ) : null}

                    {references.length > 0 ? (
                      <div className="border-t border-stone-100 pt-4">
                        <h4 className="mb-3 text-xs font-semibold uppercase tracking-wider text-stone-400">
                          引用来源
                        </h4>
                        <div className="flex flex-wrap gap-2">
                          {references.map((reference) => {
                            const isActive = activeReferenceId === reference.id;
                            const ordinal = getReferenceOrdinal(reference.id, references) ?? "?";
                            return (
                              <button
                                className={`flex items-center gap-2 rounded-xl px-3 py-2 text-sm transition-all ${
                                  isActive
                                    ? "bg-stone-900 text-white shadow-md"
                                    : "border border-stone-200 bg-stone-50 text-stone-600 hover:border-stone-300 hover:bg-stone-100"
                                }`}
                                key={reference.id}
                                onClick={() => onReferenceClick(reference.id)}
                                title={`引用 ${ordinal} · ${reference.displayTitle} · ${reference.source.clause}`}
                                type="button"
                              >
                                <span
                                  className={`inline-flex h-5 min-w-5 items-center justify-center rounded-full text-[11px] font-semibold leading-none ${
                                    isActive
                                      ? "bg-white/15 text-white"
                                      : "bg-cyan-700 text-white"
                                  }`}
                                >
                                  {ordinal}
                                </span>
                                <FileText className="h-3.5 w-3.5" />
                                <span className="font-mono text-xs leading-5">
                                  {reference.displayTitle} · {reference.source.clause}
                                </span>
                              </button>
                            );
                          })}
                        </div>
                      </div>
                    ) : null}

                    {message.relatedRefs.length > 0 ? (
                      <div className="flex flex-wrap gap-2">
                        {message.relatedRefs.map((ref) => {
                          const matched = matchRelatedRefToReference(ref, references);
                          if (matched) {
                            const ordinal = getReferenceOrdinal(matched.id, references) ?? "?";
                            const isActive = activeReferenceId === matched.id;
                            return (
                              <button
                                className={`flex items-center gap-1.5 rounded-full px-3 py-1 text-xs transition-all ${
                                  isActive
                                    ? "bg-stone-900 text-white shadow-md"
                                    : "border border-stone-200 bg-stone-50 text-stone-600 hover:border-stone-300 hover:bg-stone-100"
                                }`}
                                key={ref}
                                onClick={() => onReferenceClick(matched.id)}
                                title={`引用 ${ordinal} · ${ref}`}
                                type="button"
                              >
                                <span
                                  className={`inline-flex h-4 min-w-4 items-center justify-center rounded-full text-[10px] font-semibold leading-none ${
                                    isActive
                                      ? "bg-white/15 text-white"
                                      : "bg-cyan-700 text-white"
                                  }`}
                                >
                                  {ordinal}
                                </span>
                                {ref}
                              </button>
                            );
                          }
                          return (
                            <span
                              className="rounded-full border border-stone-200 bg-stone-50 px-3 py-1 text-xs text-stone-500"
                              key={ref}
                            >
                              {ref}
                            </span>
                          );
                        })}
                      </div>
                    ) : null}

                    {/* 底部操作栏：复制 + 重新生成 */}
                    {message.status === "done" ? (
                      <div className="flex items-center gap-1 pt-2">
                        <button
                          aria-label="复制回答"
                          className={`inline-flex h-8 w-8 items-center justify-center rounded-lg transition ${
                            copyTone === "success"
                              ? "text-emerald-600"
                              : "text-stone-400 hover:bg-stone-100 hover:text-stone-600"
                          }`}
                          disabled={!isCopyable}
                          onClick={() => {
                            void handleCopyMessage(message);
                          }}
                          title={
                            copyTone === "success"
                              ? "已复制"
                              : "复制回答"
                          }
                          type="button"
                        >
                          {copyTone === "success" ? (
                            <Check className="h-4 w-4" />
                          ) : (
                            <Copy className="h-4 w-4" />
                          )}
                        </button>
                        <button
                          aria-label="重新生成"
                          className="inline-flex h-8 w-8 items-center justify-center rounded-lg text-stone-400 transition hover:bg-stone-100 hover:text-stone-600 disabled:cursor-not-allowed disabled:text-stone-300"
                          disabled={isSubmitting || !onRegenerateAnswer}
                          onClick={() => onRegenerateAnswer?.(message.id)}
                          title="重新生成"
                          type="button"
                        >
                          <RotateCcw className="h-4 w-4" />
                        </button>
                      </div>
                    ) : null}
                  </div>
                </motion.div>
              </div>
            );
          })}

          {/* 无来源提示已移至标题行动态显示 */}
        </div>
      </div>

      <div className="z-10 border-t border-stone-100 bg-white p-5 lg:p-6">
        <div className="mx-auto max-w-4xl">
          <div className="group relative">
            <div className="absolute inset-0 rounded-xl bg-gradient-to-r from-cyan-500/20 to-blue-500/20 opacity-0 blur-md transition-opacity duration-500 group-focus-within:opacity-100" />
            <div className="relative flex flex-col rounded-xl border border-stone-300 bg-white shadow-sm transition-all focus-within:border-cyan-500 focus-within:ring-1 focus-within:ring-cyan-500">
              <textarea
                className="min-h-[96px] w-full resize-none bg-transparent px-4 py-3 text-[15px] text-stone-800 placeholder:text-stone-400 focus:outline-none"
                onChange={(event) => onDraftQuestionChange(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" && !event.shiftKey) {
                    event.preventDefault();
                    if (isSubmitting) {
                      onStop?.();
                    } else {
                      onSubmit();
                    }
                  }
                }}
                placeholder="输入规范相关问题，例如：长细比是如何定义的?"
                value={draftQuestion}
              />
              <div className="flex items-center justify-between border-t border-stone-100 bg-stone-50/60 px-3 py-2">
                <div className="flex items-center gap-3">
                  <span className="flex items-center gap-1 text-xs text-stone-500">
                    <Search className="h-3.5 w-3.5" />
                    混合检索
                  </span>
                </div>
                {isSubmitting ? (
                  <button
                    aria-label="停止生成"
                    className="flex items-center justify-center rounded-lg bg-stone-900 p-1.5 text-white transition-colors hover:bg-stone-700"
                    onClick={onStop}
                    title="停止生成"
                    type="button"
                  >
                    <Square className="h-4 w-4" />
                  </button>
                ) : (
                  <button
                    aria-label="提交问题"
                    className="flex items-center justify-center rounded-lg bg-stone-900 p-1.5 text-white transition-colors hover:bg-stone-800 disabled:cursor-not-allowed disabled:bg-stone-300"
                    disabled={draftQuestion.trim().length === 0}
                    onClick={onSubmit}
                    type="button"
                  >
                    <CornerDownLeft className="h-4 w-4" />
                  </button>
                )}
              </div>
            </div>
          </div>

          <div className="mt-3 text-center">
            <span className="text-[10px] text-stone-400">
              AI 生成内容可能存在误差，请结合原规范进行工程判断。
            </span>
            {bootError ? (
              <span className="ml-2 text-[10px] text-amber-600">{bootError}</span>
            ) : null}
          </div>
        </div>
      </div>
    </main>
  );
}
