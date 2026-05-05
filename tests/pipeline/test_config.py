"""Tests for contextualize-related pipeline settings."""
from __future__ import annotations

from pathlib import Path

from pipeline.config import PipelineConfig


def test_contextualize_fields_default_values(monkeypatch, tmp_path: Path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("CONTEXTUALIZE_LLM_API_KEY", raising=False)
    monkeypatch.delenv("CONTEXTUALIZE_LLM_BASE_URL", raising=False)
    monkeypatch.delenv("CONTEXTUALIZE_LLM_MODEL", raising=False)
    monkeypatch.delenv("CONTEXTUALIZE_CONCURRENCY", raising=False)
    monkeypatch.delenv("CONTEXTUALIZE_RETRY_ATTEMPTS", raising=False)

    cfg = PipelineConfig()

    assert cfg.contextualize_llm_api_key == ""
    assert cfg.contextualize_llm_base_url == ""
    assert cfg.contextualize_llm_model == ""
    assert cfg.contextualize_concurrency == 8
    assert cfg.contextualize_retry_attempts == 2


def test_contextualize_fields_env_override(monkeypatch, tmp_path: Path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CONTEXTUALIZE_LLM_API_KEY", "context-key")
    monkeypatch.setenv("CONTEXTUALIZE_LLM_BASE_URL", "https://contextualize.test/v1")
    monkeypatch.setenv("CONTEXTUALIZE_LLM_MODEL", "context-model")
    monkeypatch.setenv("CONTEXTUALIZE_CONCURRENCY", "16")
    monkeypatch.setenv("CONTEXTUALIZE_RETRY_ATTEMPTS", "3")

    cfg = PipelineConfig()

    assert cfg.contextualize_llm_api_key == "context-key"
    assert cfg.contextualize_llm_base_url == "https://contextualize.test/v1"
    assert cfg.contextualize_llm_model == "context-model"
    assert cfg.contextualize_concurrency == 16
    assert cfg.contextualize_retry_attempts == 3
