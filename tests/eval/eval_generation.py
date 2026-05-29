"""生成侧活跑评测脚本。

需 Milvus+ES+LLM 在线,周期性手动跑,非 CI 门禁。
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import structlog

logger = structlog.get_logger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
EVAL_DIR = Path(__file__).parent
DEFAULT_QUESTIONS_PATH = EVAL_DIR / "test_questions.json"
DEFAULT_OUTPUT_PATH = EVAL_DIR / "baselines" / "generation_baseline.json"
DEFAULT_API_URL = "http://127.0.0.1:18080"
DEFAULT_TIMEOUT_SECONDS = 600.0
CITATION_PATTERN = re.compile(r"\[Ref-(\d+)\]")


def _load_questions(path: Path) -> list[dict[str, Any]]:
    """Load the eval question set from disk."""
    logger.info("generation_eval_load_questions", path=str(path))
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError(f"Expected a JSON array at {path}")
    return data


def _stream_url(api_url: str) -> str:
    """Build the query stream endpoint URL from a base API URL."""
    return api_url.rstrip("/") + "/api/v1/query/stream"


def _parse_sse_line_events(lines: list[str]) -> list[tuple[str, str]]:
    """Parse SSE lines into event/data pairs."""
    events: list[tuple[str, str]] = []
    event_name = "message"
    data_lines: list[str] = []

    def flush() -> None:
        nonlocal event_name, data_lines
        if data_lines:
            events.append((event_name, "\n".join(data_lines)))
        event_name = "message"
        data_lines = []

    for raw_line in lines:
        line = raw_line.rstrip("\r")
        if line == "":
            flush()
            continue
        if line.startswith(":"):
            continue
        if line.startswith("event:"):
            event_name = line.split(":", 1)[1].strip()
        elif line.startswith("data:"):
            data_lines.append(line.split(":", 1)[1].lstrip())
    flush()
    return events


async def _query_stream(
    client: httpx.AsyncClient,
    url: str,
    question: str,
) -> tuple[str, dict[str, Any]]:
    """Call POST /api/v1/query/stream and return full answer text plus done payload."""
    answer_parts: list[str] = []
    done_payload: dict[str, Any] | None = None
    pending_lines: list[str] = []

    logger.info("generation_eval_query_start", question=question)
    async with client.stream(
        "POST",
        url,
        json={"question": question, "stream": True},
    ) as response:
        response.raise_for_status()
        async for line in response.aiter_lines():
            pending_lines.append(line)
            if line != "":
                continue

            for event_name, data_text in _parse_sse_line_events(pending_lines):
                payload = json.loads(data_text)
                if event_name == "chunk":
                    text = payload.get("text")
                    if isinstance(text, str):
                        answer_parts.append(text)
                elif event_name == "done":
                    if not isinstance(payload, dict):
                        raise ValueError("done event payload must be a JSON object")
                    done_payload = payload
                    answer = payload.get("normalized_answer") or payload.get("answer")
                    if isinstance(answer, str):
                        return answer, done_payload
                    return "".join(answer_parts), done_payload
                elif event_name == "error":
                    raise RuntimeError(f"stream error event: {payload}")
            pending_lines = []

    if pending_lines:
        for event_name, data_text in _parse_sse_line_events(pending_lines):
            payload = json.loads(data_text)
            if event_name == "done" and isinstance(payload, dict):
                done_payload = payload

    if done_payload is None:
        raise RuntimeError("stream ended before done event")
    answer = done_payload.get("normalized_answer") or done_payload.get("answer")
    return answer if isinstance(answer, str) else "".join(answer_parts), done_payload


def _source_identity(source: dict[str, Any]) -> tuple[Any, ...]:
    """Return a stable identity tuple for a source payload."""
    return (
        source.get("document_id") or source.get("docId"),
        source.get("file"),
        source.get("clause"),
        source.get("locator_text") or source.get("locatorText"),
        source.get("original_text") or source.get("originalText"),
    )


def _citation_accuracy(answer: str, sources: list[Any]) -> tuple[float, list[int]]:
    """Check citation numbers are in range and map to an existing done source."""
    source_dicts = [source for source in sources if isinstance(source, dict)]
    source_identities = {_source_identity(source) for source in source_dicts}
    citations = [int(match) for match in CITATION_PATTERN.findall(answer)]
    invalid = [
        number
        for number in citations
        if number < 1
        or number > len(sources)
        or not isinstance(sources[number - 1], dict)
        or _source_identity(sources[number - 1]) not in source_identities
    ]
    return (1.0 if not invalid else 0.0), invalid


def _key_clause_hit_rate(answer: str, expected_keywords: list[str]) -> tuple[float, list[str]]:
    """Return expected keyword hit rate in generated answer text."""
    if not expected_keywords:
        return 1.0, []
    lowered_answer = answer.lower()
    hits = [keyword for keyword in expected_keywords if keyword.lower() in lowered_answer]
    return len(hits) / len(expected_keywords), hits


def _groundedness_match(
    groundedness: str | None,
    expected_mode: str | None,
) -> bool | None:
    """Compare stream done groundedness with the expected mode when declared."""
    if expected_mode is None:
        return None
    return groundedness == expected_mode


async def evaluate(
    *,
    api_url: str = DEFAULT_API_URL,
    questions_path: Path = DEFAULT_QUESTIONS_PATH,
    output_path: Path = DEFAULT_OUTPUT_PATH,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Run generation-side live evaluation and persist the baseline JSON."""
    questions = _load_questions(questions_path)
    url = _stream_url(api_url)
    results: list[dict[str, Any]] = []
    citation_hits = 0
    groundedness_hits = 0
    groundedness_measured = 0
    total_key_clause_hit_rate = 0.0
    successful_questions = 0

    async with httpx.AsyncClient(timeout=httpx.Timeout(timeout_seconds)) as client:
        for question_spec in questions:
            qid = question_spec["id"]
            question = question_spec["question"]
            expected_keywords = question_spec.get("expected_keywords", [])
            expected_mode = question_spec.get("expected_mode")
            try:
                answer, done_payload = await _query_stream(client, url, question)
            except Exception as exc:
                logger.warning(
                    "generation_eval_question_failed",
                    question_id=qid,
                    error=str(exc),
                    exc_info=True,
                )
                results.append(
                    {
                        "id": qid,
                        "question": question,
                        "category": question_spec.get("category"),
                        "expected_mode": expected_mode,
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )
                print(f"[ERROR] {qid}: {type(exc).__name__}: {exc}")
                continue

            successful_questions += 1
            sources = done_payload.get("sources", [])
            if not isinstance(sources, list):
                sources = []
            citation_score, invalid_citations = _citation_accuracy(answer, sources)
            citation_hits += int(citation_score == 1.0)

            groundedness = done_payload.get("groundedness")
            groundedness_score = _groundedness_match(
                groundedness if isinstance(groundedness, str) else None,
                expected_mode if isinstance(expected_mode, str) else None,
            )
            if groundedness_score is not None:
                groundedness_measured += 1
                groundedness_hits += int(groundedness_score)

            keyword_rate, hit_keywords = _key_clause_hit_rate(answer, expected_keywords)
            total_key_clause_hit_rate += keyword_rate

            logger.info(
                "generation_eval_question_complete",
                question_id=qid,
                citation_accuracy=citation_score,
                groundedness_match=groundedness_score,
                key_clause_hit_rate=keyword_rate,
                source_count=len(sources),
            )
            status = "PASS" if citation_score == 1.0 and groundedness_score is not False else "FAIL"
            print(
                f"[{status}] {qid}: citation_accuracy={citation_score:.2f} | "
                f"groundedness_match={groundedness_score} | "
                f"key_clause_hit_rate={keyword_rate:.2f}"
            )

            results.append(
                {
                    "id": qid,
                    "question": question,
                    "category": question_spec.get("category"),
                    "expected_mode": expected_mode,
                    "groundedness": groundedness,
                    "groundedness_match": groundedness_score,
                    "citation_accuracy": citation_score,
                    "invalid_citations": invalid_citations,
                    "key_clause_hit_rate": round(keyword_rate, 4),
                    "expected_keywords": expected_keywords,
                    "hit_keywords": hit_keywords,
                    "answer_chars": len(answer),
                    "source_count": len(sources),
                }
            )

    total_questions = len(questions)
    metrics = {
        "citation_accuracy": round(citation_hits / successful_questions, 4)
        if successful_questions else 0.0,
        "groundedness_match": round(groundedness_hits / groundedness_measured, 4)
        if groundedness_measured else None,
        "groundedness_match_measured_questions": groundedness_measured,
        "key_clause_hit_rate": round(total_key_clause_hit_rate / successful_questions, 4)
        if successful_questions else 0.0,
        "pass_rate": round(successful_questions / total_questions, 4)
        if total_questions else 0.0,
        "total": total_questions,
        "measured_questions": successful_questions,
    }
    summary = {
        "metadata": {
            "baseline_version": "generation-live-v0.1.0",
            "created_at": datetime.now(UTC).date().isoformat(),
            "git_sha": _git_sha(),
            "note": "生成侧活跑结果依赖在线 Milvus、Elasticsearch 和 LLM，不作为 CI 门禁。",
        },
        "config": {
            "api_url": api_url,
            "questions_path": str(questions_path),
            "timeout_seconds": timeout_seconds,
        },
        "metrics": metrics,
        "per_question": results,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    logger.info("generation_eval_saved", output_path=str(output_path), metrics=metrics)
    print(f"详细结果已保存到: {output_path}")
    return summary


def _git_sha() -> str | None:
    """Read the current git SHA without failing eval output."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=PROJECT_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="生成侧 query/stream 活跑评测")
    parser.add_argument("--api-url", default=DEFAULT_API_URL)
    parser.add_argument(
        "--questions-path",
        type=Path,
        default=DEFAULT_QUESTIONS_PATH,
    )
    parser.add_argument(
        "--output-path",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
    )
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_SECONDS)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    asyncio.run(
        evaluate(
            api_url=args.api_url,
            questions_path=args.questions_path,
            output_path=args.output_path,
            timeout_seconds=args.timeout,
        )
    )


if __name__ == "__main__":
    main()
