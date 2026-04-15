"""Server configuration."""
from pydantic_settings import BaseSettings, SettingsConfigDict


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
    llm_enable_thinking: bool = True

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

    debug_pipeline_dir: str = "data/debug_runs"
    parsed_dir: str = "data/parsed"
    glossary_path: str = "data/glossary.json"
    pdf_dir: str = "data/pdfs"

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
