"""Pydantic data models for requests, responses, and internal data structures."""

from __future__ import annotations

import uuid
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_serializer


def to_camel(value: str) -> str:
    """Convert snake_case field names to lower camelCase."""
    parts = value.split("_")
    return parts[0] + "".join(part[:1].upper() + part[1:] for part in parts[1:])


class CamelModel(BaseModel):
    """Base model for external API-document contracts."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )


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


class QuestionType(str, Enum):
    """问题分型：四类工程问题。"""

    RULE = "rule"
    PARAMETER = "parameter"
    CALCULATION = "calculation"
    MECHANISM = "mechanism"


class EngineeringContext(BaseModel):
    """从用户问题中提取的工程上下文字段。"""

    country: Optional[str] = None
    structure_type: Optional[str] = None
    limit_state: Optional[str] = None
    load_combination: Optional[bool] = None
    concrete_class: Optional[str] = None
    rebar_grade: Optional[str] = None
    prestressed: Optional[bool] = None
    discontinuity_region: Optional[bool] = None

    @property
    def missing_fields(self) -> list[str]:
        """返回值为 None 或空字符串的字段名列表。"""
        missing: list[str] = []
        for name, value in self.model_dump().items():
            if value is None or (isinstance(value, str) and not value.strip()):
                missing.append(name)
        return missing


class RoutingTargetHint(BaseModel):
    """LLM 输出的检索目标提示。"""

    document: Optional[str] = None
    clause: Optional[str] = None
    object: Optional[str] = None


class RoutingDecision(BaseModel):
    """查询理解阶段的路由决策。"""

    intent_label: str
    target_hint: RoutingTargetHint
    reason_short: str


class GuideHint(BaseModel):
    """查询理解阶段输出的指南算例提示。"""

    need_example: bool = False
    example_query: Optional[str] = None
    example_kind: Optional[str] = None


class ChunkMetadata(BaseModel):
    source: str
    document_id: Optional[str] = None
    source_title: str
    display_title: str = ""
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
    object_type: Optional[str] = None
    object_label: str = ""
    object_id: str = ""
    object_aliases: list[str] = []
    ref_labels: list[str] = []
    ref_object_ids: list[str] = []


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
    model_config = ConfigDict(populate_by_name=True)

    question: str = Field(..., max_length=500)
    domain: Optional[str] = None
    doc_ids: list[str] = Field(
        default_factory=list,
        alias="docIds",
        max_length=100,
    )
    kb_ids: list[str] = Field(default_factory=list, alias="kbIds")
    conversation_id: Optional[str] = None
    session_id: Optional[str] = Field(default=None, alias="sessionId")
    stream: bool = False
    llm: Optional[LlmSettingsOverride] = None


class Source(BaseModel):
    file: str
    document_id: str
    display_title: str = ""
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


class RetrievalContext(BaseModel):
    chunks: list[dict[str, object]] = Field(default_factory=list)
    parent_chunks: list[dict[str, object]] = Field(default_factory=list)
    guide_chunks: list[dict[str, object]] = Field(default_factory=list)
    guide_example_chunks: list[dict[str, object]] = Field(default_factory=list)
    ref_chunks: list[dict[str, object]] = Field(default_factory=list)
    # chunk_id -> "Ref-N"，即答案文本引用所使用的真实编号（按 agent 曝光顺序分配，
    # 与各 chunk 列表的类别拼接顺序不同）。消费方需按此映射对齐引用。
    ref_labels: dict[str, str] = Field(default_factory=dict)
    resolved_refs: list[str] = Field(default_factory=list)
    unresolved_refs: list[str] = Field(default_factory=list)
    slot_results: list[dict[str, object]] = Field(default_factory=list)
    unresolved_slots: list[str] = Field(default_factory=list)


class QueryResponse(BaseModel):
    answer: str
    sources: list[Source] = Field(default_factory=list)
    related_refs: list[str] = []
    confidence: Confidence
    conversation_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    degraded: bool = False
    usage: dict[str, int] | None = None
    cost: dict[str, object] | None = None
    elapsed_ms: int | None = None
    retrieval_context: RetrievalContext | None = None
    question_type: Optional[str] = None
    engineering_context: Optional[dict[str, object]] = None
    groundedness: Optional[str] = None


class ConversationTurn(CamelModel):
    id: str
    question: str
    answer: str = ""
    reasoning: str = ""
    status: str = "done"
    confidence: str = Confidence.NONE.value
    sources: list[dict[str, object]] = Field(default_factory=list)
    related_refs: list[str] = Field(default_factory=list)
    degraded: bool = False
    conversation_id: str
    error_message: Optional[str] = None
    usage: dict[str, int] | None = None
    cost: dict[str, object] | None = None
    elapsed_ms: int | None = None
    retrieval_context: Optional[dict[str, object]] = None
    question_type: Optional[str] = None
    engineering_context: Optional[dict[str, object]] = None
    progress_events: list[dict[str, object]] = Field(default_factory=list)
    commentaries: list[str] = Field(default_factory=list)


class ConversationSessionResponse(CamelModel):
    session_id: str
    conversation_id: str
    title: Optional[str] = None
    updated_at: Optional[str] = None
    messages: list[ConversationTurn] = Field(default_factory=list)


class ConversationSessionSummary(CamelModel):
    session_id: str
    conversation_id: str
    title: Optional[str] = None
    updated_at: Optional[str] = None
    message_count: int = 0


class ConversationSessionListResponse(CamelModel):
    sessions: list[ConversationSessionSummary] = Field(default_factory=list)


class ConversationSessionDeleteResponse(CamelModel):
    session_id: str
    deleted: bool


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


class DocumentStatus(str, Enum):
    """文档生命周期状态。"""

    UPLOADED = "uploaded"
    PENDING = "pending"
    PARSING = "parsing"
    STRUCTURING = "structuring"
    CHUNKING = "chunking"
    SUMMARIZING = "summarizing"
    INDEXING = "indexing"
    READY = "ready"
    ERROR = "error"


class DocumentInfo(BaseModel):
    id: str
    name: str
    title: str
    total_pages: int
    chunk_count: int
    status: DocumentStatus = DocumentStatus.READY
    usage: dict[str, int] | None = None
    cost: dict[str, object] | None = None


class DocumentUploadResponse(BaseModel):
    doc_id: str
    name: str
    title: str
    total_pages: int


class DocumentProcessResponse(BaseModel):
    doc_id: str
    stage: str
    message: str


class ApiErrorResponse(CamelModel):
    code: int
    message: str
    detail: str | None = None


class DocumentParseRequest(CamelModel):
    """Single-document parse payload (internal helpers / upload paths)."""

    doc_id: str
    file_name: str
    minio_path: str
    context_summary_enabled: bool = True


class DocumentParseFileItem(CamelModel):
    """One file entry in the external batch parse contract.

    Empty strings are allowed at schema level so the batch endpoint can return
    per-file ``rejected`` results instead of failing the whole request.
    """

    doc_id: str = ""
    file_name: str = ""
    minio_path: str = ""
    context_summary_enabled: bool | None = None


class DocumentParseBatchRequest(CamelModel):
    """External batch parse request: files[] only (no v1 single-object form)."""

    context_summary_enabled: bool = True
    files: list[DocumentParseFileItem] = Field(..., min_length=1, max_length=20)


class DocumentParseResultItem(CamelModel):
    doc_id: str
    status: str
    message: str
    error: dict[str, str] | None = None


class DocumentParseResponse(CamelModel):
    """Legacy single-doc response shape used by internal enqueue helpers."""

    code: int = 200
    doc_id: str
    status: str
    message: str


class DocumentParseBatchResponse(CamelModel):
    code: int = 200
    results: list[DocumentParseResultItem]


class DocumentParseQueueResponse(CamelModel):
    code: int = 200
    capacity: int
    used: int
    remaining: int
    active: int
    queued: int
    max_files_per_request: int


class DocumentUploadToMinioResponse(CamelModel):
    code: int = 200
    doc_id: str
    file_name: str
    minio_path: str
    status: str
    message: str


class KnowledgeBaseCreate(CamelModel):
    name: str = Field(..., min_length=1, max_length=120)
    description: str = Field(default="", max_length=500)


class KnowledgeBaseUpdate(CamelModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)


class KnowledgeBaseDocumentsUpdate(CamelModel):
    doc_ids: list[str] = Field(..., min_length=1, max_length=100)


class KnowledgeBaseInfo(CamelModel):
    id: str
    name: str
    description: str = ""
    document_count: int = 0
    created_at: str
    updated_at: str


class KBDocumentInfo(CamelModel):
    doc_id: str
    file_name: str
    status: DocumentStatus
    added_at: str


class KnowledgeBaseDetail(KnowledgeBaseInfo):
    documents: list[KBDocumentInfo] = Field(default_factory=list)


class DocumentStatusBatchRequest(CamelModel):
    doc_ids: list[str] = Field(..., min_length=1, max_length=50)


class DocumentStatusError(CamelModel):
    type: str
    detail: str
    stage: str
    timestamp: str


class DocumentStatusItem(CamelModel):
    doc_id: str
    status: str
    progress: float
    stage: str
    message: str
    chunk_count: int | None = None
    usage: dict[str, int] | None = None
    cost: dict[str, object] | None = None
    error: DocumentStatusError | None = None

    @model_serializer(mode="wrap")
    def _omit_empty_usage_cost(self, serializer):
        payload = serializer(self)
        if payload.get("usage") is None:
            payload.pop("usage", None)
        if payload.get("cost") is None:
            payload.pop("cost", None)
        return payload


class DocumentStatusBatchResponse(CamelModel):
    code: int = 200
    results: list[DocumentStatusItem]


class DocumentDeleteBatchRequest(CamelModel):
    doc_ids: list[str] = Field(..., min_length=1, max_length=50)


class DeletedChunks(CamelModel):
    milvus: int
    elasticsearch: int


class DocumentDeleteError(CamelModel):
    code: str
    message: str


class DocumentDeleteItem(CamelModel):
    doc_id: str
    deleted: bool
    deleted_chunks: DeletedChunks | None = None
    error: DocumentDeleteError | None = None


class DocumentDeleteBatchResponse(CamelModel):
    code: int = 200
    deleted: bool
    deleted_chunks: DeletedChunks


class TranslationContext(CamelModel):
    document_id: str | None = None
    title: str | None = None
    section: str | None = None
    clause: str | None = None


class TranslationRequest(CamelModel):
    text: str
    context: TranslationContext | None = None


class TranslationResponse(CamelModel):
    code: int = 200
    translation: str


class PipelineProgressEvent(BaseModel):
    doc_id: str
    stage: str
    progress: float
    message: str = ""
    error: Optional[str] = None


class GlossaryEntry(BaseModel):
    zh: list[str]
    en: str
    verified: bool = True
