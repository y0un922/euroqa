"""Tests for shared tokenizer counting helpers."""
from __future__ import annotations

from dataclasses import dataclass

import pytest

import shared.tokenizers as tokenizers


@dataclass
class _FakeTokenizer:
    pieces: list[int]

    def encode(self, text: str, *, add_special_tokens: bool = False) -> list[int]:
        assert add_special_tokens is False
        return self.pieces


@pytest.fixture(autouse=True)
def _clear_tokenizer_cache(monkeypatch):
    tokenizers._get_hf_tokenizer.cache_clear()
    tokenizers._FAILED_HF_TOKENIZERS.clear()
    monkeypatch.delenv("TOKENIZER_NAME_QWEN3_EMBEDDING_8B", raising=False)
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    yield
    tokenizers._get_hf_tokenizer.cache_clear()
    tokenizers._FAILED_HF_TOKENIZERS.clear()


def test_embedding_count_loads_bge_m3_tokenizer(monkeypatch):
    calls: list[tuple[str, bool]] = []

    def fake_load(name: str, *, local_files_only: bool):
        calls.append((name, local_files_only))
        return _FakeTokenizer([1, 2, 3])

    monkeypatch.setattr(tokenizers, "_load_hf_tokenizer", fake_load)

    assert tokenizers.count_for_embedding("concrete beam") == (3, False)
    assert tokenizers.count_for_embedding("second call") == (3, False)
    assert calls == [("BAAI/bge-m3", True)]


def test_rerank_count_uses_independent_reranker_tokenizer(monkeypatch):
    calls: list[tuple[str, bool]] = []

    def fake_load(name: str, *, local_files_only: bool):
        calls.append((name, local_files_only))
        return _FakeTokenizer([1, 2, 3, 4])

    monkeypatch.setattr(tokenizers, "_load_hf_tokenizer", fake_load)

    assert tokenizers.count_for_rerank("EN 1992 clause 6.2.a") == (4, False)
    assert calls == [("BAAI/bge-reranker-v2-m3", True)]


def test_hf_loader_falls_back_from_local_cache_to_online(monkeypatch):
    calls: list[tuple[str, bool]] = []

    def fake_load(name: str, *, local_files_only: bool):
        calls.append((name, local_files_only))
        if local_files_only:
            raise OSError("cache miss")
        return _FakeTokenizer([1, 2])

    monkeypatch.setattr(tokenizers, "_load_hf_tokenizer", fake_load)

    assert tokenizers.count_for_embedding("混凝土 concrete") == (2, False)
    assert calls == [("BAAI/bge-m3", True), ("BAAI/bge-m3", False)]


def test_hf_loader_falls_back_to_char_estimate_when_unavailable(monkeypatch):
    calls: list[tuple[str, bool]] = []

    def fake_load(name: str, *, local_files_only: bool):
        calls.append((name, local_files_only))
        raise OSError("offline")

    monkeypatch.setattr(tokenizers, "_load_hf_tokenizer", fake_load)

    assert tokenizers.count_for_rerank("abcdef") == (3, True)
    assert tokenizers.count_for_rerank("abcdefgh") == (4, True)
    assert calls == [
        ("BAAI/bge-reranker-v2-m3", True),
        ("BAAI/bge-reranker-v2-m3", False),
    ]


def test_bge_count_helpers_return_plain_counts(monkeypatch):
    def fake_load(name: str, *, local_files_only: bool):
        return _FakeTokenizer([1, 2])

    monkeypatch.setattr(tokenizers, "_load_hf_tokenizer", fake_load)

    assert tokenizers.count_for_bge_embedding("text") == 2
    assert tokenizers.count_for_bge_rerank("text") == 2


def test_qwen_llm_count_uses_openai_compatible_usage(monkeypatch):
    calls = []

    class FakeCompletions:
        @staticmethod
        def create(**kwargs):
            calls.append(kwargs)
            return {"usage": {"prompt_tokens": 7}}

    class FakeClient:
        chat = type("Chat", (), {"completions": FakeCompletions})()

    def fake_client(**kwargs):
        calls.append({"client": kwargs})
        return FakeClient()

    monkeypatch.setenv("LLM_API_KEY", "llm-key")
    monkeypatch.setenv("LLM_BASE_URL", "https://dashscope.example/v1")
    monkeypatch.setattr(tokenizers, "_get_openai_compatible_client", fake_client)

    count, is_estimate = tokenizers.count_for_llm("混合 mixed text", "qwen3.6-flash")

    assert (count, is_estimate) == (7, False)
    assert calls == [
        {
            "client": {
                "api_key": "llm-key",
                "base_url": "https://dashscope.example/v1",
            }
        },
        {
            "model": "qwen3.6-flash",
            "messages": [{"role": "user", "content": "混合 mixed text"}],
            "max_tokens": 1,
        },
    ]


def test_qwen_llm_count_falls_back_when_usage_missing(monkeypatch):
    class FakeCompletions:
        @staticmethod
        def create(**kwargs):
            return {"usage": {}}

    class FakeClient:
        chat = type("Chat", (), {"completions": FakeCompletions})()

    monkeypatch.setenv("DASHSCOPE_API_KEY", "dashscope-key")
    monkeypatch.setattr(
        tokenizers,
        "_get_openai_compatible_client",
        lambda **kwargs: FakeClient(),
    )

    assert tokenizers.count_for_llm("abcdef", "qwen3.6-flash") == (3, True)


def test_qwen_embedding_count_can_use_dashscope_tokenization(monkeypatch):
    calls = []

    class FakeTokenization:
        @staticmethod
        def call(**kwargs):
            calls.append(kwargs)
            return {"usage": {"input_tokens": 5}}

    monkeypatch.setenv("DASHSCOPE_API_KEY", "dashscope-key")
    monkeypatch.setattr(tokenizers, "_get_dashscope_tokenization", lambda: FakeTokenization)

    assert tokenizers.count_for_embedding("query", "qwen3-embedding-8b") == (5, False)
    assert calls == [
        {
            "model": "qwen3-embedding-8b",
            "prompt": "query",
            "api_key": "dashscope-key",
        }
    ]


def test_qwen_count_falls_back_to_estimate_without_api_key(monkeypatch):
    def fail_hf_load(name: str, *, local_files_only: bool):
        raise AssertionError("HF tokenizer should not be loaded for Qwen API models")

    monkeypatch.setattr(tokenizers, "_load_hf_tokenizer", fail_hf_load)

    assert tokenizers.count_for_llm("abcdef", "qwen-max") == (3, True)


def test_llm_count_for_deepseek_model_is_estimate(monkeypatch):
    def fail_hf_load(name: str, *, local_files_only: bool):
        raise AssertionError("HF tokenizer should not be loaded for DeepSeek API alias")

    monkeypatch.setattr(tokenizers, "_load_hf_tokenizer", fail_hf_load)

    assert tokenizers.count_for_llm("abcdef", "deepseek-v4-flash") == (3, True)


def test_llm_count_for_openai_model_uses_tiktoken(monkeypatch):
    def fail_hf_load(name: str, *, local_files_only: bool):
        raise AssertionError("HF tokenizer should not be loaded")

    monkeypatch.setattr(tokenizers, "_load_hf_tokenizer", fail_hf_load)

    count, is_estimate = tokenizers.count_for_llm("hello world", "gpt-4o")

    assert count > 0
    assert is_estimate is False


def test_unknown_model_falls_back_to_estimate(monkeypatch):
    def fail_hf_load(name: str, *, local_files_only: bool):
        raise AssertionError("HF tokenizer should not be loaded without mapping")

    monkeypatch.setattr(tokenizers, "_load_hf_tokenizer", fail_hf_load)

    assert tokenizers.count_for_embedding("abcdef", "unknown-embedding") == (3, True)


def test_model_specific_hf_override(monkeypatch):
    calls: list[tuple[str, bool]] = []

    def fake_load(name: str, *, local_files_only: bool):
        calls.append((name, local_files_only))
        return _FakeTokenizer([1])

    monkeypatch.setattr(tokenizers, "_load_hf_tokenizer", fake_load)
    monkeypatch.setenv("TOKENIZER_NAME_QWEN3_EMBEDDING_8B", "Qwen/custom-tokenizer")

    assert tokenizers.count_for_embedding("hello", "qwen3-embedding-8b") == (1, False)
    assert calls == [("Qwen/custom-tokenizer", True)]
