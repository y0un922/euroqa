"""Pipeline configuration."""
from pydantic_settings import BaseSettings


class PipelineConfig(BaseSettings):
    model_config = {"env_prefix": ""}

    mineru_api_url: str = "http://localhost:8000"
    mineru_backend: str = "hybrid-http-client"

    llm_api_key: str = ""
    llm_base_url: str = "https://api.deepseek.com/v1"
    llm_model: str = "deepseek-chat"

    milvus_host: str = "localhost"
    milvus_port: int = 19530
    milvus_collection: str = "eurocode_chunks"

    es_url: str = "http://localhost:9200"
    es_index: str = "eurocode_chunks"

    pdf_dir: str = "data/pdfs"
    parsed_dir: str = "data/parsed"
    glossary_path: str = "data/glossary.json"

    child_chunk_max_tokens: int = 800
    child_chunk_min_tokens: int = 100
    parent_chunk_max_tokens: int = 4000
    long_subsection_threshold: int = 1500
    formula_group_threshold: int = 5
