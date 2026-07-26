"""Evaluate stored answers with one judge plus deterministic diagnostics."""

from __future__ import annotations

import argparse
import json
import sys
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
from eval_methodology.mvp.metrics.e2e import (  # noqa: E402
    aggregate,
    per_question_from_parts,
)
from eval_methodology.mvp.metrics.judges.cache import JudgeCache  # noqa: E402
from eval_methodology.mvp.metrics.judges.judge import (  # noqa: E402
    JudgeResult,
    judge_question,
)
from eval_methodology.mvp.metrics.schemas import PerQuestionMetrics  # noqa: E402
from eval_methodology.mvp.paths import (  # noqa: E402
    ARTIFACTS_DIR,
    BASELINE_PORT,
    CANDIDATE_PORT,
    DATASET_JSON,
)
from eval_methodology.mvp.runner.answers import (  # noqa: E402
    generate_answers,
    load_answers,
)
from eval_methodology.mvp.runner.sidecar import SidecarHandle, start_sidecar  # noqa: E402


def _load_split_items(
    dataset_path: Path,
    split: str,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    data = json.loads(dataset_path.read_text(encoding="utf-8"))
    items = sorted(
        (
            item
            for item in data["items"]
            if split == "full" or item.get("split") == split
        ),
        key=lambda item: item["id"],
    )
    return items[:limit] if limit is not None else items


def _evidence_for_crec(item: dict[str, Any]) -> list[dict[str, Any]]:
    gold = item.get("gold") or {}
    if not isinstance(gold, dict) or gold.get("gold_claim_status") != "supported":
        return []
    review = gold.get("human_review")
    if isinstance(review, dict) and review.get("confirmed") is False:
        return []  # human-rejected gold never enters the CRec denominator
    evidence = gold.get("evidence") or []
    return list(evidence) if isinstance(evidence, list) else []


def _gold_confirmed(item: dict[str, Any]) -> bool:
    gold = item.get("gold") or {}
    review = gold.get("human_review") if isinstance(gold, dict) else None
    return isinstance(review, dict) and review.get("confirmed") is True


def _gold_claim_status(item: dict[str, Any]) -> str:
    gold = item.get("gold") or {}
    return str(gold.get("gold_claim_status") or "") if isinstance(gold, dict) else ""


def _skipped_judge() -> JudgeResult:
    return JudgeResult(None, None, 0, 0, False, "judge skipped", "", "", gold_evidence_coverages={})


def metrics_from_answers(
    answers: dict[str, dict[str, Any]],
    items: list[dict[str, Any]],
    *,
    use_llm_judge: bool,
    cache: JudgeCache | None = None,
) -> dict[str, Any]:
    """Compute per-question and aggregate metrics from answer checkpoints.

    Args:
        answers: Answer records keyed by qid.
        items: Dataset items in evaluation order.
        use_llm_judge: Whether to compute Faith and CitP.
        cache: Optional judge cache.

    Returns:
        Serialized metric payload with raw per-question records.
    """
    cache = cache or JudgeCache()
    per_question: list[PerQuestionMetrics] = []
    raw: list[dict[str, Any]] = []
    models: dict[str, str] = {}
    judge_models: set[str] = set()

    for item in items:
        qid = str(item["id"])
        answer = answers.get(qid) or {
            "id": qid,
            "status": "error",
            "error": {"type": "MissingAnswer", "message": "answer checkpoint missing"},
        }
        if answer.get("status") != "ok":
            metric = per_question_from_parts(
                question_id=qid,
                faith=None,
                citp=None,
                judge_failed=False,
                evidence_locators=[],
                context_chunk_ids=[],
                context_chunks=[],
                unresolved_refs=None,
                resolved_refs=None,
                gold_claim_status=_gold_claim_status(item),
                elapsed_ms=answer.get("elapsed_ms"),
                status="error",
                notes=json.dumps(answer.get("error"), ensure_ascii=False),
            )
            judge = _skipped_judge()
        else:
            gold_ev = _evidence_for_crec(item) if use_llm_judge else []
            judge = (
                judge_question(
                    question=str(item["question"]),
                    answer=str(answer.get("answer") or ""),
                    context_chunks=answer.get("context_chunks") or [],
                    cache=cache,
                    gold_evidence=gold_ev,
                )
                if use_llm_judge
                else _skipped_judge()
            )
            if judge.family and judge.resolved_model:
                models[judge.family] = judge.resolved_model
            if not judge.judge_failed and judge.resolved_model:
                judge_models.add(judge.resolved_model)
            metric = per_question_from_parts(
                question_id=qid,
                faith=judge.faith,
                citp=judge.citp,
                judge_failed=judge.judge_failed,
                evidence_locators=_evidence_for_crec(item),
                context_chunk_ids=answer.get("context_chunk_ids") or [],
                context_chunks=answer.get("context_chunks") or [],
                unresolved_refs=answer.get("unresolved_refs"),
                resolved_refs=answer.get("resolved_refs"),
                n_claims=judge.n_claims,
                n_citations=judge.n_citations,
                gold_claim_status=_gold_claim_status(item),
                gold_confirmed=_gold_confirmed(item),
                elapsed_ms=answer.get("elapsed_ms"),
                status="judge_failed" if judge.judge_failed else "ok",
                notes=judge.fail_reason,
                llm_gold_coverages=getattr(judge, "gold_evidence_coverages", None) or None,
            )
        per_question.append(metric)
        raw.append(
            {
                "id": qid,
                "answer": answer,
                "metrics": metric.model_dump(),
                "judge": {
                    "failed": judge.judge_failed,
                    "fail_reason": judge.fail_reason,
                    "faith": judge.faith,
                    "citp": judge.citp,
                    "model": judge.resolved_model,
                    "family": judge.family,
                    "gold_evidence_coverages": getattr(judge, "gold_evidence_coverages", {}) or {},
                },
            }
        )

    return {
        "n": len(items),
        "aggregate": aggregate(per_question).model_dump(),
        "per_question": [metric.model_dump() for metric in per_question],
        "raw": raw,
        "resolved_models": models,
        "judge_models": sorted(judge_models),
    }


def eval_on_sidecar(
    handle: SidecarHandle,
    items: list[dict[str, Any]],
    run_dir: Path,
    *,
    use_llm_judge: bool = True,
    cache: JudgeCache | None = None,
) -> dict[str, Any]:
    """Generate answer checkpoints, then evaluate them independently."""
    generate_answers(handle, items, run_dir)
    result = metrics_from_answers(
        load_answers(run_dir),
        items,
        use_llm_judge=use_llm_judge,
        cache=cache,
    )
    result.update(
        {
            "candidate": describe_candidate(handle.candidate),
            "port": handle.port,
            "answers_dir": str(run_dir),
        }
    )
    return result


def run_variant(
    candidate: CandidateConfig,
    items: list[dict[str, Any]],
    run_dir: Path,
    *,
    port: int,
    repeats: int = 1,
    use_llm_judge: bool = True,
) -> list[dict[str, Any]]:
    """Run one sidecar variant one or more times."""
    handle = start_sidecar(candidate, port=port)
    try:
        handle.wait_ready(timeout_s=180.0)
        return [
            eval_on_sidecar(
                handle,
                items,
                run_dir / ("answers" if index == 0 else f"answers_repeat_{index + 1}"),
                use_llm_judge=use_llm_judge,
            )
            for index in range(repeats)
        ]
    finally:
        handle.stop()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate one MVP sidecar variant")
    parser.add_argument("--dataset", type=Path, default=DATASET_JSON)
    parser.add_argument("--split", default="dev")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--variant", choices=("baseline", "candidate"), default="baseline")
    parser.add_argument("--no-judge", action="store_true")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)

    items = _load_split_items(args.dataset, args.split, args.limit)
    if not items:
        raise SystemExit(f"no items in split={args.split}")
    candidate = (
        baseline_candidate()
        if args.variant == "baseline"
        else treatment_candidate({"retrieval_auto_cross_ref_closure": True})
    )
    port = BASELINE_PORT if args.variant == "baseline" else CANDIDATE_PORT
    run_dir = ARTIFACTS_DIR / f"eval_{args.variant}_{args.split}"
    payload = run_variant(
        candidate,
        items,
        run_dir,
        port=port,
        use_llm_judge=not args.no_judge,
    )[0]
    out = args.out or (run_dir / "payload.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
