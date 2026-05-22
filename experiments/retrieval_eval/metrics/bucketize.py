"""Bucketed metric summaries."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

_SKIP_BUCKETS = {"重大修改"}


def bucket_summary(per_question: list[dict]) -> dict:
    """Return averages for category, doc span, and review bucket dimensions."""
    return {
        "category": _summarize(per_question, lambda row: row.get("category", "unknown")),
        "doc_span": _summarize(per_question, _doc_span),
        "review_bucket": _summarize(
            per_question,
            lambda row: row.get("review_bucket", "unknown"),
            skip_keys=set(),
        ),
        "included_review_bucket": _summarize(
            per_question,
            lambda row: row.get("review_bucket", "unknown"),
            skip_keys=_SKIP_BUCKETS,
        ),
    }


def _summarize(
    rows: list[dict],
    key_fn,
    skip_keys: set[str] | None = None,
) -> dict[str, dict[str, Any]]:
    skip_keys = skip_keys or set()
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        key = str(key_fn(row) or "unknown")
        if key in skip_keys:
            continue
        grouped[key].append(row)

    return {key: _average_metrics(bucket_rows) for key, bucket_rows in sorted(grouped.items())}


def _average_metrics(rows: list[dict]) -> dict[str, Any]:
    metric_names: set[str] = set()
    for row in rows:
        metric_names.update((row.get("metrics") or {}).keys())

    averaged: dict[str, Any] = {"count": len(rows)}
    for name in sorted(metric_names):
        values = [
            value
            for row in rows
            for value in [(row.get("metrics") or {}).get(name)]
            if isinstance(value, int | float)
        ]
        if values:
            averaged[name] = round(sum(values) / len(values), 4)
    return averaged


def _doc_span(row: dict) -> str:
    expected_docs = row.get("expected_documents") or []
    return "multi_doc" if len(expected_docs) > 1 else "single_doc"
