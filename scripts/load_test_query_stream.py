"""Lightweight load test for POST /api/v1/query/stream."""
from __future__ import annotations

import argparse
import asyncio
import statistics
import time
from dataclasses import dataclass

import httpx


DEFAULT_QUESTION = "欧洲规范 EN 1992-1-1 第 6.2.3 节关于剪切的计算公式是什么？"


@dataclass
class RequestResult:
    elapsed_seconds: float | None
    error: str | None = None

    @property
    def succeeded(self) -> bool:
        return self.elapsed_seconds is not None and self.error is None


def _percentile(values: list[float], percentile: float) -> float:
    """Return a nearest-rank percentile for small load-test samples."""
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]
    rank = (len(values) - 1) * percentile
    lower = int(rank)
    upper = min(lower + 1, len(values) - 1)
    fraction = rank - lower
    return values[lower] + (values[upper] - values[lower]) * fraction


async def _run_one_request(
    client: httpx.AsyncClient,
    url: str,
    question: str,
) -> RequestResult:
    started_at = time.perf_counter()
    try:
        async with client.stream(
            "POST",
            url,
            json={"question": question, "stream": True},
        ) as response:
            response.raise_for_status()
            saw_done = False
            async for line in response.aiter_lines():
                if line.strip() == "event: done":
                    saw_done = True
                    break
            if not saw_done:
                return RequestResult(None, "stream ended before event: done")
        return RequestResult(time.perf_counter() - started_at)
    except Exception as exc:
        return RequestResult(None, str(exc))


async def _worker(
    worker_id: int,
    args: argparse.Namespace,
    results: list[RequestResult],
) -> None:
    if args.ramp_up > 0:
        await asyncio.sleep(worker_id * args.ramp_up)
    headers = {"Authorization": f"Bearer {args.token}"}
    timeout = httpx.Timeout(args.timeout)
    async with httpx.AsyncClient(headers=headers, timeout=timeout) as client:
        for _ in range(args.requests_per_user):
            results.append(await _run_one_request(client, args.url, args.question))


def _print_summary(
    args: argparse.Namespace,
    results: list[RequestResult],
    elapsed_total: float,
) -> None:
    successes = [result.elapsed_seconds for result in results if result.succeeded]
    latencies = sorted(value for value in successes if value is not None)
    fail_count = len(results) - len(latencies)
    total_requests = args.concurrency * args.requests_per_user
    exception_rate = (fail_count / total_requests * 100.0) if total_requests else 0.0

    print("=== query/stream load test ===")
    print(f"concurrency       : {args.concurrency}")
    print(f"total requests    : {total_requests}")
    print(f"success / fail    : {len(latencies)} / {fail_count}")
    print(f"elapsed total     : {elapsed_total:.2f} s")
    print(
        "latency p50 / p95 / max / min : "
        f"{statistics.median(latencies) if latencies else 0.0:.2f} / "
        f"{_percentile(latencies, 0.95):.2f} / "
        f"{max(latencies) if latencies else 0.0:.2f} / "
        f"{min(latencies) if latencies else 0.0:.2f} s"
    )
    print(f"exception rate    : {exception_rate:.1f}%")


async def _main(args: argparse.Namespace) -> None:
    results: list[RequestResult] = []
    started_at = time.perf_counter()
    await asyncio.gather(
        *(_worker(worker_id, args, results) for worker_id in range(args.concurrency))
    )
    _print_summary(args, results, time.perf_counter() - started_at)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Load test POST /api/v1/query/stream until event: done."
    )
    parser.add_argument("--url", required=True)
    parser.add_argument("--token", required=True)
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--requests-per-user", type=int, default=1)
    parser.add_argument("--question", default=DEFAULT_QUESTION)
    parser.add_argument("--timeout", type=float, default=600.0)
    parser.add_argument("--ramp-up", type=float, default=0.0)
    return parser.parse_args()


if __name__ == "__main__":
    asyncio.run(_main(_parse_args()))
