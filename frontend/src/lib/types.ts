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
  conversation_id?: string;
  stream?: boolean;
  llm?: LlmRequestOverride;
};

export type Source = {
  file: string;
  document_id?: string;
  element_type?: "text" | "table" | "formula" | "image";
  bbox?: number[];
  title: string;
  section: string;
  page: number | string;
  clause: string;
  original_text: string;
  highlight_text?: string;
  locator_text?: string;
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
  section: string;
  page: number | string;
  clause: string;
  content: string;
  score?: number;
};

export type RetrievalContext = {
  chunks: RetrievalContextItem[];
  parent_chunks: RetrievalContextItem[];
};

export type QueryResponse = {
  answer: string;
  sources: Source[];
  related_refs: string[];
  confidence: Confidence;
  conversation_id: string;
  degraded?: boolean;
  retrieval_context?: RetrievalContext | null;
  question_type?: QuestionType | null;
  engineering_context?: Record<string, unknown> | null;
};

export type StreamDonePayload = {
  sources: Source[];
  related_refs: string[];
  confidence: Confidence;
  retrieval_context?: RetrievalContext | null;
  question_type?: QuestionType | null;
  engineering_context?: Record<string, unknown> | null;
};

export type StreamReasoningPayload = {
  text?: string;
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

export type DocumentUploadResponse = {
  doc_id: string;
  name: string;
  title: string;
  total_pages: number;
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
  retrievalContext?: RetrievalContext | null;
  questionType?: QuestionType | null;
  engineeringContext?: Record<string, unknown> | null;
};
