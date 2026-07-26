"""Render the MVP v2 JSON payload as a compact Markdown report."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from eval_methodology.mvp.paths import REPORTS_DIR


def _fmt(value: Any, digits: int = 3) -> str:
    if value is None:
        return "-"
    return f"{value:.{digits}f}" if isinstance(value, float) else str(value)


def _aggregate_row(name: str, run: dict[str, Any] | None) -> list[str]:
    aggregate = (run or {}).get("aggregate") or {}
    return [
        name,
        _fmt(aggregate.get("faith_mean")),
        _fmt(aggregate.get("citp_mean")),
        _fmt(aggregate.get("unresolved_ref_rate_mean")),
        _fmt(aggregate.get("crec_mean")),
        str(aggregate.get("crec_eligible_n", "-")),
        _fmt(aggregate.get("judge_fail_rate"), 2),
    ]


def _answer_records(payload: dict[str, Any]) -> list[dict[str, Any]]:
    records = list(payload.get("candidate_answer_records") or [])
    for key in ("baseline_runs", "candidate_runs"):
        for run in payload.get(key) or []:
            for row in run.get("raw") or []:
                answer = row.get("answer")
                if isinstance(answer, dict):
                    records.append(answer)
    return records


def _token_total(records: list[dict[str, Any]]) -> int:
    total = 0
    for record in records:
        usage = record.get("usage")
        if not isinstance(usage, dict):
            continue
        if isinstance(usage.get("total_tokens"), int):
            total += usage["total_tokens"]
        else:
            total += sum(
                value
                for key, value in usage.items()
                if key in {"input_tokens", "output_tokens"} and isinstance(value, int)
            )
    return total


def _percentile(values: list[int], pct: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    rank = (len(ordered) - 1) * pct
    lower = int(rank)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (rank - lower)


def _per_question_rows(run: dict[str, Any] | None) -> list[list[str]]:
    if not run:
        return []
    return [
        [
            str(row.get("question_id")),
            _fmt(row.get("faith")),
            _fmt(row.get("citp")),
            _fmt(row.get("unresolved_ref_rate")),
            _fmt(row.get("crec")),
            str(row.get("elapsed_ms") or "-"),
            str(row.get("status") or "ok"),
        ]
        for row in run.get("per_question") or []
    ]


def render_report(
    payload: dict[str, Any],
    *,
    out_dir: Path | None = None,
    ts: str | None = None,
) -> Path:
    """Write a Markdown report and return its path."""
    out_dir = out_dir or REPORTS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = ts or datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    path = out_dir / f"baseline_vs_candidate_{ts}.md"

    baseline_runs = payload.get("baseline_runs") or []
    candidate_runs = payload.get("candidate_runs") or []
    baseline = baseline_runs[0] if baseline_runs else None
    candidate = candidate_runs[0] if candidate_runs else None
    decision = payload.get("decision") or {}
    records = _answer_records(payload)
    elapsed = [
        record.get("elapsed_ms")
        for record in records
        if isinstance(record.get("elapsed_ms"), int)
        and record.get("status", "ok") == "ok"
    ]
    models = {}
    for run in (baseline, candidate):
        if run:
            models.update(run.get("resolved_models") or {})

    lines = [
        f"# Eurocode QA MVP v2 报告 (`{ts}`)",
        "",
        "## 摘要",
        "",
        f"- 模式：`{payload.get('mode')}`；划分：`{payload.get('split')}`；题数：{payload.get('n_items')}",
        f"- 三态判定：**{decision.get('state', '-')}**",
        f"- 理由：{decision.get('reason', '-')}",
        f"- 瓶颈：{(payload.get('bottleneck') or {}).get('stage', '-')} - {(payload.get('bottleneck') or {}).get('reason', '-')}",
        f"- 候选：{(payload.get('pick') or {}).get('action_id', '-')} - {(payload.get('pick') or {}).get('reason', '-')}",
        "",
        "## 核心指标",
        "",
        "| 版本 | Faith | CitP | unresolved_ref_rate | CRec* | CRec eligible n | judge_fail_rate |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in (
        _aggregate_row("baseline", baseline),
        _aggregate_row("candidate", candidate),
    ):
        lines.append("| " + " | ".join(row) + " |")
    crec_agg = ((baseline or candidate) or {}).get("aggregate") or {}
    crec_eligible = int(crec_agg.get("crec_eligible_n") or 0)
    crec_confirmed = int(crec_agg.get("crec_confirmed_n") or 0)
    # Full LLM-as-judge mode (no human participation): CRec is LLM semantic coverage of gold evidence.
    if crec_eligible:
        crec_footnote = (
            rf"\* CRec = LLM-as-judge 语义覆盖率（gold evidence 由 LLM 判断上下文是否覆盖核心信息）。"
            f" eligible={crec_eligible}（全 LLM，无需人工确认）。"
        )
    else:
        crec_footnote = r"\* CRec 暂无 gold evidence（LLM 覆盖诊断）。 "
    lines.extend(
        [
            "",
            crec_footnote,
            "",
            "### 版本差值",
            "",
            "| 指标 | candidate - baseline |",
            "|---|---:|",
        ]
    )
    base_agg = (baseline or {}).get("aggregate") or {}
    cand_agg = (candidate or {}).get("aggregate") or {}
    for metric in ("faith", "citp", "unresolved_ref_rate", "crec"):
        key = f"{metric}_mean"
        left, right = base_agg.get(key), cand_agg.get(key)
        delta = right - left if isinstance(left, (int, float)) and isinstance(right, (int, float)) else None
        lines.append(f"| {metric} | {_fmt(delta)} |")

    lines.extend(["", "## 阶段耗时", "", "| 阶段 | 秒 |", "|---|---:|"])
    for name, seconds in (payload.get("stage_timings") or {}).items():
        lines.append(f"| {name} | {_fmt(seconds)} |")

    lines.extend(
        [
            "",
            "## 逐题状态",
            "",
            "| qid | Faith | CitP | URR | CRec | elapsed_ms | status |",
            "|---|---:|---:|---:|---:|---:|---|",
        ]
    )
    rows = _per_question_rows(candidate or baseline)
    if rows:
        for row in rows:
            lines.append("| " + " | ".join(row) + " |")
    else:
        for record in payload.get("candidate_answer_records") or []:
            lines.append(
                f"| {record.get('id')} | - | - | - | - | {record.get('elapsed_ms', '-')} | {record.get('status', '-')} |"
            )

    aggregate = (candidate or baseline or {}).get("aggregate") or {}
    lines.extend(
        [
            "",
            "## Ops",
            "",
            f"- 平均时延：{_fmt(sum(elapsed) / len(elapsed) if elapsed else None)} ms",
            f"- P50 时延：{_fmt(_percentile(elapsed, 0.5))} ms",
            f"- P95 时延：{_fmt(_percentile(elapsed, 0.95))} ms",
            *[
                f"- {side} 时延：mean {_fmt(stats.get('mean_ms'), 1)}"
                f" / P50 {_fmt(stats.get('p50_ms'), 1)}"
                f" / P95 {_fmt(stats.get('p95_ms'), 1)} ms (n={stats.get('n')})"
                for side, stats in (payload.get("latency") or {}).items()
                if isinstance(stats, dict)
            ],
            f"- token 合计：{_token_total(records)}",
            f"- judge_fail_rate：{_fmt(aggregate.get('judge_fail_rate'), 2)}",
            "",
            "## 判定细节",
            "",
            f"- 变更门：{(payload.get('precheck') or {}).get('diff_kind', '-')} diff 题数 {(payload.get('precheck') or {}).get('diff_n', '-')}",
            f"- diff IDs：{', '.join((payload.get('precheck') or {}).get('diff_ids') or []) or '-'}",
            f"- self_noise_bound：{payload.get('self_noise_bound') or '-'}",
            f"- 95% CI：{decision.get('ci') or '-'}",
            "",
            "## Resolved model",
            "",
        ]
    )
    lines.extend(
        [f"- `{family}`: `{model}`" for family, model in models.items()]
        or ["- 未调用 judge"]
    )
    lines.extend(
        [
            "",
            "## 隔离",
            "",
            f"- 主项目隔离：`{(payload.get('isolation') or {}).get('ok')}`",
            f"- `.env` 变更：`{(payload.get('isolation') or {}).get('env_changed')}`",
            f"- 时间：{payload.get('started_at')} -> {payload.get('finished_at')}",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
