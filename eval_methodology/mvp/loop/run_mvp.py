"""MVP v2: stored answers -> single judge -> three-state decision."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from eval_methodology.mvp.candidate import (  # noqa: E402
    CandidateConfig,
    baseline_candidate,
    describe_candidate,
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
    answer_diff_from_answers,
    candidate_precheck,
    context_diff_from_answers,
    locate_bottleneck,
    merge_hard_gate_decisions,
    pick_single_var_action,
)
from eval_methodology.mvp.metrics.bootstrap import self_noise_bound  # noqa: E402
from eval_methodology.mvp.metrics.e2e import paired_series  # noqa: E402
from eval_methodology.mvp.metrics.judges.cache import JudgeCache  # noqa: E402
from eval_methodology.mvp.metrics.run_eval import (  # noqa: E402
    _load_split_items,
    metrics_from_answers,
)
from eval_methodology.mvp.metrics.schemas import PerQuestionMetrics  # noqa: E402
from eval_methodology.mvp.paths import (  # noqa: E402
    BASELINE_PORT,
    CANDIDATE_PORT,
    CONTEXT_DIFF_MIN_QUESTIONS,
    DATASET_JSON,
    MVP_DATASET_VERSION,
    RUNS_DIR,
)
from eval_methodology.mvp.reports.render import _percentile, render_report  # noqa: E402
from eval_methodology.mvp.runner.answers import (  # noqa: E402
    generate_answers,
    load_answers,
)
from eval_methodology.mvp.runner.sidecar import start_sidecar  # noqa: E402


def _utc() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%d_%H%M%S")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def _timing(payload: dict[str, Any], stage: str, seconds: float) -> None:
    payload.setdefault("stage_timings", {})[f"{stage}_s"] = seconds
    print(f"{stage}: {seconds:.3f}s")


def _git_head() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=_PROJECT_ROOT, check=True, capture_output=True, text=True
    ).stdout.strip()


def _candidate_hash(candidate: CandidateConfig) -> str:
    data = json.dumps(candidate.model_dump(), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(data.encode()).hexdigest()[:12]


def _baseline_key(items: list[dict[str, Any]], split: str) -> str:
    """Cache key for a baseline run: code + config + dataset + exact item set."""
    ids_hash = hashlib.sha256(
        ",".join(str(item["id"]) for item in items).encode()
    ).hexdigest()[:12]
    raw = ":".join(
        [
            _git_head(),
            _candidate_hash(baseline_candidate()),
            MVP_DATASET_VERSION,
            split,
            ids_hash,
        ]
    )
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _judge_models_of(runs: list[dict[str, Any]]) -> set[str]:
    """Distinct models that produced non-failed judge verdicts in these runs."""
    models: set[str] = set()
    for run in runs:
        models.update(run.get("judge_models") or [])
    return models


def _per_question(run: dict[str, Any]) -> list[PerQuestionMetrics]:
    return [PerQuestionMetrics.model_validate(item) for item in run.get("per_question") or []]


def _answer_dir(run_dir: Path, variant: str, repeat: int = 1) -> Path:
    suffix = variant if repeat == 1 else f"{variant}_repeat_{repeat}"
    return run_dir / "answers" / suffix


def _checkpoint_callback(
    payload: dict[str, Any],
    payload_path: Path,
    variant: str,
):
    def checkpoint(record: dict[str, Any]) -> None:
        progress = payload.setdefault("answer_progress", {}).setdefault(variant, {})
        progress[record["id"]] = record["status"]
        _write_json(payload_path, payload)

    return checkpoint


def _generate_variant(
    candidate: CandidateConfig,
    items: list[dict[str, Any]],
    run_dir: Path,
    variant: str,
    *,
    port: int,
    repeats: int,
    payload: dict[str, Any],
    payload_path: Path,
) -> tuple[list[dict[str, dict[str, Any]]], float]:
    started = time.monotonic()
    handle = start_sidecar(candidate, port=port)
    try:
        handle.wait_ready(timeout_s=180.0)
        answer_runs = []
        for repeat in range(1, repeats + 1):
            label = variant if repeat == 1 else f"{variant}_repeat_{repeat}"
            print(f"=== answers: {label} ===")
            directory = _answer_dir(run_dir, variant, repeat)
            generate_answers(
                handle,
                items,
                directory,
                on_record=_checkpoint_callback(payload, payload_path, label),
            )
            answer_runs.append(load_answers(directory))
        return answer_runs, time.monotonic() - started
    finally:
        handle.stop()


def _stored_answer_runs(
    run_dir: Path,
    variant: str,
    repeats: int,
) -> list[dict[str, dict[str, Any]]]:
    return [load_answers(_answer_dir(run_dir, variant, repeat)) for repeat in range(1, repeats + 1)]


def _complete(answer_runs: list[dict[str, dict[str, Any]]], items: list[dict[str, Any]]) -> bool:
    expected = {str(item["id"]) for item in items}
    return bool(answer_runs) and all(
        set(run) >= expected
        and all(run[qid].get("status") == "ok" for qid in expected)
        for run in answer_runs
    )


def _evaluate_runs(
    answer_runs: list[dict[str, dict[str, Any]]],
    items: list[dict[str, Any]],
    candidate: CandidateConfig,
    *,
    use_llm_judge: bool,
) -> tuple[list[dict[str, Any]], float]:
    started = time.monotonic()
    cache = JudgeCache()
    runs = []
    for answers in answer_runs:
        result = metrics_from_answers(
            answers,
            items,
            use_llm_judge=use_llm_judge,
            cache=cache,
        )
        result["candidate"] = describe_candidate(candidate)
        runs.append(result)
    return runs, time.monotonic() - started


def _self_noise(runs: list[dict[str, Any]]) -> dict[str, float]:
    if len(runs) < 2:
        return {}
    first = _per_question(runs[0])
    second = _per_question(runs[1])
    out = {}
    for metric in ("faith", "citp"):
        left, right, _ids = paired_series(first, second, metric)
        if left:
            out[metric] = self_noise_bound(left, right)
    return out


def _finish(payload: dict[str, Any], run_dir: Path, before: Any) -> dict[str, Any]:
    payload["finished_at"] = _utc()
    payload_path = run_dir / "payload.json"
    payload["_artifact_json"] = str(payload_path)
    _write_json(payload_path, payload)

    started = time.monotonic()
    report_path = render_report(payload, out_dir=run_dir, ts=payload.get("run_id"))
    _timing(payload, "report", time.monotonic() - started)
    payload["_report_md"] = str(report_path)

    after = take_snapshot()
    isolation = compare_snapshots(before, after)
    payload["isolation"] = isolation.to_dict()
    _write_json(payload_path, payload)
    render_report(payload, out_dir=run_dir, ts=payload.get("run_id"))
    assert_isolation(isolation)
    print(f"wrote {payload_path}")
    print(f"wrote {report_path}")
    return payload


def _build_baseline(
    items: list[dict[str, Any]],
    *,
    split: str,
    use_llm_judge: bool,
    fresh: bool,
    repeats: int,
    baseline_port: int,
) -> tuple[dict[str, Any], Path]:
    key = _baseline_key(items, split)
    run_dir = RUNS_DIR / f"baseline-{key}"
    if fresh and run_dir.exists():
        shutil.rmtree(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    payload_path = run_dir / "payload.json"
    payload = (
        json.loads(payload_path.read_text(encoding="utf-8"))
        if payload_path.is_file()
        else {
            "run_id": run_dir.name,
            "mode": "baseline",
            "cache_key": key,
            "git_head": _git_head(),
            "started_at": _utc(),
            "split": split,
            "n_items": len(items),
            "item_ids": [item["id"] for item in items],
            "stage_timings": {},
        }
    )
    answer_runs = _stored_answer_runs(run_dir, "baseline", repeats)
    if not _complete(answer_runs, items):
        answer_runs, answer_s = _generate_variant(
            baseline_candidate(),
            items,
            run_dir,
            "baseline",
            port=baseline_port,
            repeats=repeats,
            payload=payload,
            payload_path=payload_path,
        )
        _timing(payload, "answers", answer_s)
    else:
        payload["reused_answers"] = True
        _timing(payload, "answers", 0.0)

    runs, judge_s = _evaluate_runs(
        answer_runs,
        items,
        baseline_candidate(),
        use_llm_judge=use_llm_judge,
    )
    if use_llm_judge:
        models = _judge_models_of(runs)
        if len(models) > 1:
            # Mixed models mean stale cache entries from a previous judge backend.
            # Live calls in the first pass pinned the current model, so one
            # re-evaluation converges lookups onto it.
            print(f"judge models mixed {sorted(models)}; re-judging baseline once")
            runs, extra_s = _evaluate_runs(
                answer_runs,
                items,
                baseline_candidate(),
                use_llm_judge=use_llm_judge,
            )
            judge_s += extra_s
            models = _judge_models_of(runs)
            if len(models) > 1:
                payload["judge_models"] = sorted(models)
                _write_json(payload_path, payload)
                raise RuntimeError(
                    f"baseline judged by multiple models {sorted(models)}; "
                    "set MVP_JUDGE_MODEL to pin the judge or clear "
                    "eval_methodology/mvp/cache before rerunning"
                )
        payload["judge_models"] = sorted(models)
    payload.update(
        {
            "judge_enabled": use_llm_judge,
            "baseline_runs": runs,
            "self_noise_bound": _self_noise(runs) if repeats == 2 else {},
            "completed": True,
        }
    )
    _timing(payload, "judge", judge_s)
    _timing(payload, "decide", 0.0)
    _write_json(payload_path, payload)
    return payload, run_dir


def run_baseline(
    *,
    dataset_path: Path = DATASET_JSON,
    split: str = "dev",
    limit: int | None = None,
    use_llm_judge: bool = True,
    fresh: bool = False,
    repeats: int = 1,
    baseline_port: int = BASELINE_PORT,
) -> dict[str, Any]:
    """Run or reuse the cached baseline."""
    if repeats not in (1, 2):
        raise ValueError("repeats must be 1 or 2")
    before = take_snapshot()
    items = _load_split_items(dataset_path, split, limit)
    if not items:
        raise RuntimeError(f"no items in split={split}")
    payload, run_dir = _build_baseline(
        items,
        split=split,
        use_llm_judge=use_llm_judge,
        fresh=fresh,
        repeats=repeats,
        baseline_port=baseline_port,
    )
    return _finish(payload, run_dir, before)


def run_compare(
    *,
    dataset_path: Path = DATASET_JSON,
    split: str = "dev",
    limit: int | None = None,
    use_llm_judge: bool = True,
    fresh: bool = False,
    gate_n: int = 12,
    baseline_port: int = BASELINE_PORT,
    candidate_port: int = CANDIDATE_PORT,
) -> dict[str, Any]:
    """Run baseline selection, candidate answers, diff gate, and A/B decision."""
    before = take_snapshot()
    items = _load_split_items(dataset_path, split, limit)
    if not items:
        raise RuntimeError(f"no items in split={split}")
    baseline_payload, _baseline_dir = _build_baseline(
        items,
        split=split,
        use_llm_judge=use_llm_judge,
        fresh=fresh,
        repeats=1,
        baseline_port=baseline_port,
    )
    baseline_run = baseline_payload["baseline_runs"][0]
    run_dir = RUNS_DIR / f"compare-{_stamp()}"
    run_dir.mkdir(parents=True, exist_ok=True)
    payload_path = run_dir / "payload.json"
    payload: dict[str, Any] = {
        "run_id": run_dir.name,
        "mode": "compare",
        "started_at": _utc(),
        "split": split,
        "n_items": len(items),
        "item_ids": [item["id"] for item in items],
        "baseline_cache_key": baseline_payload["cache_key"],
        "baseline_runs": [baseline_run],
        "stage_timings": {},
    }

    decide_started = time.monotonic()
    snapshot = MetricSnapshot.from_aggregate(baseline_run["aggregate"])
    bottleneck = locate_bottleneck(snapshot)
    pick = pick_single_var_action(bottleneck)
    precheck = candidate_precheck(baseline=snapshot, pick=pick)
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
    payload["precheck"] = {
        "ok": precheck.ok,
        "points_to_l4": precheck.points_to_l4,
        "reasons": precheck.reasons,
    }
    decide_s = time.monotonic() - decide_started
    if pick.action_id == "noop" or not precheck.ok:
        payload["decision"] = {
            "state": "inconclusive",
            "reason": (
                f"baseline does not justify candidate {pick.action_id}: "
                + "; ".join(precheck.reasons)
            ),
            "primary_metric": "faith",
        }
        _timing(payload, "decide", decide_s)
        return _finish(payload, run_dir, before)

    treatment = treatment_candidate(pick.config_knobs)
    candidate_answers, answer_s = _generate_variant(
        treatment,
        items,
        run_dir,
        "candidate",
        port=candidate_port,
        repeats=1,
        payload=payload,
        payload_path=payload_path,
    )
    _timing(payload, "answers", answer_s)
    baseline_answers = load_answers(_answer_dir(_baseline_dir, "baseline"))
    decide_started = time.monotonic()
    if pick.stage == "L4":
        diff_kind = "context"
        gate_fail_reason = "候选未改变检索路径"
        diff_ids, diff_details = context_diff_from_answers(
            baseline_answers, candidate_answers[0]
        )
    else:
        diff_kind = "answer"
        gate_fail_reason = "候选未改变答案"
        diff_ids, diff_details = answer_diff_from_answers(
            baseline_answers, candidate_answers[0]
        )
    decide_s += time.monotonic() - decide_started
    payload["precheck"].update(
        {
            "diff_kind": diff_kind,
            "diff_n": len(diff_ids),
            "context_diff_n": len(diff_ids) if diff_kind == "context" else None,
            "diff_ids": diff_ids,
            "details": diff_details,
        }
    )
    if len(diff_ids) < CONTEXT_DIFF_MIN_QUESTIONS:
        payload["candidate_answer_records"] = list(candidate_answers[0].values())
        payload["decision"] = {
            "state": "inconclusive",
            "reason": gate_fail_reason,
            "primary_metric": "faith",
        }
        _timing(payload, "decide", decide_s)
        return _finish(payload, run_dir, before)

    candidate_runs, judge_s = _evaluate_runs(
        candidate_answers,
        items,
        treatment,
        use_llm_judge=use_llm_judge,
    )
    payload["candidate_runs"] = candidate_runs
    candidate_run = candidate_runs[0]
    if use_llm_judge:
        union = _judge_models_of([baseline_run, candidate_run])
        if len(union) > 1:
            # Baseline verdicts came from cache under a previous judge model while
            # the candidate was judged live. Re-judge the stored baseline answers:
            # the live calls pinned the current model, so lookups now converge.
            print(f"judge models mixed {sorted(union)}; re-judging baseline once")
            rejudged, extra_s = _evaluate_runs(
                [baseline_answers],
                items,
                baseline_candidate(),
                use_llm_judge=use_llm_judge,
            )
            judge_s += extra_s
            baseline_run = rejudged[0]
            payload["baseline_runs"] = [baseline_run]
            payload["judge_consistency"] = {
                "rejudged_baseline": True,
                "initial_models": sorted(union),
            }
            union = _judge_models_of([baseline_run, candidate_run])
            if len(union) > 1:
                payload["judge_models"] = sorted(union)
                _timing(payload, "judge", judge_s)
                _write_json(payload_path, payload)
                raise RuntimeError(
                    f"baseline and candidate judged by different models {sorted(union)}; "
                    "set MVP_JUDGE_MODEL to pin the judge or clear "
                    "eval_methodology/mvp/cache before rerunning"
                )
        payload["judge_models"] = sorted(union)
    _timing(payload, "judge", judge_s)
    decide_started = time.monotonic()
    per_metric = {}
    paired_deltas = {}
    modes = {"faith": "improve", "citp": "non_regress"}
    for metric, mode in modes.items():
        baseline_values, candidate_values, ids = paired_series(
            _per_question(baseline_run),
            _per_question(candidate_run),
            metric,
        )
        if not baseline_values:
            continue
        decision = ab_decide(
            baseline_values,
            candidate_values,
            primary_metric=metric,
            gate_n=gate_n,
            mode=mode,
        )
        per_metric[metric] = decision
        payload[f"decision_{metric}"] = decision.to_dict()
        paired_deltas[metric] = [
            {
                "question_id": qid,
                "baseline": baseline_values[index],
                "candidate": candidate_values[index],
                "delta": candidate_values[index] - baseline_values[index],
            }
            for index, qid in enumerate(ids)
        ]
    payload["paired_deltas"] = paired_deltas
    payload["decision"] = merge_hard_gate_decisions(per_metric).to_dict()
    decide_s += time.monotonic() - decide_started
    _timing(payload, "decide", decide_s)
    return _finish(payload, run_dir, before)


def _latency_stats(answers: dict[str, dict[str, Any]]) -> dict[str, Any]:
    elapsed = sorted(
        record["elapsed_ms"]
        for record in answers.values()
        if isinstance(record.get("elapsed_ms"), int) and record.get("status") == "ok"
    )
    if not elapsed:
        return {"n": 0, "mean_ms": None, "p50_ms": None, "p95_ms": None}
    return {
        "n": len(elapsed),
        "mean_ms": sum(elapsed) / len(elapsed),
        "p50_ms": _percentile(elapsed, 0.5),
        "p95_ms": _percentile(elapsed, 0.95),
    }


def run_compare_runs(
    *,
    baseline_run_dir: Path,
    candidate_run_dir: Path,
    dataset_path: Path = DATASET_JSON,
    use_llm_judge: bool = True,
    gate_n: int = 12,
) -> dict[str, Any]:
    """Gate a code change: paired non-regression A/B between two stored runs.

    Unlike ``compare`` (same code, single config knob), both sides here are
    stored ``baseline``-mode runs produced at different git HEADs. Answers are
    reused as-is; judging runs live so both sides share one judge model.
    """
    before = take_snapshot()
    base_payload = json.loads(
        (baseline_run_dir / "payload.json").read_text(encoding="utf-8")
    )
    cand_payload = json.loads(
        (candidate_run_dir / "payload.json").read_text(encoding="utf-8")
    )
    base_ids = {str(item) for item in base_payload.get("item_ids") or []}
    cand_ids = {str(item) for item in cand_payload.get("item_ids") or []}
    if not base_ids or base_ids != cand_ids:
        raise RuntimeError(
            f"runs cover different item sets: baseline={sorted(base_ids)} "
            f"candidate={sorted(cand_ids)}"
        )
    split = base_payload.get("split") or "dev"
    items = [
        item
        for item in _load_split_items(dataset_path, split, None)
        if str(item["id"]) in base_ids
    ]
    if len(items) != len(base_ids):
        raise RuntimeError(
            f"dataset split={split} no longer contains all run items "
            f"({len(items)} of {len(base_ids)})"
        )

    baseline_answers = load_answers(_answer_dir(baseline_run_dir, "baseline"))
    candidate_answers = load_answers(_answer_dir(candidate_run_dir, "baseline"))
    for label, answers in (
        ("baseline", baseline_answers),
        ("candidate", candidate_answers),
    ):
        if not _complete([answers], items):
            raise RuntimeError(f"{label} run has incomplete or failed answers")

    run_dir = RUNS_DIR / f"compare-runs-{_stamp()}"
    run_dir.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "run_id": run_dir.name,
        "mode": "compare_runs",
        "started_at": _utc(),
        "split": split,
        "n_items": len(items),
        "item_ids": [item["id"] for item in items],
        "baseline_run_dir": str(baseline_run_dir),
        "candidate_run_dir": str(candidate_run_dir),
        "baseline_git_head": base_payload.get("git_head"),
        "candidate_git_head": cand_payload.get("git_head"),
        "stage_timings": {},
    }

    diff_ids, diff_details = context_diff_from_answers(
        baseline_answers, candidate_answers
    )
    payload["precheck"] = {
        "ok": True,
        "diff_kind": "context",
        "diff_n": len(diff_ids),
        "diff_ids": diff_ids,
        "details": diff_details,
    }

    baseline_runs, judge_base_s = _evaluate_runs(
        [baseline_answers], items, baseline_candidate(), use_llm_judge=use_llm_judge
    )
    candidate_runs, judge_cand_s = _evaluate_runs(
        [candidate_answers], items, baseline_candidate(), use_llm_judge=use_llm_judge
    )
    _timing(payload, "judge", judge_base_s + judge_cand_s)
    baseline_run = baseline_runs[0]
    candidate_run = candidate_runs[0]
    payload["baseline_runs"] = [baseline_run]
    payload["candidate_runs"] = [candidate_run]
    if use_llm_judge:
        union = _judge_models_of([baseline_run, candidate_run])
        if len(union) > 1:
            _write_json(run_dir / "payload.json", payload)
            raise RuntimeError(
                f"sides judged by different models {sorted(union)}; "
                "set MVP_JUDGE_MODEL or clear eval_methodology/mvp/cache"
            )
        payload["judge_models"] = sorted(union)

    payload["latency"] = {
        "baseline": _latency_stats(baseline_answers),
        "candidate": _latency_stats(candidate_answers),
    }

    decide_started = time.monotonic()
    per_metric = {}
    paired_deltas = {}
    for metric in ("faith", "citp"):
        baseline_values, candidate_values, ids = paired_series(
            _per_question(baseline_run),
            _per_question(candidate_run),
            metric,
        )
        if not baseline_values:
            continue
        decision = ab_decide(
            baseline_values,
            candidate_values,
            primary_metric=metric,
            gate_n=gate_n,
            mode="non_regress",
        )
        per_metric[metric] = decision
        payload[f"decision_{metric}"] = decision.to_dict()
        paired_deltas[metric] = [
            {
                "question_id": qid,
                "baseline": baseline_values[index],
                "candidate": candidate_values[index],
                "delta": candidate_values[index] - baseline_values[index],
            }
            for index, qid in enumerate(ids)
        ]
    payload["paired_deltas"] = paired_deltas
    payload["decision"] = merge_hard_gate_decisions(per_metric).to_dict()
    _timing(payload, "decide", time.monotonic() - decide_started)
    return _finish(payload, run_dir, before)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run MVP v2 evaluation")
    subparsers = parser.add_subparsers(dest="command", required=True)

    for name in ("baseline", "compare"):
        sub = subparsers.add_parser(name)
        sub.add_argument("--dataset", type=Path, default=DATASET_JSON)
        sub.add_argument("--split", default="dev")
        sub.add_argument("--limit", type=int)
        sub.add_argument("--no-judge", action="store_true")
        sub.add_argument("--fresh", action="store_true")
    baseline = subparsers.choices["baseline"]
    baseline.add_argument("--repeats", type=int, choices=(1, 2), default=1)
    compare = subparsers.choices["compare"]
    compare.add_argument("--gate-n", type=int, default=12)
    compare_runs = subparsers.add_parser(
        "compare-runs",
        help="non-regression A/B between two stored baseline runs (code-change gate)",
    )
    compare_runs.add_argument("--baseline-run", type=Path, required=True)
    compare_runs.add_argument("--candidate-run", type=Path, required=True)
    compare_runs.add_argument("--dataset", type=Path, default=DATASET_JSON)
    compare_runs.add_argument("--no-judge", action="store_true")
    compare_runs.add_argument("--gate-n", type=int, default=12)

    args = parser.parse_args(argv)
    if args.command == "compare-runs":
        run_compare_runs(
            baseline_run_dir=args.baseline_run,
            candidate_run_dir=args.candidate_run,
            dataset_path=args.dataset,
            use_llm_judge=not args.no_judge,
            gate_n=args.gate_n,
        )
        return 0
    common = {
        "dataset_path": args.dataset, "split": args.split, "limit": args.limit,
        "use_llm_judge": not args.no_judge, "fresh": args.fresh,
    }
    if args.command == "baseline":
        run_baseline(**common, repeats=args.repeats)
    else:
        run_compare(**common, gate_n=args.gate_n)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
