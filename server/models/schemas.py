"""Pydantic data models for requests, responses, and internal data structures."""
from __future__ import annotations

import uuid
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ElementType(str, Enum):
    TEXT = "text"
    TABLE = "table"
    FORMULA = "formula"
    IMAGE = "image"


class Confidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    NONE = "none"


class QueryType(str, Enum):
    CONCEPT = "concept"
    CLAUSE = "clause"
    PARAMETER = "parameter"
    COMPARISON = "comparison"


class IntentType(str, Enum):
    EXACT = "exact"
    CONCEPT = "concept"
    REASONING = "reasoning"


class ChunkMetadata(BaseModel):
    source: str
    source_title: str
    section_path: list[str]
    page_numbers: list[int]
    page_file_index: list[int]
    clause_ids: list[str]
    element_type: ElementType
    cross_refs: list[str] = []
    parent_chunk_id: Optional[str] = None
    parent_text_chunk_id: Optional[str] = None
    bbox: list[float] = []
    bbox_page_idx: int = -1


class Chunk(BaseModel):
    chunk_id: str
    content: str
    embedding_text: str
    metadata: ChunkMetadata


class LlmSettingsOverride(BaseModel):
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    model: Optional[str] = None
    enable_thinking: Optional[bool] = None


class LlmSettingsResponse(BaseModel):
    base_url: str
    model: str
    enable_thinking: bool
    api_key_configured: bool


class QueryRequest(BaseModel):
    question: str = Field(..., max_length=500)
    domain: Optional[str] = None
    query_type: Optional[QueryType] = None
    conversation_id: Optional[str] = None
    stream: bool = False
    llm: Optional[LlmSettingsOverride] = None


class Source(BaseModel):
    file: str
    document_id: str
    element_type: ElementType = ElementType.TEXT
    bbox: list[float] = Field(default_factory=list)
    title: str
    section: str
    page: int | str
    clause: str
    original_text: str
    locator_text: str
    highlight_text: str = ""
    translation: str

    @field_validator("page", mode="before")
    @classmethod
    def normalize_page(cls, value: object) -> str:
        """将 page 统一为字符串，兼容 LLM 返回 int 或 str。"""
        if isinstance(value, int):
            return str(value)
        if isinstance(value, str):
            return value
        return str(value)


class QueryResponse(BaseModel):
    answer: str
    sources: list[Source] = Field(default_factory=list, max_length=5)
    related_refs: list[str] = []
    confidence: Confidence
    conversation_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    degraded: bool = False


class SourceTranslationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: str
    file: str
    title: str
    section: str
    page: int | str
    clause: str
    original_text: str
    locator_text: str


class SourceTranslationResponse(BaseModel):
    translation: str


class DocumentInfo(BaseModel):
    id: str
    name: str
    title: str
    total_pages: int
    chunk_count: int


class GlossaryEntry(BaseModel):
    zh: list[str]
    en: str
    verified: bool = True
