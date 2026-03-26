"""Server configuration."""
from pydantic_settings import BaseSettings


class ServerConfig(BaseSettings):
    model_config = {"env_prefix": ""}

    llm_api_key: str = ""
    llm_base_url: str = "https://api.deepseek.com/v1"
    llm_model: str = "deepseek-chat"

    milvus_host: str = "localhost"
    milvus_port: int = 19530
    milvus_collection: str = "eurocode_chunks"

    es_url: str = "http://localhost:9200"
    es_index: str = "eurocode_chunks"

    vector_top_k: int = 20
    bm25_top_k: int = 20
    rerank_top_n: int = 5
    max_context_tokens: int = 3000

    conversation_ttl_hours: int = 24
    max_conversation_rounds: int = 3

    glossary_path: str = "data/glossary.json"
    pdf_dir: str = "data/pdfs"
