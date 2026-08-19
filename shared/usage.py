"""Collect provider-reported token usage for billing.

Local tokenizers are not a billing source. Only `usage` fields returned by
DashScope compatible-mode, OpenAI-compatible embeddings/rerank, or the Agents
SDK are recorded.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from typing import Any

from shared.pricing import cost_cny, price_source

_USAGE_INT_KEYS = (
    "requests",
    "input_tokens",
    "output_tokens",
    "total_tokens",
    "cached_tokens",
    "reasoning_tokens",
)

_collector: ContextVar["UsageLedger | None"] = ContextVar(
    "usage_collector",
    default=None,
)


@dataclass
class UsageItem:
    """One billed model call, or a merged group of calls to the same model."""

    vendor: str
    model: str
    usage: dict[str, int] = field(default_factory=dict)


@dataclass
class UsageLedger:
    """In-request accumulator of official usage blobs."""

    items: list[UsageItem] = field(default_factory=list)

    def add(self, *, vendor: str, model: str, usage: Mapping[str, int]) -> None:
        cleaned = _clean_usage(usage)
        if not cleaned:
            return
        cleaned["requests"] = cleaned.get("requests", 0) or 1
        if "total_tokens" not in cleaned:
            total = cleaned.get("input_tokens", 0) + cleaned.get("output_tokens", 0)
            if total:
                cleaned["total_tokens"] = total
        self.items.append(UsageItem(vendor=vendor, model=model, usage=cleaned))

    def totals(self) -> dict[str, int]:
        merged: dict[str, int] = {}
        for item in self.items:
            merged = merge_usage(merged, item.usage)
        return merged

    def report(self) -> dict[str, Any]:
        priced: list[dict[str, Any]] = []
        unpriced: list[dict[str, Any]] = []
        total_cny = 0.0
        for vendor, model, blob in _merge_items(self.items):
            row = {
                "vendor": vendor,
                "model": model,
                **blob,
            }
            amount = cost_cny(model=model, vendor=vendor, usage=blob)
            if amount is None:
                unpriced.append(row)
                continue
            row["cny"] = round(amount, 8)
            priced.append(row)
            total_cny += amount
        return {
            "usage": self.totals(),
            "cost": {
                "currency": "CNY",
                "total": round(total_cny, 8),
                "price_source": price_source(),
                "items": priced,
                "unpriced": unpriced,
            },
        }


def extract_usage(source: object | None) -> dict[str, int]:
    """Normalize a response, payload, or usage object into billing counters."""
    if source is None:
        return {}
    raw = _unwrap_usage(source)
    if raw is None:
        return {}
    values: dict[str, int] = {}
    _put_int(values, "requests", _field(raw, "requests"))
    _put_int(
        values,
        "input_tokens",
        _field(raw, "input_tokens", "prompt_tokens"),
    )
    _put_int(
        values,
        "output_tokens",
        _field(raw, "output_tokens", "completion_tokens"),
    )
    _put_int(values, "total_tokens", _field(raw, "total_tokens"))
    details_in = _field(raw, "input_tokens_details", "prompt_tokens_details")
    _put_int(values, "cached_tokens", _field(details_in, "cached_tokens"))
    details_out = _field(raw, "output_tokens_details", "completion_tokens_details")
    _put_int(values, "reasoning_tokens", _field(details_out, "reasoning_tokens"))
    if "total_tokens" not in values:
        total = values.get("input_tokens", 0) + values.get("output_tokens", 0)
        if total:
            values["total_tokens"] = total
    return values


def merge_usage(*parts: Mapping[str, int] | None) -> dict[str, int]:
    """Sum integer usage fields across multiple official usage blobs."""
    merged: dict[str, int] = {}
    for part in parts:
        if not part:
            continue
        for key in _USAGE_INT_KEYS:
            value = part.get(key)
            if isinstance(value, bool) or not isinstance(value, int):
                continue
            if value:
                merged[key] = merged.get(key, 0) + value
    return merged


@contextmanager
def collect_usage() -> Iterator[UsageLedger]:
    """Bind a ledger to the current task/request."""
    ledger = UsageLedger()
    token: Token[UsageLedger | None] = _collector.set(ledger)
    try:
        yield ledger
    finally:
        _collector.reset(token)


def record_usage(
    *,
    model: str,
    vendor: str,
    payload: object | None = None,
    usage_blob: Mapping[str, int] | None = None,
) -> dict[str, int]:
    """Record official usage when a collector is active. No-op otherwise."""
    extracted = dict(usage_blob or {}) or extract_usage(payload)
    ledger = _collector.get()
    if ledger is not None:
        ledger.add(vendor=vendor, model=model, usage=extracted)
    return extracted


def current_report() -> dict[str, Any] | None:
    """Return the active collector report, if any."""
    ledger = _collector.get()
    if ledger is None:
        return None
    return ledger.report()


def vendor_from_base_url(base_url: str) -> str:
    """Map an API base URL to a billing vendor key."""
    url = (base_url or "").lower()
    if "siliconflow" in url:
        return "siliconflow"
    if "dashscope" in url or "aliyuncs.com" in url or "bailian" in url:
        return "bailian"
    if "deepseek.com" in url:
        return "deepseek"
    return "unknown"


def _unwrap_usage(source: object) -> object | None:
    if isinstance(source, Mapping):
        nested = source.get("usage")
        if nested is not None:
            return nested
        if any(
            key in source for key in ("prompt_tokens", "input_tokens", "total_tokens")
        ):
            return source
        return None
    nested = getattr(source, "usage", None)
    if nested is not None:
        return nested
    return source


def _field(obj: object | None, *names: str) -> object:
    if obj is None:
        return None
    for name in names:
        if isinstance(obj, Mapping) and name in obj:
            return obj.get(name)
        if not isinstance(obj, Mapping):
            value = getattr(obj, name, None)
            if value is not None:
                return value
    return None


def _put_int(target: dict[str, int], key: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        return
    if value:
        target[key] = int(value)


def _clean_usage(raw: Mapping[str, int]) -> dict[str, int]:
    cleaned: dict[str, int] = {}
    for key in _USAGE_INT_KEYS:
        value = raw.get(key)
        if isinstance(value, bool) or not isinstance(value, int):
            continue
        if value:
            cleaned[key] = int(value)
    return cleaned


def _merge_items(
    items: list[UsageItem],
) -> list[tuple[str, str, dict[str, int]]]:
    grouped: dict[tuple[str, str], dict[str, int]] = {}
    order: list[tuple[str, str]] = []
    for item in items:
        key = (item.vendor, item.model)
        if key not in grouped:
            grouped[key] = {}
            order.append(key)
        grouped[key] = merge_usage(grouped[key], item.usage)
    return [(vendor, model, grouped[(vendor, model)]) for vendor, model in order]
