"""Tests for settings loading."""
from __future__ import annotations

from pathlib import Path

from pipeline.config import PipelineConfig
from server.config import ServerConfig


def test_server_config_loads_project_dotenv(monkeypatch, tmp_path: Path):
    (tmp_path / ".env").write_text(
        "RERANK_PROVIDER=remote\nRERANK_API_URL=https://api.siliconflow.cn/v1\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("RERANK_PROVIDER", raising=False)
    monkeypatch.delenv("RERANK_API_URL", raising=False)

    cfg = ServerConfig()

    assert cfg.rerank_provider == "remote"
    assert cfg.rerank_api_url == "https://api.siliconflow.cn/v1"


def test_server_config_defaults(monkeypatch, tmp_path: Path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("RERANK_TOP_N", raising=False)
    monkeypatch.delenv("USE_UNIFIED_TOKENIZER", raising=False)

    cfg = ServerConfig()

    assert cfg.rerank_top_n == 15
    assert cfg.rerank_max_length == 8192
    assert cfg.use_unified_tokenizer is True


def test_pipeline_config_loads_project_dotenv(monkeypatch, tmp_path: Path):
    (tmp_path / ".env").write_text(
        "EMBEDDING_PROVIDER=remote\nEMBEDDING_API_URL=https://api.siliconflow.cn/v1\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("EMBEDDING_PROVIDER", raising=False)
    monkeypatch.delenv("EMBEDDING_API_URL", raising=False)

    cfg = PipelineConfig()

    assert cfg.embedding_provider == "remote"
    assert cfg.embedding_api_url == "https://api.siliconflow.cn/v1"
    assert cfg.use_unified_tokenizer is True
