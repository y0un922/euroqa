import {
  Check,
  ChevronDown,
  CircleMinus,
  Clock3,
  Database,
  LoaderCircle,
  Network,
} from "lucide-react";

import type { ChatTurn, QueryProgressStatus, ToolSubStep } from "../lib/types";

type TimelineStep = ToolSubStep & {
  children: TimelineStep[];
};

const STEP_ORDER = new Map<string, number>([
  ["query_understanding", 10],
  ["hybrid_search", 20],
  ["metadata_probe", 30],
  ["vector_search", 40],
  ["bm25_search", 50],
  ["fusion_rerank", 60],
  ["parent_retrieval", 70],
  ["cross_ref_closure", 80],
  ["guide_retrieval", 90],
]);

const PARALLEL_STEP_IDS = new Set(["vector_search", "bm25_search"]);

function compactMetadata(
  metadata: Record<string, unknown>,
): Record<string, unknown> {
  return Object.fromEntries(
    Object.entries(metadata).filter(([, value]) => {
      if (value === null || value === undefined || value === "") {
        return false;
      }
      return !Array.isArray(value) || value.length > 0;
    }),
  );
}

function statusRank(status: QueryProgressStatus): number {
  if (status === "running") {
    return 3;
  }
  if (status === "completed") {
    return 2;
  }
  return 1;
}

function mergeStatus(
  current: QueryProgressStatus | undefined,
  next: QueryProgressStatus,
): QueryProgressStatus {
  if (!current) {
    return next;
  }
  return statusRank(next) > statusRank(current) ? next : current;
}

function statusLabel(status: QueryProgressStatus): string {
  if (status === "running") {
    return "运行中";
  }
  if (status === "completed") {
    return "完成";
  }
  return "跳过";
}

function statusIcon(status: QueryProgressStatus) {
  if (status === "running") {
    return <LoaderCircle className="h-4 w-4 animate-spin text-cyan-600" />;
  }
  if (status === "completed") {
    return <Check className="h-4 w-4 text-emerald-600" />;
  }
  return <CircleMinus className="h-4 w-4 text-stone-400" />;
}

function formatElapsed(ms: number | undefined): string {
  const value = Math.max(0, ms ?? 0);
  if (value >= 1000) {
    return `${(value / 1000).toFixed(value >= 10_000 ? 0 : 1)}s`;
  }
  return `${value}ms`;
}

function metadataPreview(metadata: Record<string, unknown>): string {
  const parts: string[] = [];
  const rewritten = metadata.rewritten_question;
  if (typeof rewritten === "string" && rewritten.trim()) {
    parts.push(`改写: ${rewritten}`);
  }
  const expanded = metadata.expanded_queries;
  if (Array.isArray(expanded)) {
    parts.push(`扩展查询 ${expanded.length} 条`);
  }
  const chunkCount = metadata.chunk_count ?? metadata.candidate_count;
  if (typeof chunkCount === "number") {
    parts.push(`${chunkCount} 候选`);
  }
  const groundedness = metadata.groundedness;
  if (typeof groundedness === "string") {
    parts.push(`groundedness=${groundedness}`);
  }
  const resolvedRefs = metadata.resolved_refs;
  if (Array.isArray(resolvedRefs) && resolvedRefs.length > 0) {
    parts.push(`补齐 ${resolvedRefs.length} 引用`);
  }
  return parts.join(" · ");
}

function stepSortKey(step: ToolSubStep): number {
  return STEP_ORDER.get(step.step_id) ?? 999;
}

function buildStepTree(steps: ToolSubStep[]): TimelineStep[] {
  const nodes = new Map<string, TimelineStep>();

  for (const step of steps) {
    nodes.set(step.step_id, { ...step, children: [] });
  }

  const roots: TimelineStep[] = [];
  for (const node of nodes.values()) {
    const parentId = node.parent_step_id ?? null;
    const parent = parentId ? nodes.get(parentId) : null;
    if (parent) {
      parent.children.push(node);
    } else {
      roots.push(node);
    }
  }

  const sortTree = (items: TimelineStep[]) => {
    items.sort((a, b) => stepSortKey(a) - stepSortKey(b));
    for (const item of items) {
      sortTree(item.children);
    }
  };
  sortTree(roots);
  return roots;
}

function toolNameForSteps(steps: ToolSubStep[]): string {
  const named = steps.find((step) => step.tool_name);
  return named?.tool_name ?? "retrieve";
}

function toolTitle(toolName: string): string {
  if (toolName === "retrieve") {
    return "检索规范知识库";
  }
  if (toolName === "lookup_glossary") {
    return "查询术语表";
  }
  return `调用 ${toolName}`;
}

function aggregateStatus(steps: ToolSubStep[]): QueryProgressStatus {
  return (
    steps.reduce<QueryProgressStatus | undefined>(
      (current, step) => mergeStatus(current, step.status),
      undefined,
    ) ?? "completed"
  );
}

function StepRow({ depth, step }: { depth: number; step: TimelineStep }) {
  const metadata = compactMetadata(step.metadata ?? {});
  const hasMetadata = Object.keys(metadata).length > 0;
  const preview = metadataPreview(metadata);
  const isParallel = PARALLEL_STEP_IDS.has(step.step_id);

  return (
    <div className={depth > 0 ? "ml-5 border-l border-stone-200 pl-4" : ""}>
      <div className="rounded-md border border-stone-200 bg-white">
        <div className="flex items-start gap-3 px-3 py-2.5">
          <div className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded bg-stone-50">
            {statusIcon(step.status)}
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-sm font-semibold text-stone-800">
                {step.title}
              </span>
              <span className="rounded bg-stone-100 px-1.5 py-0.5 text-[10px] font-semibold text-stone-500">
                {statusLabel(step.status)}
              </span>
              {isParallel ? (
                <span className="rounded border border-cyan-200 bg-cyan-50 px-1.5 py-0.5 text-[10px] font-semibold text-cyan-700">
                  并行
                </span>
              ) : null}
              <span className="inline-flex items-center gap-1 text-xs text-stone-400">
                <Clock3 className="h-3 w-3" />
                {formatElapsed(step.elapsed_ms)}
              </span>
            </div>
            {step.summary ? (
              <div className="mt-1 text-sm leading-5 text-stone-600">
                {step.summary}
              </div>
            ) : null}
            {preview ? (
              <div className="mt-1 text-xs leading-5 text-stone-500">
                {preview}
              </div>
            ) : null}
          </div>
        </div>
        {hasMetadata ? (
          <details className="group border-t border-stone-100 bg-stone-50/70">
            <summary className="flex cursor-pointer list-none items-center justify-between px-3 py-2 text-xs font-semibold text-stone-500 [&::-webkit-details-marker]:hidden">
              Metadata
              <ChevronDown className="h-3.5 w-3.5 transition-transform group-open:rotate-180" />
            </summary>
            <pre className="overflow-x-auto px-3 pb-3 font-mono text-xs leading-5 text-stone-700">
              {JSON.stringify(metadata, null, 2)}
            </pre>
          </details>
        ) : null}
      </div>
      {step.children.length > 0 ? (
        <div className="mt-2 space-y-2">
          {step.children.map((child) => (
            <StepRow depth={depth + 1} key={child.step_id} step={child} />
          ))}
        </div>
      ) : null}
    </div>
  );
}

export function AgentChainTimeline({ message }: { message: ChatTurn }) {
  const steps = message.toolSubSteps ?? [];
  if (steps.length === 0) {
    return null;
  }

  const tree = buildStepTree(steps);
  const status = aggregateStatus(steps);
  const toolName = toolNameForSteps(steps);
  const runningParallel = steps.filter(
    (step) => step.status === "running" && PARALLEL_STEP_IDS.has(step.step_id),
  );

  return (
    <details className="group overflow-hidden rounded-lg border border-stone-200 bg-stone-50/60 shadow-sm">
      <summary className="flex cursor-pointer list-none items-center justify-between gap-4 bg-white px-4 py-3 [&::-webkit-details-marker]:hidden">
        <div className="flex min-w-0 items-center gap-3">
          <span className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-stone-900 text-white">
            {status === "running" ? (
              <LoaderCircle className="h-4 w-4 animate-spin" />
            ) : (
              <Network className="h-4 w-4" />
            )}
          </span>
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <span className="rounded bg-stone-100 px-2 py-1 font-mono text-[11px] font-semibold uppercase text-stone-500">
                TOOL
              </span>
              <span className="font-mono text-sm font-semibold text-stone-800">
                {toolName}
              </span>
              {statusIcon(status)}
            </div>
            <div className="mt-1 flex flex-wrap items-center gap-2 text-sm text-stone-600">
              <span>{toolTitle(toolName)}</span>
              <span className="text-xs text-stone-400">
                {steps.length} 个子步骤
              </span>
              {runningParallel.length > 1 ? (
                <span className="inline-flex items-center gap-1 rounded border border-cyan-200 bg-cyan-50 px-1.5 py-0.5 text-[10px] font-semibold text-cyan-700">
                  <Database className="h-3 w-3" />
                  并行检索中
                </span>
              ) : null}
            </div>
          </div>
        </div>
        <ChevronDown className="h-4 w-4 shrink-0 text-stone-400 transition-transform group-open:rotate-180" />
      </summary>
      <div className="space-y-2 border-t border-stone-100 px-4 py-4">
        {tree.map((step) => (
          <StepRow depth={0} key={step.step_id} step={step} />
        ))}
      </div>
    </details>
  );
}
