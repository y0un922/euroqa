"""Pydantic data models for requests, responses, and internal data structures."""
from __future__ import annotations

import uuid
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


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


class Chunk(BaseModel):
    chunk_id: str
    content: str
    embedding_text: str
    metadata: ChunkMetadata


class QueryRequest(BaseModel):
    question: str = Field(..., max_length=500)
    domain: Optional[str] = None
    query_type: Optional[QueryType] = None
    conversation_id: Optional[str] = None
    stream: bool = False


class Source(BaseModel):
    file: str
    title: str
    section: str
    page: int
    clause: str
    original_text: str = Field(..., max_length=1000)
    translation: str


class QueryResponse(BaseModel):
    answer: str
    sources: list[Source] = Field(default_factory=list, max_length=5)
    related_refs: list[str] = []
    confidence: Confidence
    conversation_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    degraded: bool = False


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
