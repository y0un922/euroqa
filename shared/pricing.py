"""Official model prices for converting provider usage into CNY.

Billing tokens always come from the provider `usage` object. Snapshot prices
cover models this project actually runs. Bailian models missing from the
snapshot are resolved from GET /api/v1/models so a newly switched model does
not stay unpriced.
"""

from __future__ import annotations

import os
from typing import Mapping

import structlog

logger = structlog.get_logger()

# Snapshot of Alibaba Cloud Model Studio Beijing list prices, 2026-08-19.
# Source: https://help.aliyun.com/zh/model-studio/model-pricing
# Live cache hit prices come from GET /api/v1/models when the snapshot misses.
# Unit: CNY per million tokens. Output for thinking models includes reasoning.
_BAILIAN_PRICES: dict[str, dict[str, float]] = {
    "qwen3.6-flash": {"input": 1.2, "output": 7.2},
    "qwen3.6-flash-2026-04-16": {"input": 1.2, "output": 7.2},
    "qwen3.7-flash": {"input": 0.2, "output": 0.8},
    "qwen3.7-flash-2026-07-15": {"input": 0.2, "output": 0.8},
    "qwen3.5-flash": {"input": 0.2, "output": 2.0},
    "qwen-flash": {"input": 0.15, "output": 1.5},
    "qwen3.6-plus": {"input": 2.0, "output": 12.0},
    "qwen3.5-plus": {"input": 0.8, "output": 4.8},
    "qwen-plus": {"input": 0.8, "output": 2.0},
    "qwen3-rerank": {"input": 0.5, "output": 0.0},
    "qwen3-vl-rerank": {"input": 0.5, "output": 0.0},
    "gte-rerank-v2": {"input": 0.8, "output": 0.0},
    "qwen3.7-text-embedding": {"input": 0.5, "output": 0.0},
    "text-embedding-v4": {"input": 0.5, "output": 0.0},
    "deepseek-v4-flash": {"input": 1.0, "output": 2.0, "cache_input": 0.2},
    "deepseek-v4-flash-0731": {"input": 1.5, "output": 4.5, "cache_input": 0.15},
    "deepseek-v4-pro": {"input": 12.0, "output": 24.0},
    "deepseek-v4-pro-0813": {"input": 4.5, "output": 13.5},
}

_SILICONFLOW_PRICES: dict[str, dict[str, float]] = {
    "BAAI/bge-m3": {"input": 0.0, "output": 0.0},
    "Pro/BAAI/bge-m3": {"input": 0.0, "output": 0.0},
}

_DEEPSEEK_PRICES: dict[str, dict[str, float]] = {
    "deepseek-v4-flash": {"input": 1.5, "output": 4.5, "cache_input": 0.05},
    "deepseek-v4-pro": {"input": 4.5, "output": 13.5, "cache_input": 0.15},
    "deepseek-chat": {"input": 2.0, "output": 3.0},
}

PROJECT_MODELS: tuple[tuple[str, str], ...] = (
    ("bailian", "qwen3.6-flash"),
    ("bailian", "qwen3-rerank"),
    ("bailian", "deepseek-v4-flash"),
    ("bailian", "deepseek-v4-pro"),
    ("siliconflow", "BAAI/bge-m3"),
    ("deepseek", "deepseek-chat"),
    ("deepseek", "deepseek-v4-flash"),
)

_PRICE_SOURCE = "bailian_official_2026-08-19"
_LIVE_CACHE: dict[str, dict[str, float] | None] = {}
_BAILIAN_MODELS_URL = "https://dashscope.aliyuncs.com/api/v1/models"


def price_source() -> str:
    """Return the snapshot identifier attached to cost reports."""
    return _PRICE_SOURCE


def clear_live_price_cache() -> None:
    """Drop cached live Bailian lookups. Tests use this between cases."""
    _LIVE_CACHE.clear()


def price_for_model(
    model: str,
    *,
    vendor: str = "",
) -> dict[str, float | str] | None:
    """Return published input/output CNY per million tokens, if known."""
    snapshot = _snapshot_price(model, vendor)
    if snapshot is not None:
        return _public_price(snapshot)
    live = _live_bailian_price(model, vendor)
    if live is not None:
        return _public_price(live)
    return None


def parse_bailian_model_prices(
    payload: Mapping[str, object],
    model: str,
) -> dict[str, float] | None:
    """Extract CNY/million prices from a Bailian GET /api/v1/models payload."""
    output = payload.get("output")
    models = output.get("models") if isinstance(output, Mapping) else None
    if not isinstance(models, list):
        return None
    for item in models:
        if not isinstance(item, Mapping) or item.get("model") != model:
            continue
        parsed = _parse_price_ranges(item.get("prices"))
        if parsed is not None:
            return parsed
    return None


def cost_cny(
    *,
    model: str,
    vendor: str,
    usage: Mapping[str, int] | None,
) -> float | None:
    """Return CNY for one usage blob, or None when the model has no list price."""
    price = price_for_model(model, vendor=vendor)
    if price is None or not usage:
        return None
    input_tokens = int(usage.get("input_tokens") or 0)
    output_tokens = int(usage.get("output_tokens") or 0)
    cached_tokens = int(usage.get("cached_tokens") or 0)
    input_price = float(price["input"])
    output_price = float(price["output"])
    if "cache_input" in price and cached_tokens > 0:
        uncached = max(0, input_tokens - cached_tokens)
        input_cost = uncached * input_price + cached_tokens * float(price["cache_input"])
    else:
        input_cost = input_tokens * input_price
    return (input_cost + output_tokens * output_price) / 1_000_000


def _snapshot_price(model: str, vendor: str) -> dict[str, float] | None:
    table = _table_for_vendor(vendor)
    exact = table.get(model) or table.get(model.lower())
    if exact is None:
        exact = _prefix_match(table, model)
    return dict(exact) if exact is not None else None


def _public_price(exact: Mapping[str, float]) -> dict[str, float | str]:
    priced: dict[str, float | str] = {
        "input": float(exact["input"]),
        "output": float(exact["output"]),
        "unit": "CNY_per_million",
    }
    if "cache_input" in exact:
        priced["cache_input"] = float(exact["cache_input"])
    return priced


def _live_bailian_price(model: str, vendor: str) -> dict[str, float] | None:
    if vendor not in {"", "bailian", "dashscope"}:
        return None
    if model in _LIVE_CACHE:
        return _LIVE_CACHE[model]
    payload = _fetch_bailian_model_payload(model)
    parsed = parse_bailian_model_prices(payload, model) if payload else None
    _LIVE_CACHE[model] = parsed
    if parsed is None:
        logger.warning("bailian_model_price_missing", model=model, vendor=vendor)
    return parsed


def _fetch_bailian_model_payload(model: str) -> dict[str, object] | None:
    api_key = _bailian_api_key()
    if not api_key or not model.strip():
        return None
    try:
        import httpx

        response = httpx.get(
            _BAILIAN_MODELS_URL,
            params={"model": model.strip(), "page_size": 5},
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            timeout=8.0,
        )
        response.raise_for_status()
        payload = response.json()
    except Exception:
        logger.warning("bailian_model_price_lookup_failed", model=model, exc_info=True)
        return None
    return payload if isinstance(payload, dict) else None


def _bailian_api_key() -> str:
    for name in ("DASHSCOPE_API_KEY", "LLM_API_KEY", "RERANK_API_KEY"):
        value = os.getenv(name, "").strip()
        if value:
            return value
    return ""


def _parse_price_ranges(ranges: object) -> dict[str, float] | None:
    if not isinstance(ranges, list) or not ranges:
        return None
    chosen = None
    for item in ranges:
        if isinstance(item, Mapping) and item.get("range_name") == "Default":
            chosen = item
            break
    if chosen is None:
        first = ranges[0]
        chosen = first if isinstance(first, Mapping) else None
    if chosen is None:
        return None
    rows = chosen.get("prices")
    if not isinstance(rows, list):
        return None
    parsed: dict[str, float] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        kind = str(row.get("type") or "")
        raw_price = row.get("price")
        try:
            amount = float(raw_price)
        except (TypeError, ValueError):
            continue
        if kind == "input_token" and "input" not in parsed:
            parsed["input"] = amount
        elif kind == "output_token" and "output" not in parsed:
            parsed["output"] = amount
        elif kind == "input_token_cache" and "cache_input" not in parsed:
            parsed["cache_input"] = amount
    if "input" in parsed and "output" in parsed:
        return parsed
    return None


def _table_for_vendor(vendor: str) -> dict[str, dict[str, float]]:
    if vendor == "siliconflow":
        return _SILICONFLOW_PRICES
    if vendor == "deepseek":
        return _DEEPSEEK_PRICES
    if vendor in {"", "bailian", "dashscope"}:
        return _BAILIAN_PRICES
    return {}


def _prefix_match(
    table: dict[str, dict[str, float]],
    model: str,
) -> dict[str, float] | None:
    normalized = (model or "").strip()
    if not normalized:
        return None
    for key, price in table.items():
        if normalized == key or normalized.startswith(f"{key}-"):
            return price
    return None
