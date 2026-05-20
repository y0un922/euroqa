"""Run fixed spot-check queries against a local Euro_QA backend."""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEFAULT_FIXTURES = ROOT / "tests" / "fixtures" / "spot_check_queries.jsonl"


async def main() -> None:
    args = _parse_args()
    queries = _load_queries(args.fixtures)
    started = time.perf_counter()
    failures = 0

    os.environ["SPOT_CHECK_ENABLED"] = "true"
    os.environ["SPOT_CHECK_TAG"] = args.baseline_tag
    print(
        "Ensure the target backend process was started with "
        f"SPOT_CHECK_ENABLED=true SPOT_CHECK_TAG={args.baseline_tag}.",
        file=sys.stderr,
    )

    headers = {"Authorization": f"Bearer {args.token}"} if args.token else {}
    async with httpx.AsyncClient(timeout=args.timeout, headers=headers) as client:
        for item in queries:
            status = await _run_one(client, args.base_url, item)
            if status >= 400:
                failures += 1

    elapsed = time.perf_counter() - started
    print(
        json.dumps(
            {
                "queries": len(queries),
                "failures": failures,
                "elapsed_seconds": round(elapsed, 2),
                "average_seconds": round(elapsed / len(queries), 2) if queries else 0,
                "baseline_tag": args.baseline_tag,
            },
            ensure_ascii=False,
        )
    )


async def _run_one(client: httpx.AsyncClient, base_url: str, item: dict[str, Any]) -> int:
    response = await client.post(
        f"{base_url.rstrip('/')}/api/v1/query",
        json={"question": item["query"]},
    )
    return response.status_code


def _load_queries(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if stripped:
                rows.append(json.loads(stripped))
    return rows


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixtures", type=Path, default=DEFAULT_FIXTURES)
    parser.add_argument("--baseline-tag", default="baseline-v0")
    parser.add_argument("--base-url", default=os.getenv("EURO_QA_BASE_URL", "http://127.0.0.1:8000"))
    parser.add_argument("--timeout", type=float, default=600.0)
    parser.add_argument("--token", default=os.getenv("EURO_QA_TOKEN", ""))
    return parser.parse_args()


if __name__ == "__main__":
    asyncio.run(main())
