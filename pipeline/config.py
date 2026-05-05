"""Pipeline configuration."""
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class PipelineConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    mineru_provider: Literal["local", "official"] = "local"
    mineru_api_url: str = "http://localhost:8000"
    mineru_backend: str = "hybrid-http-client"
    mineru_official_base_url: str = "https://mineru.net"
    mineru_api_token: str = ""
    mineru_official_model_version: Literal["pipeline", "vlm", "MinerU-HTML"] = "pipeline"
    mineru_enable_formula: bool = True
    mineru_enable_table: bool = True
    mineru_language: str = "ch"
    mineru_is_ocr: bool = False
    mineru_request_timeout_seconds: float = 600.0
    mineru_poll_interval_seconds: float = 5.0

    llm_api_key: str = ""
    llm_base_url: str = "https://api.deepseek.com/v1"
    llm_model: str = "deepseek-chat"
    llm_concurrency: int = 10
    contextualize_llm_api_key: str = ""
    contextualize_llm_base_url: str = ""
    contextualize_llm_model: str = ""
    contextualize_concurrency: int = 8
    contextualize_retry_attempts: int = 2

    embedding_provider: Literal["local", "remote"] = "local"
    embedding_api_url: str = ""
    embedding_api_key: str = ""
    embedding_model: str = "BAAI/bge-m3"
    embedding_request_timeout_seconds: float = 120.0
    embedding_batch_size: int = 8

    rerank_provider: Literal["local", "remote"] = "local"
    rerank_api_url: str = ""
    rerank_api_key: str = ""
    rerank_model: str = "BAAI/bge-reranker-v2-m3"
    rerank_request_timeout_seconds: float = 120.0

    milvus_host: str = "localhost"
    milvus_port: int = 19530
    milvus_collection: str = "eurocode_chunks"

    es_url: str = "http://localhost:9200"
    es_index: str = "eurocode_chunks"

    pdf_dir: str = "data/pdfs"
    parsed_dir: str = "data/parsed"
    debug_pipeline_dir: str = "data/debug_runs"
    glossary_path: str = "data/glossary.json"

    # 文档树清洗
    tree_pruning_enabled: bool = True
    tree_pruning_body_start_titles: str = "Foreword"

    child_chunk_max_tokens: int = 800
    child_chunk_min_tokens: int = 100
    parent_chunk_max_tokens: int = 4000
    long_subsection_threshold: int = 1500
    formula_group_threshold: int = 5
