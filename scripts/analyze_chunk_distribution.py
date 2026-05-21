"""Analyze token distribution for indexed chunks.

Reads chunk documents from Elasticsearch and writes a Markdown report with
embedding and rerank token-count percentiles.
"""
from __future__ import annotations

import asyncio
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.config import PipelineConfig  # noqa: E402
from shared.elasticsearch_client import build_async_elasticsearch  # noqa: E402
from shared.tokenizers import count_for_embedding, count_for_rerank  # noqa: E402

_PAGE_SIZE = 500
_THRESHOLDS = (1024, 2048, 8192)


async def main() -> None:
    config = PipelineConfig()
    rows = await _fetch_chunk_rows(config)
    report = _build_report(rows, config)
    output_dir = Path("reports")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"chunk_token_distribution_{datetime.now():%Y%m%d}.md"
    output_path.write_text(report, encoding="utf-8")
    print(f"wrote {output_path}")


async def _fetch_chunk_rows(config: PipelineConfig) -> list[dict[str, Any]]:
    es = build_async_elasticsearch(config.es_url)
    rows: list[dict[str, Any]] = []
    try:
        if not await es.indices.exists(index=config.es_index):
            return rows

        search_after: list[Any] | None = None
        while True:
            body: dict[str, Any] = {
                "size": _PAGE_SIZE,
                "sort": [{"chunk_id": "asc"}],
                "_source": [
                    "chunk_id",
                    "embedding_text",
                    "content",
                    "element_type",
                    "source",
                ],
            }
            if search_after:
                body["search_after"] = search_after

            response = await es.search(index=config.es_index, body=body)
            hits = response.get("hits", {}).get("hits", [])
            if not hits:
                break

            for hit in hits:
                source = hit.get("_source", {})
                text = source.get("embedding_text") or source.get("content") or ""
                rows.append(
                    {
                        "chunk_id": source.get("chunk_id") or hit.get("_id", ""),
                        "source": source.get("source", ""),
                        "element_type": source.get("element_type", "unknown"),
                        "embedding_text": text,
                    }
                )
            search_after = hits[-1].get("sort")
    finally:
        await es.close()
    return rows


def _build_report(rows: list[dict[str, Any]], config: PipelineConfig) -> str:
    now = datetime.now().isoformat(timespec="seconds")
    lines = [
        "# Chunk Token Distribution",
        "",
        f"- Generated: {now}",
        f"- Elasticsearch index: `{config.es_index}`",
        f"- Total chunks: {len(rows)}",
        "",
    ]
    if not rows:
        lines.append("No chunks found.")
        return "\n".join(lines) + "\n"

    enriched = [_with_token_counts(row, config) for row in rows]
    lines.extend(_summary_section("All chunks", enriched))

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in enriched:
        grouped[row["element_type"]].append(row)

    for element_type in sorted(grouped):
        lines.extend(_summary_section(f"element_type={element_type}", grouped[element_type]))

    return "\n".join(lines) + "\n"


def _with_token_counts(row: dict[str, Any], config: PipelineConfig) -> dict[str, Any]:
    text = row["embedding_text"]
    embedding_tokens, embedding_estimate = count_for_embedding(
        text,
        config.embedding_model,
    )
    rerank_tokens, rerank_estimate = count_for_rerank(
        text,
        config.rerank_model,
    )
    return {
        **row,
        "embedding_tokens": embedding_tokens,
        "embedding_estimate": embedding_estimate,
        "rerank_tokens": rerank_tokens,
        "rerank_estimate": rerank_estimate,
    }


def _summary_section(title: str, rows: list[dict[str, Any]]) -> list[str]:
    embedding_values = [row["embedding_tokens"] for row in rows]
    rerank_values = [row["rerank_tokens"] for row in rows]
    rerank_estimates = sum(1 for row in rows if row["rerank_estimate"])
    embedding_estimates = sum(1 for row in rows if row["embedding_estimate"])

    return [
        f"## {title}",
        "",
        f"- Count: {len(rows)}",
        f"- Embedding estimates: {embedding_estimates}",
        f"- Rerank estimates: {rerank_estimates}",
        "",
        "| metric | p50 | p90 | p95 | p99 | max | >1024 | >2048 | >8192 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
        _metric_row("embedding", embedding_values),
        _metric_row("rerank", rerank_values),
        "",
    ]


def _metric_row(label: str, values: list[int]) -> str:
    return (
        f"| {label} | {_percentile(values, 50)} | {_percentile(values, 90)} | "
        f"{_percentile(values, 95)} | {_percentile(values, 99)} | {max(values)} | "
        f"{_over_threshold(values, 1024)} | {_over_threshold(values, 2048)} | "
        f"{_over_threshold(values, 8192)} |"
    )


def _percentile(values: list[int], percentile: int) -> int:
    ordered = sorted(values)
    if not ordered:
        return 0
    index = round((len(ordered) - 1) * percentile / 100)
    return ordered[index]


def _over_threshold(values: list[int], threshold: int) -> str:
    count = sum(1 for value in values if value > threshold)
    ratio = count / len(values) if values else 0
    return f"{count} ({ratio:.1%})"


if __name__ == "__main__":
    asyncio.run(main())
