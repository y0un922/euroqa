import type { DocumentStatus } from "../lib/types";

const CONFIG: Record<
  string,
  { dot: string; label: string; pulse?: boolean }
> = {
  ready: { dot: "bg-emerald-500", label: "就绪" },
  error: { dot: "bg-rose-500", label: "错误" },
  uploaded: { dot: "bg-stone-400", label: "已上传" },
  pending: { dot: "bg-stone-400", label: "排队中" },
  parsing: { dot: "bg-amber-500", label: "解析中", pulse: true },
  structuring: { dot: "bg-amber-500", label: "结构化", pulse: true },
  chunking: { dot: "bg-amber-500", label: "分块中", pulse: true },
  summarizing: { dot: "bg-amber-500", label: "摘要中", pulse: true },
  indexing: { dot: "bg-amber-500", label: "索引中", pulse: true },
};

type DocumentStatusBadgeProps = {
  status: DocumentStatus;
};

export default function DocumentStatusBadge({ status }: DocumentStatusBadgeProps) {
  const cfg = CONFIG[status] ?? CONFIG.ready;
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-stone-100 px-1.5 py-0.5 text-[10px] text-stone-500">
      <span
        className={`inline-block h-1.5 w-1.5 rounded-full ${cfg.dot} ${
          cfg.pulse ? "animate-pulse" : ""
        }`}
      />
      {cfg.label}
    </span>
  );
}
