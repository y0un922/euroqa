"""MVP single-iteration orchestration.

baseline ×2 → LocateBottleneck → precheck gates → candidate A/B → report.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from eval_methodology.mvp.candidate import (  # noqa: E402
    baseline_candidate,
    treatment_candidate,
)
from eval_methodology.mvp.isolation import (  # noqa: E402
    assert_isolation,
    compare_snapshots,
    take_snapshot,
)
from eval_methodology.mvp.loop.decision import (  # noqa: E402
    MetricSnapshot,
    ab_decide,
    candidate_precheck,
    locate_bottleneck,
    pick_single_var_action,
)
from eval_methodology.mvp.metrics.e2e import paired_series  # noqa: E402
from eval_methodology.mvp.metrics.run_eval import (  # noqa: E402
    _load_split_items,
    eval_on_sidecar,
)
from eval_methodology.mvp.metrics.schemas import PerQuestionMetrics  # noqa: E402
from eval_methodology.mvp.paths import (  # noqa: E402
    ARTIFACTS_DIR,
    BASELINE_PORT,
    CANDIDATE_PORT,
    DATASET_JSON,
    REPORTS_DIR,
)
from eval_methodology.mvp.reports.render import render_report  # noqa: E402
from eval_methodology.mvp.runner.client import context_id_set, query_stream  # noqa: E402
from eval_methodology.mvp.runner.sidecar import SidecarHandle, start_sidecar  # noqa: E402


def _utc() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _per_q_list(run: dict[str, Any]) -> list[PerQuestionMetrics]:
    return [PerQuestionMetrics.model_validate(p) for p in run["per_question"]]


def _context_diff_scan(
    items: list[dict[str, Any]],
    *,
    baseline_port: int = BASELINE_PORT,
    candidate_port: int = CANDIDATE_PORT,
) -> tuple[list[str], dict[str, Any]]:
    """Compare ordered context chunk-id sets off vs on (no judge)."""
    base_h: SidecarHandle | None = None
    cand_h: SidecarHandle | None = None
    diff_ids: list[str] = []
    details: dict[str, Any] = {}
    try:
        base_h = start_sidecar(baseline_candidate(), port=baseline_port)
        base_h.wait_ready(timeout_s=180.0)
        cand_h = start_sidecar(treatment_candidate(), port=candidate_port)
        cand_h.wait_ready(timeout_s=180.0)
        for item in items:
            qid = item["id"]
            b = query_stream(base_h.stream_url, item["question"])
            c = query_stream(cand_h.stream_url, item["question"])
            bs, cs = context_id_set(b), context_id_set(c)
            changed = bs != cs
            details[qid] = {
                "changed": changed,
                "baseline_n": len(bs),
                "candidate_n": len(cs),
                "only_baseline": sorted(bs - cs)[:10],
                "only_candidate": sorted(cs - bs)[:10],
            }
            if changed:
                diff_ids.append(qid)
    finally:
        if cand_h is not None:
            cand_h.stop()
        if base_h is not None:
            base_h.stop()
    return diff_ids, details


def run_mvp(
    *,
    dataset_path: Path = DATASET_JSON,
    split: str = "dev",
    limit: int | None = None,
    use_llm_judge: bool = True,
    use_llm_extract: bool = True,
    skip_precheck_context: bool = False,
) -> dict[str, Any]:
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    before = take_snapshot()
    items = _load_split_items(dataset_path, split, limit)
    if not items:
        raise RuntimeError(f"no items in split={split}")

    payload: dict[str, Any] = {
        "started_at": _utc(),
        "split": split,
        "n_items": len(items),
        "item_ids": [i["id"] for i in items],
    }

    try:
        # --- baseline ×2 ---
        print("=== baseline run 1/2 ===")
        base_h = start_sidecar(baseline_candidate(), port=BASELINE_PORT)
        try:
            base_h.wait_ready(timeout_s=180.0)
            run1 = eval_on_sidecar(
                base_h,
                items,
                use_llm_judge=use_llm_judge,
                use_llm_extract=use_llm_extract,
            )
            print("=== baseline run 2/2 ===")
            run2 = eval_on_sidecar(
                base_h,
                items,
                use_llm_judge=use_llm_judge,
                use_llm_extract=use_llm_extract,
            )
        finally:
            base_h.stop()

        payload["baseline_runs"] = [run1, run2]
        snap = MetricSnapshot.from_aggregate(run1["aggregate"])
        bottleneck = locate_bottleneck(snap)
        pick = pick_single_var_action(bottleneck)
        payload["bottleneck"] = {
            "stage": bottleneck.stage,
            "reason": bottleneck.reason,
            "signals": bottleneck.metric_signals,
        }
        payload["pick"] = {
            "action_id": pick.action_id,
            "stage": pick.stage,
            "config_knobs": pick.config_knobs,
            "reason": pick.reason,
        }

        # --- precheck ---
        if skip_precheck_context:
            diff_ids, diff_details = [], {}
            precheck_note = "context precheck skipped by flag"
        else:
            print("=== context-diff precheck (off vs on) ===")
            diff_ids, diff_details = _context_diff_scan(items)
            precheck_note = ""
        pre = candidate_precheck(baseline=snap, context_diff_question_ids=diff_ids)
        if precheck_note:
            pre.reasons.append(precheck_note)
        payload["precheck"] = {
            "ok": pre.ok,
            "points_to_l4": pre.points_to_l4,
            "context_diff_n": pre.context_diff_n,
            "diff_ids": diff_ids,
            "reasons": pre.reasons,
            "details": diff_details,
        }

        if pick.action_id != "auto_cross_ref_closure_on":
            payload["decision"] = {
                "state": "inconclusive",
                "reason": f"pick is {pick.action_id}, not MVP A candidate",
            }
            payload["stopped_before_candidate"] = True
        elif not pre.ok:
            payload["decision"] = {
                "state": "inconclusive",
                "reason": "candidate precheck failed: " + "; ".join(pre.reasons),
            }
            payload["stopped_before_candidate"] = True
        else:
            # --- candidate (×1; budget) ---
            print("=== candidate run ===")
            cand_h = start_sidecar(treatment_candidate(), port=CANDIDATE_PORT)
            try:
                cand_h.wait_ready(timeout_s=180.0)
                cand_run = eval_on_sidecar(
                    cand_h,
                    items,
                    use_llm_judge=use_llm_judge,
                    use_llm_extract=use_llm_extract,
                )
            finally:
                cand_h.stop()
            payload["candidate_runs"] = [cand_run]

            # Paired series on Faith (primary hard gate); also record CitP.
            b_pq = _per_q_list(run1)
            c_pq = _per_q_list(cand_run)
            b_f, c_f, ids_f = paired_series(b_pq, c_pq, "faith")
            b_rep_a = [p.faith for p in _per_q_list(run1) if p.faith is not None]
            # Align repeat series on intersection of non-null faith.
            map1 = {p.question_id: p.faith for p in _per_q_list(run1)}
            map2 = {p.question_id: p.faith for p in _per_q_list(run2)}
            common = sorted(
                qid
                for qid in set(map1) & set(map2)
                if map1[qid] is not None and map2[qid] is not None
            )
            rep_a = [float(map1[q]) for q in common]
            rep_b = [float(map2[q]) for q in common]

            decision = ab_decide(
                baseline_values=b_f,
                candidate_values=c_f,
                baseline_repeat_a=rep_a,
                baseline_repeat_b=rep_b,
                primary_metric="faith",
                effective_n=len(b_f),
                judge_drop_rate=float(run1["aggregate"].get("judge_drop_rate") or 0),
                degraded_to_trend=bool(run1["aggregate"].get("degraded_to_trend")),
            )
            payload["decision"] = decision.to_dict()
            payload["paired_ids_faith"] = ids_f

            b_c, c_c, ids_c = paired_series(b_pq, c_pq, "citp")
            if b_c:
                citp_dec = ab_decide(
                    baseline_values=b_c,
                    candidate_values=c_c,
                    primary_metric="citp",
                    effective_n=len(b_c),
                    judge_drop_rate=float(run1["aggregate"].get("judge_drop_rate") or 0),
                )
                payload["decision_citp"] = citp_dec.to_dict()
                payload["paired_ids_citp"] = ids_c

        payload["finished_at"] = _utc()
    finally:
        after = take_snapshot()
        iso = compare_snapshots(before, after)
        payload["isolation"] = iso.to_dict()
        ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        out_json = ARTIFACTS_DIR / f"mvp_run_{ts}.json"
        out_json.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        payload["_artifact_json"] = str(out_json)
        md_path = render_report(payload, out_dir=REPORTS_DIR, ts=ts)
        payload["_report_md"] = str(md_path)
        print(f"wrote {out_json}")
        print(f"wrote {md_path}")
        assert_isolation(iso)

    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run MVP single-iteration loop")
    parser.add_argument("--dataset", type=Path, default=DATASET_JSON)
    parser.add_argument("--split", type=str, default="dev")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--no-llm-judge", action="store_true")
    parser.add_argument("--no-llm-extract", action="store_true")
    parser.add_argument(
        "--skip-precheck-context",
        action="store_true",
        help="skip off→on context diff scan (debug only)",
    )
    args = parser.parse_args(argv)
    run_mvp(
        dataset_path=args.dataset,
        split=args.split,
        limit=args.limit,
        use_llm_judge=not args.no_llm_judge,
        use_llm_extract=not args.no_llm_extract,
        skip_precheck_context=args.skip_precheck_context,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
