"""CLI for running the retrieval evaluation baseline."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from server.config import ServerConfig  # noqa: E402
from server.deps import get_glossary  # noqa: E402

from experiments.retrieval_eval.dataset.schema import load_questions  # noqa: E402
from experiments.retrieval_eval.runner import run_evaluation  # noqa: E402
from experiments.retrieval_eval.trace.wrapper import TracingHybridRetriever  # noqa: E402


async def _main() -> None:
    args = _parse_args()
    questions = load_questions(args.questions)
    if args.exp == "smoke":
        questions = questions[: min(5, len(questions))]
    config = _build_config(args)
    retriever = TracingHybridRetriever(
        config,
        disable_rerank=args.exp == "no-rerank",
        disable_cap=args.exp == "no-cap",
        rerank_fill_from_candidates=args.exp in ("rerank-fill", "rerank-en-fill"),
        multi_query_max_rerank=args.exp == "multi-query-max-rerank",
    )
    try:
        result = await run_evaluation(
            questions=questions,
            retriever=retriever,
            glossary=get_glossary(),
            config=config,
            top_k=args.top_k,
            exp=args.exp,
        )
    finally:
        await retriever.close()

    output = args.output or _default_output_path(args.exp)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Wrote {output}")
    print(json.dumps(result["metrics"], ensure_ascii=False, indent=2))


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--questions",
        type=Path,
        default=Path("experiments/retrieval_eval/dataset/test_questions_v2.json"),
    )
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument(
        "--exp",
        choices=[
            "baseline",
            "smoke",
            "high-recall",
            "no-rerank",
            "no-cap",
            "rerank-english",
            "rerank-en-fill",
            "rerank-fill",
            "multi-query-max-rerank",
            "rerank-translated-original",
        ],
        default="baseline",
    )
    return parser.parse_args()


def _build_config(args: argparse.Namespace) -> ServerConfig:
    config = ServerConfig()
    if args.exp == "smoke":
        return config.model_copy(
            update={"vector_top_k": 10, "bm25_top_k": 10, "rerank_top_n": args.top_k}
        )
    if args.exp == "high-recall":
        return config.model_copy(
            update={
                "vector_top_k": 80,
                "bm25_top_k": 80,
                "rerank_top_n": max(args.top_k, 20),
            }
        )
    if args.exp == "no-rerank":
        return config.model_copy(update={"rerank_top_n": args.top_k})
    return config


def _default_output_path(exp: str) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return Path(f"experiments/retrieval_eval/results/{exp}_{stamp}.json")


if __name__ == "__main__":
    asyncio.run(_main())
