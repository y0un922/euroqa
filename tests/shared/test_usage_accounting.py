"""Official API usage is the billing source of truth, not tiktoken."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from shared import pricing, usage


def test_extract_usage_prefers_openai_compatible_server_fields():
    payload = SimpleNamespace(
        usage=SimpleNamespace(
            prompt_tokens=22,
            completion_tokens=18,
            total_tokens=40,
        )
    )

    assert usage.extract_usage(payload) == {
        "input_tokens": 22,
        "output_tokens": 18,
        "total_tokens": 40,
    }


def test_extract_usage_reads_agent_style_fields_and_details():
    payload = SimpleNamespace(
        usage=SimpleNamespace(
            requests=2,
            input_tokens=100,
            output_tokens=40,
            total_tokens=140,
            input_tokens_details=SimpleNamespace(cached_tokens=12),
            output_tokens_details=SimpleNamespace(reasoning_tokens=8),
        )
    )

    assert usage.extract_usage(payload) == {
        "requests": 2,
        "input_tokens": 100,
        "output_tokens": 40,
        "total_tokens": 140,
        "cached_tokens": 12,
        "reasoning_tokens": 8,
    }


def test_extract_usage_from_embedding_payload_dict():
    assert usage.extract_usage(
        {"usage": {"prompt_tokens": 80, "total_tokens": 80}}
    ) == {
        "input_tokens": 80,
        "total_tokens": 80,
    }


def test_extract_usage_returns_empty_when_provider_omits_usage():
    assert usage.extract_usage({"data": []}) == {}
    assert usage.extract_usage(None) == {}


def test_merge_usage_sums_known_integer_fields():
    merged = usage.merge_usage(
        {"input_tokens": 10, "output_tokens": 2, "total_tokens": 12},
        {"input_tokens": 5, "output_tokens": 1, "total_tokens": 6, "requests": 1},
    )
    assert merged == {
        "input_tokens": 15,
        "output_tokens": 3,
        "total_tokens": 18,
        "requests": 1,
    }


def test_collect_usage_records_official_tokens_and_official_price():
    with usage.collect_usage() as ledger:
        usage.record_usage(
            model="qwen3.6-flash",
            vendor="bailian",
            payload=SimpleNamespace(
                usage=SimpleNamespace(
                    prompt_tokens=1_000_000,
                    completion_tokens=1_000_000,
                    total_tokens=2_000_000,
                )
            ),
        )
        usage.record_usage(
            model="qwen3-rerank",
            vendor="bailian",
            payload={"usage": {"prompt_tokens": 1_000_000, "total_tokens": 1_000_000}},
        )

    report = ledger.report()
    assert report["usage"] == {
        "input_tokens": 2_000_000,
        "output_tokens": 1_000_000,
        "total_tokens": 3_000_000,
        "requests": 2,
    }
    assert report["cost"]["currency"] == "CNY"
    assert report["cost"]["total"] == pytest.approx(1.2 + 7.2 + 0.5)
    models = {item["model"]: item for item in report["cost"]["items"]}
    assert models["qwen3.6-flash"]["cny"] == pytest.approx(8.4)
    assert models["qwen3-rerank"]["cny"] == pytest.approx(0.5)


def test_unknown_model_keeps_tokens_but_does_not_invent_a_price():
    with usage.collect_usage() as ledger:
        usage.record_usage(
            model="mystery-model",
            vendor="unknown",
            payload={"usage": {"prompt_tokens": 10, "completion_tokens": 2}},
        )

    report = ledger.report()
    assert report["usage"]["total_tokens"] == 12
    assert report["cost"]["total"] == 0
    assert report["cost"]["unpriced"] == [
        {
            "vendor": "unknown",
            "model": "mystery-model",
            "input_tokens": 10,
            "output_tokens": 2,
            "total_tokens": 12,
            "requests": 1,
        }
    ]


def test_record_usage_is_noop_without_active_collector():
    usage.record_usage(
        model="qwen3.6-flash",
        vendor="bailian",
        payload={"usage": {"prompt_tokens": 9, "completion_tokens": 1}},
    )


def test_vendor_from_base_url():
    assert (
        usage.vendor_from_base_url("https://dashscope.aliyuncs.com/compatible-mode/v1")
        == "bailian"
    )
    assert usage.vendor_from_base_url("https://api.siliconflow.cn/v1") == "siliconflow"
    assert usage.vendor_from_base_url("https://api.deepseek.com/v1") == "deepseek"


def test_official_qwen36_flash_price_is_beijing_list_price():
    price = pricing.price_for_model("qwen3.6-flash", vendor="bailian")
    assert price == {"input": 1.2, "output": 7.2, "unit": "CNY_per_million"}


def test_pricing_does_not_use_tiktoken_or_local_counts():
    cost = pricing.cost_cny(
        model="qwen3.6-flash",
        vendor="bailian",
        usage={"input_tokens": 500_000, "output_tokens": 250_000},
    )
    assert cost == pytest.approx(0.6 + 1.8)


def test_deepseek_v4_flash_uses_bailian_list_price_and_cache_discount():
    price = pricing.price_for_model("deepseek-v4-flash", vendor="bailian")
    assert price == {
        "input": 1.0,
        "output": 2.0,
        "cache_input": 0.2,
        "unit": "CNY_per_million",
    }
    cost = pricing.cost_cny(
        model="deepseek-v4-flash",
        vendor="bailian",
        usage={
            "input_tokens": 1_000_000,
            "output_tokens": 1_000_000,
            "cached_tokens": 200_000,
        },
    )
    assert cost == pytest.approx(0.8 * 1.0 + 0.2 * 0.2 + 2.0)


def test_siliconflow_bge_m3_is_free():
    price = pricing.price_for_model("BAAI/bge-m3", vendor="siliconflow")
    assert price == {"input": 0.0, "output": 0.0, "unit": "CNY_per_million"}
    assert (
        pricing.cost_cny(
            model="BAAI/bge-m3",
            vendor="siliconflow",
            usage={"input_tokens": 199_196, "total_tokens": 199_196},
        )
        == 0.0
    )


@pytest.fixture(autouse=True)
def _disable_live_pricing_lookup(monkeypatch):
    monkeypatch.setattr(pricing, "_fetch_bailian_model_payload", lambda _model: None)


def test_configured_project_models_have_snapshot_prices():
    missing = [
        (vendor, model)
        for vendor, model in pricing.PROJECT_MODELS
        if pricing.price_for_model(model, vendor=vendor) is None
    ]
    assert missing == []


def test_parse_official_bailian_model_payload():
    payload = {
        "success": True,
        "output": {
            "models": [
                {
                    "model": "qwen3.7-flash",
                    "prices": [
                        {
                            "range_name": "Default",
                            "prices": [
                                {"type": "input_token", "price": "0.2"},
                                {"type": "output_token", "price": "0.8"},
                                {"type": "input_token_cache", "price": "0.02"},
                            ],
                        }
                    ],
                }
            ]
        },
    }
    assert pricing.parse_bailian_model_prices(payload, "qwen3.7-flash") == {
        "input": 0.2,
        "output": 0.8,
        "cache_input": 0.02,
    }


def test_live_lookup_fills_unknown_bailian_model(monkeypatch):
    monkeypatch.setattr(
        pricing,
        "_fetch_bailian_model_payload",
        lambda model: {
            "success": True,
            "output": {
                "models": [
                    {
                        "model": model,
                        "prices": [
                            {
                                "range_name": "Default",
                                "prices": [
                                    {"type": "input_token", "price": "3"},
                                    {"type": "output_token", "price": "9"},
                                ],
                            }
                        ],
                    }
                ]
            },
        },
    )
    pricing.clear_live_price_cache()
    price = pricing.price_for_model("brand-new-qwen", vendor="bailian")
    assert price == {"input": 3.0, "output": 9.0, "unit": "CNY_per_million"}
