"""Tests for contextualize-related pipeline settings."""
from __future__ import annotations

from pathlib import Path

from pipeline.config import PipelineConfig


def test_contextualize_fields_default_values(monkeypatch, tmp_path: Path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("CONTEXTUALIZE_CONCURRENCY", raising=False)
    monkeypatch.delenv("CONTEXTUALIZE_RETRY_ATTEMPTS", raising=False)

    cfg = PipelineConfig()

    assert cfg.contextualize_concurrency == 8
    assert cfg.contextualize_retry_attempts == 2


def test_contextualize_fields_env_override(monkeypatch, tmp_path: Path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CONTEXTUALIZE_CONCURRENCY", "16")
    monkeypatch.setenv("CONTEXTUALIZE_RETRY_ATTEMPTS", "3")

    cfg = PipelineConfig()

    assert cfg.contextualize_concurrency == 16
    assert cfg.contextualize_retry_attempts == 3
