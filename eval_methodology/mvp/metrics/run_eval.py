"""Run end-to-end eval on a split via sidecar + dual judge + diagnostics."""

from __future__ import annotations

import argparse
import json
import sys
import time
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
from eval_methodology.mvp.metrics.e2e import (  # noqa: E402
    aggregate,
    run_dict_from_stream_and_judge,
)
from eval_methodology.mvp.metrics.judges.cache import JudgeCache  # noqa: E402
from eval_methodology.mvp.metrics.judges.dual_judge import judge_question  # noqa: E402
from eval_methodology.mvp.paths import (  # noqa: E402
    ARTIFACTS_DIR,
    BASELINE_PORT,
    CANDIDATE_PORT,
    DATASET_JSON,
)
from eval_methodology.mvp.runner.client import query_stream  # noqa: E402
from eval_methodology.mvp.runner.sidecar import SidecarHandle, start_sidecar  # noqa: E402


def _load_split_items(
    dataset_path: Path,
    split: str,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    data = json.loads(dataset_path.read_text(encoding="utf-8"))
    items = [i for i in data["items"] if i.get("split") == split]
    items.sort(key=lambda x: x["id"])
    if limit is not None:
        items = items[:limit]
    return items


def _e_plus_for(item: dict[str, Any]) -> list[str]:
    gold = item.get("gold") or {}
    if isinstance(gold, dict):
        return list(gold.get("E_plus") or [])
    return []


def _gold_claim_status(item: dict[str, Any]) -> str:
    gold = item.get("gold") or {}
    if isinstance(gold, dict):
        return str(gold.get("gold_claim_status") or "")
    return ""


def eval_on_sidecar(
    handle: SidecarHandle,
    items: list[dict[str, Any]],
    *,
    use_llm_judge: bool = True,
    use_llm_extract: bool = True,
    cache: JudgeCache | None = None,
    sleep_s: float = 0.0,
) -> dict[str, Any]:
    cache = cache or JudgeCache()
    per_q = []
    raw_results = []
    models_seen: dict[str, str] = {}

    for idx, item in enumerate(items, 1):
        qid = item["id"]
        question = item["question"]
        print(f"  [{idx}/{len(items)}] {qid}")
        try:
            stream = query_stream(handle.stream_url, question)
            if use_llm_judge:
                judged = judge_question(
                    question=question,
                    answer=stream.get("answer") or "",
                    context_chunks=stream.get("context_chunks") or [],
                    sources=stream.get("sources") or [],
                    use_llm_extract=use_llm_extract,
                    cache=cache,
                )
            else:
                # Offline: heuristic extract + vacuous scores for wiring.
                from eval_methodology.mvp.metrics.judges.extract import extract_units
                from eval_methodology.mvp.metrics.judges.dual_judge import DualJudgeResult

                units = extract_units(
                    question=question,
                    answer=stream.get("answer") or "",
                    sources=stream.get("sources") or [],
                    context_chunks=stream.get("context_chunks") or [],
                    use_llm=False,
                    cache=cache,
                )
                judged = DualJudgeResult(
                    units=units,
                    codex=None,
                    claude=None,
                    faith=1.0 if units.claims else None,
                    citp=1.0 if units.citations else 0.0,
                    agreed=True,
                    dropped=False,
                    drop_reason="offline-stub",
                    resolved_models={"codex": "stub", "claude": "stub"},
                    per_claim_agreement={},
                    per_citation_agreement={},
                )
            models_seen.update(judged.resolved_models)
            pq = run_dict_from_stream_and_judge(
                question_id=qid,
                stream_result=stream,
                judge_result=judged,
                e_plus=_e_plus_for(item),
                gold_claim_status=_gold_claim_status(item),
            )
            per_q.append(pq)
            raw_results.append(
                {
                    "id": qid,
                    "stream": {
                        "answer": stream.get("answer"),
                        "context_chunk_ids": stream.get("context_chunk_ids"),
                        "unresolved_refs": stream.get("unresolved_refs"),
                        "resolved_refs": stream.get("resolved_refs"),
                        "elapsed_ms": stream.get("elapsed_ms"),
                    },
                    "metrics": pq.model_dump(),
                    "retrieval_gap_ids": pq.retrieval_gap_ids,
                    "judge": {
                        "dropped": judged.dropped,
                        "drop_reason": judged.drop_reason,
                        "faith": judged.faith,
                        "citp": judged.citp,
                        "models": judged.resolved_models,
                    },
                }
            )
        except Exception as exc:  # noqa: BLE001
            from eval_methodology.mvp.metrics.schemas import PerQuestionMetrics

            pq = PerQuestionMetrics(
                question_id=qid,
                judge_dropped=True,
                notes=f"eval error: {type(exc).__name__}: {exc}",
            )
            per_q.append(pq)
            raw_results.append({"id": qid, "error": str(exc), "metrics": pq.model_dump()})
        if sleep_s > 0:
            time.sleep(sleep_s)

    agg = aggregate(per_q)
    return {
        "candidate": describe_candidate(handle.candidate),
        "port": handle.port,
        "n": len(items),
        "aggregate": agg.model_dump(),
        "per_question": [p.model_dump() for p in per_q],
        "raw": raw_results,
        "resolved_models": models_seen,
    }


def run_variant(
    candidate: CandidateConfig,
    items: list[dict[str, Any]],
    *,
    port: int,
    repeats: int = 1,
    use_llm_judge: bool = True,
    use_llm_extract: bool = True,
) -> list[dict[str, Any]]:
    runs = []
    handle: SidecarHandle | None = None
    try:
        handle = start_sidecar(candidate, port=port)
        handle.wait_ready(timeout_s=180.0)
        for r in range(repeats):
            print(f"run {r + 1}/{repeats} on port {port}")
            runs.append(
                eval_on_sidecar(
                    handle,
                    items,
                    use_llm_judge=use_llm_judge,
                    use_llm_extract=use_llm_extract,
                )
            )
    finally:
        if handle is not None:
            handle.stop()
    return runs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="MVP end-to-end evaluation")
    parser.add_argument("--dataset", type=Path, default=DATASET_JSON)
    parser.add_argument("--split", type=str, default="dev")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--repeats", type=int, default=2, help="baseline repeats (×2)")
    parser.add_argument("--variant", choices=["baseline", "candidate", "both"], default="baseline")
    parser.add_argument("--baseline-port", type=int, default=BASELINE_PORT)
    parser.add_argument("--candidate-port", type=int, default=CANDIDATE_PORT)
    parser.add_argument("--no-llm-judge", action="store_true")
    parser.add_argument("--no-llm-extract", action="store_true")
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)

    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    before = take_snapshot()
    items = _load_split_items(args.dataset, args.split, args.limit)
    if not items:
        raise SystemExit(f"no items in split={args.split} from {args.dataset}")

    use_llm_judge = not args.no_llm_judge
    use_llm_extract = not args.no_llm_extract
    payload: dict[str, Any] = {
        "split": args.split,
        "n_items": len(items),
        "item_ids": [i["id"] for i in items],
    }

    try:
        if args.variant in ("baseline", "both"):
            payload["baseline_runs"] = run_variant(
                baseline_candidate(),
                items,
                port=args.baseline_port,
                repeats=args.repeats,
                use_llm_judge=use_llm_judge,
                use_llm_extract=use_llm_extract,
            )
        if args.variant in ("candidate", "both"):
            payload["candidate_runs"] = run_variant(
                treatment_candidate(),
                items,
                port=args.candidate_port,
                repeats=1 if args.variant == "both" else args.repeats,
                use_llm_judge=use_llm_judge,
                use_llm_extract=use_llm_extract,
            )
    finally:
        after = take_snapshot()
        report = compare_snapshots(before, after)
        payload["isolation"] = report.to_dict()
        out = args.out or (ARTIFACTS_DIR / f"eval_{args.variant}_{args.split}.json")
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"wrote {out}")
        assert_isolation(report)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
