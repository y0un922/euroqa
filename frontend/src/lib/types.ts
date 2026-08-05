export type Confidence = "high" | "medium" | "low" | "none";

export type QuestionType = "rule" | "parameter" | "calculation" | "mechanism";

export type LlmSettings = {
  apiKey: string;
  baseUrl: string;
  model: string;
  enableThinking: boolean;
};

export type LlmRequestOverride = {
  api_key?: string;
  base_url?: string;
  model?: string;
  enable_thinking?: boolean;
};

export type LlmSettingsResponse = {
  base_url: string;
  model: string;
  enable_thinking: boolean;
  api_key_configured: boolean;
};

export type QueryRequestPayload = {
  question: string;
  domain?: string;
  docIds?: string[];
  kbIds?: string[];
  conversation_id?: string;
  sessionId?: string;
  stream?: boolean;
  llm?: LlmRequestOverride;
};

export type Source = {
  file: string;
  document_id?: string;
  display_title?: string;
  displayTitle?: string;
  source_title?: string;
  sourceTitle?: string;
  element_type?: "text" | "table" | "formula" | "image";
  docId?: string;
  elementType?: "text" | "table" | "figure" | "formula";
  bbox?: number[];
  title: string;
  section: string;
  page: number | string;
  clause: string;
  original_text: string;
  originalText?: string;
  highlight_text?: string;
  highlightText?: string;
  locator_text?: string;
  locatorText?: string;
  translation: string;
};

export type SourceTranslationRequest = {
  document_id: string;
  file: string;
  title: string;
  section: string;
  page: number | string;
  clause: string;
  original_text: string;
  locator_text: string;
};

export type SourceTranslationResponse = {
  translation: string;
};

export type RetrievalContextItem = {
  chunk_id: string;
  document_id: string;
  file: string;
  title: string;
  display_title?: string;
  section: string;
  page: number | string;
  clause: string;
  content: string;
  score?: number;
};

export type RetrievalContext = {
  chunks: RetrievalContextItem[];
  parent_chunks: RetrievalContextItem[];
  ref_chunks?: RetrievalContextItem[];
  guide_chunks?: RetrievalContextItem[];
  guide_example_chunks?: RetrievalContextItem[];
};

export type QueryResponse = {
  answer: string;
  sources: Source[];
  related_refs: string[];
  confidence: Confidence;
  conversation_id: string;
  degraded?: boolean;
  usage?: Record<string, number> | null;
  elapsed_ms?: number | null;
  retrieval_context?: RetrievalContext | null;
  question_type?: QuestionType | null;
  engineering_context?: Record<string, unknown> | null;
};

export type ConversationSessionResponse = {
  sessionId: string;
  conversationId: string;
  title?: string | null;
  updatedAt?: string | null;
  messages: ChatTurn[];
};

export type ConversationSessionSummaryResponse = {
  sessionId: string;
  conversationId: string;
  title?: string | null;
  updatedAt?: string | null;
  messageCount: number;
};

export type ConversationSessionListResponse = {
  sessions: ConversationSessionSummaryResponse[];
};

export type ConversationSessionDeleteResponse = {
  sessionId: string;
  deleted: boolean;
};

export type StreamDonePayload = {
  code?: number;
  sources: Source[];
  related_refs: string[];
  relatedRefs?: string[];
  confidence: Confidence;
  questionType?: QuestionType | null;
  answerMode?: string;
  title?: string | null;
  groundedness?: string | null;
  usage?: Record<string, number> | null;
  elapsed_ms?: number | null;
  retrieval_context?: RetrievalContext | null;
  question_type?: QuestionType | null;
  engineering_context?: Record<string, unknown> | null;
  normalized_answer?: string;
};

export type StreamReasoningPayload = {
  text?: string;
};

export type StreamErrorPayload = {
  code?: number;
  message?: string;
};

export type StreamCommentaryPayload = {
  text?: string;
  elapsed_ms?: number;
  request_id?: string;
};

export type ToolSubStep = {
  tool_name?: string;
  step_id: string;
  status: QueryProgressStatus;
  title: string;
  summary: string;
  metadata: Record<string, unknown>;
  elapsed_ms: number;
  parent_step_id?: string | null;
};

export type ToolProgressEvent = {
  tool_name: string;
  step: ToolSubStep;
  elapsed_ms: number;
  request_id: string;
};

export type QueryProgressStage =
  | "understanding"
  | "retrieving"
  | "references"
  | "guide"
  | "generating"
  | "agent_thinking"
  | "composing"
  | "chat"
  | "clarify"
  | "glossary_lookup"
  | `tool:${string}`
  | (string & {});

export type QueryProgressStatus = "running" | "completed" | "skipped";

export type QueryProgressEvent = {
  stage: QueryProgressStage;
  status: QueryProgressStatus;
  title: string;
  summary: string;
  elapsed_ms?: number;
  facts?: {
    question_type?: string;
    target?: string;
    evidence_count?: number;
    source_count?: number;
    resolved_refs?: string[];
    unresolved_refs?: string[];
    guide_count?: number;
    example_count?: number;
    tool_name?: string;
    tool_args?: Record<string, unknown>;
    tool_call_id?: string;
    tool_result?: string;
    tool_trace?: Record<string, unknown>;
  } & Record<string, unknown>;
};

export type DocumentStatus =
  | "uploaded"
  | "pending"
  | "parsing"
  | "structuring"
  | "chunking"
  | "summarizing"
  | "indexing"
  | "ready"
  | "error";

export type DocumentInfo = {
  id: string;
  name: string;
  title: string;
  total_pages: number;
  chunk_count: number;
  status?: DocumentStatus;
};

export type KnowledgeBaseInfo = {
  id: string;
  name: string;
  description: string;
  documentCount: number;
  createdAt: string;
  updatedAt: string;
};

export type KBDocumentInfo = {
  docId: string;
  fileName: string;
  status: DocumentStatus;
  addedAt: string;
};

export type KnowledgeBaseDetail = KnowledgeBaseInfo & {
  documents: KBDocumentInfo[];
};

export type KnowledgeBaseUploadResult = {
  kb_id: string;
  uploaded: Array<{
    doc_id: string;
    file_name: string;
    minio_path: string;
    status: string;
    message: string;
  }>;
  errors: Array<{
    doc_id?: string;
    file_name?: string;
    error: string;
  }>;
  knowledge_base: KnowledgeBaseDetail;
};

export type KnowledgeBaseDeleteResult = {
  deleted: boolean;
  delete_documents: boolean;
  deleted_documents: unknown[];
  kept_shared_doc_ids: string[];
};

export type DocumentUploadResponse = {
  doc_id: string;
  name: string;
  title: string;
  total_pages: number;
};

export type DocumentUploadToMinioResponse = {
  code: number;
  docId: string;
  fileName: string;
  minioPath: string;
  status: string;
  message: string;
};

export type PipelineProgressEvent = {
  doc_id: string;
  stage: string;
  progress: number;
  message: string;
  error?: string | null;
};

export type GlossaryEntry = {
  zh: string[];
  en: string;
  verified: boolean;
};

export type SuggestOption = {
  id: string;
  name: string;
};

export type SuggestResponse = {
  hot_questions: string[];
  domains: SuggestOption[];
};

export type ReferenceRecord = {
  id: string;
  source: Source;
  documentId: string | null;
  displayTitle: string;
  confidence: Confidence;
  relatedRefs: string[];
};

export type ChatTurn = {
  id: string;
  question: string;
  answer: string;
  reasoning: string;
  status: "streaming" | "done" | "error";
  confidence: Confidence;
  sources: Source[];
  relatedRefs: string[];
  degraded: boolean;
  conversationId?: string;
  errorMessage?: string;
  usage?: Record<string, number> | null;
  elapsed_ms?: number | null;
  retrievalContext?: RetrievalContext | null;
  questionType?: QuestionType | null;
  engineeringContext?: Record<string, unknown> | null;
  progressEvents?: QueryProgressEvent[];
  commentaries?: string[];
  toolSubSteps?: ToolSubStep[];
};
