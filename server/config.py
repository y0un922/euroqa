"""Server configuration."""

import logging

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_logger = logging.getLogger(__name__)
_DEFAULT_SECRET = "euroqa-default-secret-change-me"


class ServerConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    llm_api_key: str = ""
    llm_base_url: str = "https://api.deepseek.com/v1"
    llm_model: str = "deepseek-chat"
    llm_enable_thinking: bool = False
    llm_prompt_cache_enabled: bool = True
    use_unified_tokenizer: bool = True

    access_password: str = ""
    auth_secret_key: str = _DEFAULT_SECRET
    auth_token_ttl_seconds: int = 86400

    @model_validator(mode="after")
    def _check_auth_secret(self) -> "ServerConfig":
        if self.access_password and self.auth_secret_key == _DEFAULT_SECRET:
            raise ValueError(
                "ACCESS_PASSWORD is set but AUTH_SECRET_KEY is still the default. "
                "Set AUTH_SECRET_KEY to a random string to prevent token forgery."
            )
        return self

    query_expansion_llm_api_key: str = ""
    query_expansion_llm_base_url: str = ""
    query_expansion_llm_model: str = ""

    agent_llm_api_key: str = ""
    agent_llm_base_url: str = ""
    agent_llm_model: str = ""

    translation_llm_api_key: str = ""
    translation_llm_base_url: str = ""
    translation_llm_model: str = ""

    embedding_provider: str = "local"
    embedding_api_url: str = ""
    embedding_api_key: str = ""
    embedding_model: str = "BAAI/bge-m3"
    embedding_request_timeout_seconds: float = 120.0
    embedding_batch_size: int = 8

    rerank_provider: str = "local"
    rerank_api_url: str = ""
    rerank_api_key: str = ""
    rerank_model: str = "BAAI/bge-reranker-v2-m3"
    rerank_request_timeout_seconds: float = 120.0
    rerank_max_length: int = 8192
    httpx_max_connections: int = 100
    httpx_max_keepalive_connections: int = 20

    milvus_host: str = "localhost"
    milvus_port: int = 19530
    milvus_collection: str = "eurocode_chunks"

    es_url: str = "http://localhost:9200"
    es_index: str = "eurocode_chunks"

    vector_top_k: int = 30
    bm25_top_k: int = 30
    rerank_top_n: int = 10
    max_context_tokens: int = 4000

    conversation_ttl_hours: int = 24
    max_conversation_rounds: int = 3

    redis_url: str = ""

    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_secure: bool = False

    request_deadline_seconds: int = 120
    agent_timeout_seconds: int = 60
    agent_max_concurrency: int = 5
    agent_circuit_breaker_failure_threshold: int = 5
    agent_circuit_breaker_recovery_seconds: float = 30.0

    log_json: bool = False

    debug_pipeline_dir: str = "data/debug_runs"
    parsed_dir: str = "data/parsed"
    glossary_path: str = "data/glossary.json"
    pdf_dir: str = "data/pdfs"
    kb_db_path: str = "data/knowledge_bases.db"

    @property
    def resolved_agent_llm_api_key(self) -> str:
        """Return the agent-loop LLM API key with main LLM fallback."""
        return self.agent_llm_api_key or self.llm_api_key

    @property
    def resolved_agent_llm_base_url(self) -> str:
        """Return the agent-loop LLM base URL with main LLM fallback."""
        return self.agent_llm_base_url or self.llm_base_url

    @property
    def resolved_agent_llm_model(self) -> str:
        """Return the agent-loop LLM model with main LLM fallback."""
        return self.agent_llm_model or self.llm_model

    def with_llm_override(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        enable_thinking: bool | None = None,
    ) -> "ServerConfig":
        """Return a config copy with request-scoped LLM overrides applied."""
        data = self.model_dump()

        if api_key and api_key.strip():
            data["llm_api_key"] = api_key.strip()
        if base_url and base_url.strip():
            data["llm_base_url"] = base_url.strip()
        if model and model.strip():
            data["llm_model"] = model.strip()
        if enable_thinking is not None:
            data["llm_enable_thinking"] = enable_thinking

        return type(self)(**data)
