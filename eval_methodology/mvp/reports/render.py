"""Render client-readable Markdown + keep JSON artifact path."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from eval_methodology.mvp.paths import REPORTS_DIR
from eval_methodology.mvp.metrics.schemas import DEFERRED_METRICS


def _fmt(x: Any, digits: int = 3) -> str:
    if x is None:
        return "—"
    if isinstance(x, float):
        return f"{x:.{digits}f}"
    return str(x)


def _agg_row(name: str, run: dict[str, Any] | None) -> list[str]:
    if not run:
        return [name, "—", "—", "—", "—", "—", "—"]
    a = run.get("aggregate") or {}
    return [
        name,
        _fmt(a.get("faith_mean")),
        _fmt(a.get("citp_mean")),
        _fmt(a.get("crec_mean")),
        _fmt(a.get("unresolved_ref_rate_mean")),
        str(a.get("effective_n_faith", "—")),
        _fmt(a.get("judge_drop_rate"), 2),
    ]


def render_report(
    payload: dict[str, Any],
    *,
    out_dir: Path | None = None,
    ts: str | None = None,
) -> Path:
    out_dir = out_dir or REPORTS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = ts or datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    path = out_dir / f"baseline_vs_candidate_{ts}.md"

    base_runs = payload.get("baseline_runs") or []
    cand_runs = payload.get("candidate_runs") or []
    base0 = base_runs[0] if base_runs else None
    base1 = base_runs[1] if len(base_runs) > 1 else None
    cand0 = cand_runs[0] if cand_runs else None

    decision = payload.get("decision") or {}
    models = {}
    if base0:
        models.update(base0.get("resolved_models") or {})
    if cand0:
        models.update({f"cand_{k}": v for k, v in (cand0.get("resolved_models") or {}).items()})

    lines: list[str] = [
        f"# Eurocode QA 评估方法论 MVP 报告 (`{ts}`)",
        "",
        "## 1. 摘要",
        "",
        f"- 划分：`{payload.get('split')}`，题数 **{payload.get('n_items')}**",
        f"- 题目 ID：{', '.join(payload.get('item_ids') or [])}",
        f"- A/B 判定：**{decision.get('state', '—')}**",
        f"- 判定理由：{decision.get('reason', '—')}",
        f"- 主指标：`{decision.get('primary_metric', 'faith')}`",
        f"- 瓶颈定位：{(payload.get('bottleneck') or {}).get('stage')} — "
        f"{(payload.get('bottleneck') or {}).get('reason')}",
        f"- 候选动作：{(payload.get('pick') or {}).get('action_id')} — "
        f"{(payload.get('pick') or {}).get('reason')}",
        "",
        "## 2. 隔离与可追溯",
        "",
        f"- 主项目隔离：`{(payload.get('isolation') or {}).get('ok')}`",
        f"- `.env` 变更：`{(payload.get('isolation') or {}).get('env_changed')}`",
        f"- 新增脏路径：{', '.join((payload.get('isolation') or {}).get('new_dirty_paths') or []) or '（无）'}",
        f"- 启动时间：{payload.get('started_at')} → {payload.get('finished_at')}",
        "",
        "### 2.1 Resolved models / 族",
        "",
    ]
    if models:
        for k, v in models.items():
            lines.append(f"- `{k}`: `{v}`")
    else:
        lines.append("- （无 judge 调用记录）")

    lines.extend(
        [
            "",
            "## 3. 指标表（均值）",
            "",
            "| 版本 | Faith | CitP | CRec | unresolved_ref_rate | 有效 n (Faith) | 剔除率 |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for row in (
        _agg_row("基线 run1", base0),
        _agg_row("基线 run2", base1),
        _agg_row("候选", cand0),
    ):
        lines.append("| " + " | ".join(row) + " |")

    # CI section
    ci = decision.get("ci") or {}
    lines.extend(
        [
            "",
            "## 4. 配对 bootstrap（95% CI）",
            "",
            f"- 主指标：`{decision.get('primary_metric')}`",
            f"- Δ 均值：`{_fmt(decision.get('delta_mean'))}`",
            f"- 95% CI：`[{_fmt(ci.get('low'))}, {_fmt(ci.get('high'))}]`（宽={_fmt(ci.get('width'))}）",
            f"- 有效配对 n：`{decision.get('effective_n', ci.get('n', '—'))}`",
            f"- 探索性（CI 宽>0.1）：`{ci.get('exploratory', '—')}`",
            f"- 基线自波动（noise floor）：`{_fmt(decision.get('self_noise'))}`",
            f"- 配对题 ID：{', '.join(payload.get('paired_ids_faith') or []) or '—'}",
            "",
        ]
    )

    if payload.get("decision_citp"):
        d2 = payload["decision_citp"]
        ci2 = d2.get("ci") or {}
        lines.extend(
            [
                "### CitP 辅助判定",
                "",
                f"- 状态：`{d2.get('state')}` — {d2.get('reason')}",
                f"- Δ={_fmt(d2.get('delta_mean'))} CI=[{_fmt(ci2.get('low'))}, {_fmt(ci2.get('high'))}]",
                "",
            ]
        )

    pre = payload.get("precheck") or {}
    lines.extend(
        [
            "## 5. 候选预检门",
            "",
            f"- 通过：`{pre.get('ok')}`",
            f"- 指向 L4：`{pre.get('points_to_l4')}`",
            f"- context diff 题数：`{pre.get('context_diff_n')}`",
            f"- diff IDs：{', '.join(pre.get('diff_ids') or []) or '—'}",
            f"- 原因：{'; '.join(pre.get('reasons') or []) or '—'}",
            "",
            "## 6. CRec 说明",
            "",
            "- CRec 为 gold-dependent **确定性**诊断（依赖 E⁺，无 judge）。",
            f"- 基线 CRec eligible n：`{(base0 or {}).get('aggregate', {}).get('crec_eligible_n', '—')}`",
            "- `corpus_gap` 题不进分母；`retrieval_gap` 计入。",
            "",
            "## 7. 未实现指标（schema/todo）",
            "",
        ]
    )
    for name, meta in DEFERRED_METRICS.items():
        lines.append(f"- **{name}**：{meta.get('reason')}")

    lines.extend(
        [
            "",
            "## 8. 解读给甲方",
            "",
            "本报告验证「数据集 → 指标 → 单次迭代 A/B」最短闭环是否可运行，",
            "且调参仅通过旁路后端 env 注入，不修改主项目代码与 `.env`。",
            "当判定为 `inconclusive` 时，通常因有效样本不足、judge 分歧剔除、",
            "CI 过宽或改善幅度小于基线自波动——应视为探索性证据，而非版本门禁。",
            "",
        ]
    )

    path.write_text("\n".join(lines), encoding="utf-8")
    return path
