# Quality Guidelines

> Code quality standards for backend development.

---

## Overview

<!--
Document your project's quality standards here.

Questions to answer:
- What patterns are forbidden?
- What linting rules do you enforce?
- What are your testing requirements?
- What code review standards apply?
-->

(To be filled by the team)

---

## Forbidden Patterns

<!-- Patterns that should never be used and why -->

(To be filled by the team)

---

## Required Patterns

### Scenario: External Document Parse and Status Contracts

#### 1. Scope / Trigger

- Trigger: any change to `/api/v1/documents/parse`, `/api/v1/documents/status`, `/api/v1/documents/delete`, single-document pipeline metadata, or Huake-facing document response fields.
- Reason: Huake-visible status and file names are API contracts. Missing documents must not look like parse failures, and retrieval context must not expose opaque `docId` values when the client supplied a readable file name.

#### 2. Signatures

- Parse endpoint: `POST /api/v1/documents/parse` with `DocumentParseRequest`.
- Status endpoint: `POST /api/v1/documents/status` with `DocumentStatusBatchRequest`.
- Single-document runner: `run_single_document(doc_id: str, pipeline_config: PipelineConfig, on_progress: ProgressCallback | None = None) -> dict[str, int]`.
- Parse options file: `{parsed_dir}/{doc_id}/parse_options.json`.

#### 3. Contracts

- `DocumentParseRequest.file_name` must be persisted to `parse_options.json` as `file_name`.
- Queued single-document parsing must use persisted `file_name` for chunk `metadata.source_title` when it is present.
- Do not generate or read MinerU/OCR/markdown-derived titles (`display_title`, `title`, `source_title`, or `document_title`) for retrieval display names.
- Chunk `metadata.source` remains the stable backend `doc_id`; do not replace it with the display file name because deletion, rebuild, and source filters depend on it.
- Missing/unuploaded documents in `/api/v1/documents/status` return external `status="not_found"` and `stage="not_found"`, with `error.type="NOT_FOUND"`.
- Actual parser or pipeline failures continue to return `status="failed"`.
- Batch delete should submit Milvus/Elasticsearch deletes without forcing synchronous storage refresh/flush; otherwise repeated client deletes can block long enough to hit read timeouts.

#### 4. Validation & Error Matrix

- PDF and parsed directory both absent -> `status="not_found"`, `stage="not_found"`, `error.type="NOT_FOUND"`.
- Task manager reports `PipelineStage.ERROR` -> `status="failed"` with internal error detail.
- `file_name` is present and non-empty -> use it as retrieval display title.
- `file_name` is missing or blank -> use the legacy `docId` display fallback; do not inspect parsed title metadata.
- Batch delete succeeds in Milvus/Elasticsearch -> return deleted counts after delete submission and retriever cache invalidation, without waiting for force refresh.

#### 5. Good/Base/Bad Cases

- Good: Huake sends `fileName="Eurocode 2 - Concrete Design.pdf"` for `docId="huake_opaque_doc_123"`; answer sources show the filename while backend source keys stay `huake_opaque_doc_123`.
- Base: local/manual pipeline runs without parse options use the legacy `docId` display fallback.
- Bad: replacing `metadata.source` with the filename, which breaks delete/reindex cleanup by `doc_id`.
- Bad: reporting a never-uploaded `docId` as `failed`, forcing clients to infer missing state from error text.
- Bad: calling Milvus `flush()` or Elasticsearch `delete_by_query(refresh=True)` in the request path for Huake-facing delete operations.

#### 6. Tests Required

- API tests must assert `parse_options.json` stores `file_name` from `DocumentParseRequest.fileName`.
- Pipeline runner tests must assert client `file_name` becomes chunk `source_title`.
- Parse tests must assert Stage 1 does not write `display_title` from MinerU metadata or markdown headings.
- Status endpoint tests must assert missing documents return `not_found` and not `failed`.
- Index deletion tests must assert delete paths do not force Milvus flush or Elasticsearch refresh.
- Existing source-building tests should continue to verify readable file names flow into answer sources.

#### 7. Wrong vs Correct

##### Wrong

```python
display_title = _resolve_display_title(metadata, markdown, pdf_path.stem)
source_title = _resolve_source_title(meta, doc_id.replace("_", " "))
```

##### Correct

```python
source_title = requested_file_name or display_source_name
```

### Scenario: Indexed Source Title Repair Script

#### 1. Scope / Trigger

- Trigger: any change to the server-side script that repairs already-indexed document display titles from `{parsed_dir}/{doc_id}/parse_options.json`.
- Reason: production deployments may contain chunks indexed before the Huake filename contract was enforced. Repair must preserve stable source identity while making prompt and source display fields readable.

#### 2. Signatures

- Command: `python scripts/fix_source_titles_from_parse_options.py [--apply] [--parsed-dir PATH] [--es-url URL] [--es-index NAME] [--milvus-host HOST] [--milvus-port PORT] [--milvus-collection NAME]`.
- Environment fallbacks: `PARSED_DIR`, `ES_URL`, `ES_INDEX`, `MILVUS_HOST`, `MILVUS_PORT`, `MILVUS_COLLECTION`.
- Input sidecar: `{parsed_dir}/{doc_id}/parse_options.json` with `file_name` (also tolerates `filename` / `fileName` for repair compatibility).

#### 3. Contracts

- Default mode is dry-run. The script must not mutate Elasticsearch or Milvus unless `--apply` is present.
- Elasticsearch repair updates `source_title` and `display_title` for documents whose `source` equals the stable `doc_id` or the configured legacy source alias.
- Milvus repair must inspect the collection schema before writing. If `source_title` or `display_title` scalar fields exist, update them; if the deployed schema only contains `chunk_id`, `embedding`, `source`, and `element_type`, report that no display-title field exists and leave Milvus source identity unchanged.
- The script must never replace `source` with the filename. `source` remains the backend document id used by retrieval filters, delete, rebuild, and file endpoints.

#### 4. Validation & Error Matrix

- No parse options with filename -> exit non-zero with a clear message.
- Invalid sidecar JSON -> skip that document and report the path.
- Elasticsearch document count is zero for a target -> report zero chunks and continue.
- Milvus collection missing -> report and continue unless the caller chose to run only Milvus checks.
- Milvus schema has no display fields -> verify source presence and do not attempt an upsert.

#### 5. Good/Base/Bad Cases

- Good: `doc_id="huake-doc-123"`, `file_name="Eurocode 2 Concrete.pdf"`; ES chunks keep `source="huake-doc-123"` and get `source_title/display_title="Eurocode 2 Concrete.pdf"`.
- Base: current Milvus schema has no display fields; script reports `found` for `source` and performs no Milvus mutation.
- Bad: changing Milvus or ES `source` from `huake-doc-123` to `Eurocode 2 Concrete.pdf`, breaking document filters and delete paths.

#### 6. Tests Required

- Generation tests must assert prompt `文档名`, `sources[].display_title/title`, and retrieval context display fields prefer uploaded filename.
- Script help must remain runnable without external services.
- Dry-run target loading should be testable without Elasticsearch or Milvus by using `--skip-es --skip-milvus`.

#### 7. Wrong vs Correct

##### Wrong

```python
ctx._source.source = params.file_name
```

##### Correct

```python
ctx._source.source_title = params.file_name
ctx._source.display_title = params.file_name
```

### Scenario: Deterministic Query-Understanding Stabilizers

#### 1. Scope / Trigger

- Trigger: any change that adds deterministic correction after LLM query expansion or routing.
- Reason: query-understanding drift can change retrieval evidence before answer generation sees the prompt. For high-value exact-answer intents, a narrow deterministic stabilizer is safer than relying only on low-temperature LLM output.

#### 2. Signatures

- Query-understanding entry point: `analyze_query(question: str, glossary: dict[str, str], config: ServerConfig | None = None) -> QueryAnalysis`.
- Expansion entry point: `expand_queries(question: str, glossary: dict[str, str], config: ServerConfig | None = None) -> ExpansionResult`.
- Stabilizer shape: `_stabilize_<intent>_expansion(question: str, expansion: ExpansionResult) -> ExpansionResult`.
- Intent detector shape: `_is_<intent>_query(question: str) -> bool`.

#### 3. Contracts

- Stabilizers must run after LLM expansion parsing, so existing LLM behavior remains available for non-target questions.
- A stabilizer must be narrower than a single broad keyword. It should require:
  - an explicit domain cue, such as `concrete`, `EN 1992`, or equivalent.
  - an explicit answer target cue, such as `partial factor`, `分项系数`, or stable symbol families.
  - enough context to distinguish value lookup from open explanation questions.
- Stabilized `ExpansionResult` must set stable `queries`, `question_type`, and `routing` fields together. Do not change only one field while leaving routing inconsistent.
- Stabilized routing must not invent exact clauses or table numbers unless the rule can determine them deterministically.
- Non-target questions must return the original `ExpansionResult` unchanged.

#### 4. Validation & Error Matrix

- LLM returns `open` for a targeted exact-value query -> stabilizer may override to exact routing.
- LLM returns drifting terms for a targeted exact-value query -> stabilizer may replace all query strings with stable query strings.
- Question lacks the required domain cue -> do not stabilize.
- Question asks why/how a factor works rather than asking for values -> do not stabilize.
- LLM call fails and the original user question still matches the narrow stabilizer -> the fallback expansion may be stabilized.

#### 5. Good/Base/Bad Cases

- Good: a concrete partial-factor lookup is stabilized to exact parameter routing with stable EN 1990 / EN 1992 retrieval terms.
- Base: a generic explanation such as `分项系数有什么作用？` keeps LLM `open` routing.
- Bad: a rule that triggers on any occurrence of `作用` or `材料`, causing unrelated concrete mechanism questions to become exact lookups.

#### 6. Tests Required

- Tests must include at least one targeted question where the mocked LLM returns a wrong/open routing and drifting terms.
- Tests must include English and symbol variants when the stabilizer supports them.
- Tests must include negative cases for adjacent wording, such as generic why/mechanism questions and single-context material-only questions.
- `analyze_query()` tests must assert the public `QueryAnalysis` fields are stable, not only the private helper output.

#### 7. Wrong vs Correct

##### Wrong

```python
# Wrong: broad keyword makes many ordinary questions exact lookups.
if "作用" in question or "材料" in question:
    expansion.routing.answer_mode = AnswerMode.EXACT
```

##### Correct

```python
# Correct: require domain, lookup target, and enough context before overriding.
if not _is_concrete_action_material_partial_factor_query(question):
    return expansion
return ExpansionResult(queries=stable_queries, question_type=QuestionType.PARAMETER, ...)
```

### Scenario: Local Answer Variance Debug CLI

#### 1. Scope / Trigger

- Trigger: any new or changed local command that repeats the Euro_QA answer pipeline for diagnostics.
- Reason: repeated-answer debugging must expose enough per-layer evidence to identify whether drift begins in query understanding, retrieval, or generation, without changing normal `/api/v1/query` behavior.

#### 2. Signatures

- Module command: `python -m server.debug.answer_variance "<question>" --runs <N> [--domain <source>] [--output markdown|json]`.
- Programmatic entry point: `run_repeated(question: str, runs: int, config: ServerConfig | None = None, retriever: RetrieverLike | None = None, glossary: dict[str, str] | None = None, domain: str | None = None) -> dict[str, object]`.
- Single-run capture: `run_once(...) -> AnswerVarianceRun`.

#### 3. Contracts

- Debug CLIs live under `server/debug/` and must be runnable with `python -m ...`.
- The command must call the same non-streaming chain as `/api/v1/query`: `analyze_query` -> `retriever.retrieve` -> `generate_answer`.
- Normal API response schemas and route behavior must not change for a local debug command.
- Each run snapshot must include:
  - query-understanding fields: original/rewritten query, expanded queries, filters, answer mode, question type, intent label, target hints.
  - retrieval fields: effective filters, groundedness, exact probe flag, chunk IDs, scores, source, section/page/clause metadata, ref/guide/example chunks.
  - answer fields: confidence, degraded flag, answer mode, groundedness, source count, answer length, answer preview/full answer for JSON output.
- Summary output must identify the likely first drift layer in this order: query understanding, retrieval, generation, stable.

#### 4. Validation & Error Matrix

- `runs < 1` -> raise `ValueError` before calling external services.
- Missing external services during actual CLI use -> allow the underlying pipeline error to surface; do not hide it as a successful report.
- Injected test retriever/glossary/config -> must avoid external service initialization.
- Retriever created by the CLI and exposing `close()` -> close it in a `finally` block.

#### 5. Good/Base/Bad Cases

- Good: `uv run python -m server.debug.answer_variance "设计使用年限是什么？" --runs 3 --output markdown` prints per-run chunk sequences and a likely variance layer.
- Base: `--output json` returns the full structured payload for later diffing.
- Bad: adding debug-only fields to `QueryResponse` or changing `/api/v1/query` just to support local diagnostics.

#### 6. Tests Required

- Unit tests must cover retrieval serialization, including chunk IDs, scores, and metadata.
- Tests must cover variance summary precedence when multiple layers change.
- Runner tests must mock `analyze_query`, retrieval, and `generate_answer` so they do not require Milvus, Elasticsearch, or LLM services.
- CLI help should remain runnable with `python -m server.debug.answer_variance --help`.

#### 7. Wrong vs Correct

##### Wrong

```python
# Wrong: debug code changes the production response contract.
response = response.model_copy(update={"debug_runs": snapshots})
```

##### Correct

```python
# Correct: local command builds its own report without touching API responses.
report = await run_repeated(question=question, runs=runs)
print(render_markdown_report(report))
```

### Scenario: Answer Confidence Normalization

#### 1. Scope / Trigger

- Trigger: any change that exposes or recalculates `QueryResponse.confidence`.
- Reason: retrieval confidence is an API contract field, not free-form model prose. Streaming and non-streaming endpoints must not diverge because one trusts LLM JSON while the other uses retrieval scores.

#### 2. Contracts

- Public answer confidence must be derived deterministically from retrieval evidence, not from the LLM `confidence` field.
- Streaming and non-streaming generation paths must call the same confidence inference helper.
- `groundedness="not_grounded"` must force low confidence.
- `groundedness="partial"` must cap confidence at medium, even when the top rerank score is high.
- Missing canonical sources must force low confidence.
- LLM-provided confidence may be parsed for backward compatibility, but it must not override retrieval-derived confidence in final API responses.

#### 3. Tests Required

- Unit tests must cover the confidence helper for `grounded`, `partial`, `not_grounded`, and missing-source cases.
- Regression tests must cover non-streaming generation where the LLM returns `confidence="low"` but retrieval evidence is grounded with a high score.

### Scenario: Remote Rerank Request Compatibility

#### 1. Scope / Trigger

- Trigger: any change to remote rerank request payloads, timeout settings, or provider-specific optional fields.
- Reason: rerank is on the critical retrieval path. Optional provider fields such as `max_length` must improve scoring quality without turning a provider schema mismatch into a retrieval outage.

#### 2. Contracts

- Remote rerank clients should send configured optional fields such as `max_length` when supported.
- If a remote provider returns HTTP 400 for an optional field, retry once without that field.
- After a successful fallback, the same client instance should remember the field as unsupported and skip it on later calls.
- Request timeout must stay configurable and default to a production-safe value, currently 120 seconds.
- Structured logs must include status code, latency, model, document count, top_n, and whether the optional field was sent.
- Retrieval spot-check truncation metrics must use the configured rerank max length, not a hard-coded constant.

#### 3. Tests Required

- Unit tests must assert the remote request includes the configured `max_length`.
- Unit tests must assert a 400 response retries without `max_length`.
- Unit tests must assert later calls skip `max_length` after fallback.
- Retrieval tests must assert spot-check `max_tokens` follows config.

### Scenario: Contextual Retrieval LLM Configuration

#### 1. Scope / Trigger

- Trigger: any change to Stage 3.5 contextual retrieval enrichment, contextualizer client setup, or contextualize-related environment variables.
- Reason: contextual retrieval can be high-volume and model-sensitive. It must be tunable without changing the main answer-generation LLM.

#### 2. Signatures

- Config object: `PipelineConfig`.
- Contextualizer entry point: `Contextualizer(config: PipelineConfig)`.
- LLM call path: `Contextualizer._call_llm(prompt: str, *, max_tokens: int) -> str`.

#### 3. Contracts

- Contextual retrieval may use dedicated OpenAI-compatible settings:
  - `CONTEXTUALIZE_LLM_API_KEY`
  - `CONTEXTUALIZE_LLM_BASE_URL`
  - `CONTEXTUALIZE_LLM_MODEL`
- Each contextualize-specific setting must fall back independently to the matching main LLM setting:
  - `CONTEXTUALIZE_LLM_API_KEY` -> `LLM_API_KEY`
  - `CONTEXTUALIZE_LLM_BASE_URL` -> `LLM_BASE_URL`
  - `CONTEXTUALIZE_LLM_MODEL` -> `LLM_MODEL`
- Contextual retrieval runtime knobs remain separate from model selection:
  - `CONTEXTUALIZE_CONCURRENCY`
  - `CONTEXTUALIZE_RETRY_ATTEMPTS`
- Do not route server answer generation, query expansion, or translation through contextualize-specific settings.

#### 4. Validation & Error Matrix

- All contextualize-specific LLM settings blank -> use the main LLM key, base URL, and model.
- Only `CONTEXTUALIZE_LLM_MODEL` set -> use that model with the main LLM key and base URL.
- Only contextualize key/base set -> use those connection settings with the main LLM model.
- `CONTEXTUALIZE_RETRY_ATTEMPTS <= 0` -> clamp retry attempts to at least one attempt.

#### 5. Good/Base/Bad Cases

- Good: `.env` sets `CONTEXTUALIZE_LLM_MODEL=fast-context-model`, while answer generation keeps `LLM_MODEL=strong-answer-model`.
- Base: no contextualize-specific LLM settings are set, so contextual retrieval keeps existing `LLM_*` behavior.
- Bad: changing `LLM_MODEL` solely to tune contextual retrieval, unintentionally changing answer generation.

#### 6. Tests Required

- Config tests must cover default blank contextualize-specific LLM fields and environment overrides.
- Contextualizer tests must assert dedicated key/base/model override the main LLM settings.
- Contextualizer tests must assert blank dedicated fields fall back to the main LLM settings.

#### 7. Wrong vs Correct

##### Wrong

```python
client = AsyncOpenAI(base_url=config.llm_base_url, api_key=config.llm_api_key)
model = config.llm_model
```

##### Correct

```python
client = AsyncOpenAI(
    base_url=config.contextualize_llm_base_url or config.llm_base_url,
    api_key=config.contextualize_llm_api_key or config.llm_api_key,
)
model = config.contextualize_llm_model or config.llm_model
```

### Scenario: Retrieval Evidence Boundary

#### 1. Scope / Trigger

- Trigger: any change to retrieval ranking, guide/example retrieval, prompt assembly, or response source construction.
- Reason: every answer-supporting evidence chunk must remain citable. Guide or commentary PDFs may be tagged for observability, but retrieval must not drop them from the main evidence path because some deployments index guide/designers-guide documents as the primary corpus.

#### 2. Contracts

- `RetrievalResult.chunks` contains all reranked citable evidence, including guide/commentary/example chunks when they are retrieved.
- `RetrievalResult.guide_chunks` and `RetrievalResult.guide_example_chunks` are observability/helper views. They must not be implemented by subtracting guide-like chunks from `RetrievalResult.chunks`.
- Prompt builders use one citable citation namespace: `[Ref-N]`. Do not introduce `[Guide-N]` or `[GuideExample-N]` as answer citations unless the frontend source contract supports them.
- Response `sources` must be built from the same citable chunk ordering as prompt `[Ref-N]`, including guide/commentary/example chunks that may be cited.
- Frontend citation linkification maps only `[Ref-N]` / `[REF-N]` to `sources[N-1]`. Guide/commentary/example evidence must arrive as ordinary entries in `sources`; do not add frontend-only `[Guide-N]` or `[GuideExample-N]` citation namespaces.
- Frontend retrieval context must preserve the backend groups `chunks`, `parent_chunks`, `ref_chunks`, `guide_chunks`, and `guide_example_chunks` for export/debug snapshots, while clickable answer citations still come only from `sources`.
- Citation display names are file-name/source-key contracts. Prompt `文档名`, API `sources[].display_title/title`, and frontend `ReferenceRecord.displayTitle` must prefer the stable uploaded filename/source key (`metadata.source` in the current local pipeline; Huake `fileName` once supplied) over parser-derived PDF titles, OCR headings, section titles, bibliography text, or chunk content.
- Guide retrieval must classify guide documents from generic uploaded-document metadata such as `source`, `source_title`, `section_path`, or `clause_ids`; it must not filter for a fixed uploaded PDF name.

#### 3. Tests Required

- DG/designers-guide-only retrieval must return non-empty `RetrievalResult.chunks` when vector/BM25 and rerank produced candidates.
- Prompt tests must assert guide/example evidence is represented as `[Ref-N]`, not `[Guide-N]` / `[GuideExample-N]`.
- Generation tests must assert `sources` covers every citable guide/example chunk included in the `[Ref-N]` prompt ordering.
- Retrieval context tests may assert guide/example observability fields, but not at the expense of citable `chunks`.
- Frontend citation tests must assert uppercase `[REF-N]` is normalized to `[Ref-N]`, and legacy `[Guide-N]` text is not converted into a separate clickable namespace.
- Frontend export tests must assert `ref_chunks`, `guide_chunks`, and `guide_example_chunks` are present in Markdown retrieval context exports when supplied by the backend.
- Frontend/API tests must assert parser-derived `display_title/title` values do not override `source.file` for citation labels.

#### 4. Wrong vs Correct

##### Wrong

```python
final_chunks, scores, guide_chunks = _split_normative_and_guide_chunks(
    final_chunks,
    scores,
)
```

##### Correct

```python
guide_chunks = _collect_guide_chunks(final_chunks)
# final_chunks remains unchanged and citable.
```

### Scenario: Redis External Session History Payloads

#### 1. Scope / Trigger

- Trigger: any change to `/query`, `/query/stream`, `RedisConversationManager`, or external `sessionId` history behavior.
- Reason: external users read historical sessions directly from Redis. If the assistant message stores only answer text, reopened sessions lose the citation/source data that made `[Ref-N]` useful.

#### 2. Signatures

- API persistence helper: `_add_conversation_turn(conv_mgr, conversation_id, question, answer, *, sources=None, related_refs=None, retrieval_context=None, question_type=None, engineering_context=None, answer_mode=None, groundedness=None, thinking=None, response_payload=None) -> str | None`.
- Redis persistence entry point: `RedisConversationManager.add_turn_async(conversation_id, question, answer, *, title=None, sources=None, related_refs=None, retrieval_context=None, question_type=None, engineering_context=None, answer_mode=None, groundedness=None, thinking=None, response_payload=None) -> str | None`.
- Redis key: `context:{sessionId}` stores one JSON string per message.

#### 3. Contracts

- User messages remain minimal: `role`, `content`, `timestamp`.
- Assistant messages must preserve the same minimal fields plus optional historical display metadata when available:
  - `sources`: JSON-ready source objects using the external source aliases (`docId`, `elementType`, `originalText`, `locatorText`, `highlightText`) while preserving `file` and any upstream `source` field.
  - `relatedRefs`: related reference labels.
  - `retrievalContext`: export/debug snapshot with main, parent, guide, guide-example, and reference chunks when present.
  - `questionType`, `engineeringContext`, `answerMode`, `groundedness`: answer-state metadata for historical display and diagnostics.
  - `thinking`: concatenated text from streamed `reasoning` events when present.
  - `response`: full final `/query/stream` `done` payload snapshot, including fields the external client received.
- Python call sites use snake_case keyword arguments; Redis JSON payload fields use the external camelCase contract.
- Redis history reads for generation should continue converting messages to `{"question", "answer"}` only; citation metadata is a display/export snapshot, not prompt history.
- The persistence helper must remain compatible with legacy conversation managers that accept only `(conversation_id, question, answer)`.
- Redis external session history must not set TTL/expiration on `context:{sessionId}`; history cleanup is explicit deletion, not time-based expiry.

#### 4. Validation & Error Matrix

- Assistant answer has sources -> Redis assistant message includes `sources`.
- Assistant answer has retrieval context -> Redis assistant message includes `retrievalContext`.
- Stream emits reasoning events -> Redis assistant message includes `thinking`, and `response.thinking` matches it.
- Stream persists an external session -> Redis assistant message includes `response` with the final done payload snapshot.
- Metadata is absent or empty -> Redis assistant message may omit that optional field.
- Legacy Redis messages without metadata -> history loading still returns Q&A history.
- Legacy in-memory/test manager lacks metadata kwargs -> helper falls back to the three-argument call.
- Redis turn persistence -> no `EXPIRE` call is issued for `context:{sessionId}`.

#### 5. Good/Base/Bad Cases

- Good: a streamed external-session answer with `[Ref-1]` stores answer text, `sources`, `relatedRefs`, `retrievalContext`, `questionType`, `answerMode`, `groundedness`, `thinking`, and `response` in the assistant Redis message.
- Base: a chat/fallback answer with no sources stores only the role/content/timestamp fields.
- Bad: storing source fields only in the HTTP/SSE response while Redis keeps only answer text.

#### 6. Tests Required

- Unit tests must inspect the raw Redis list payload and assert assistant messages preserve source document/file fields.
- Helper tests must assert metadata is forwarded to async managers that support kwargs.
- Helper tests must assert managers with the legacy three-argument signature still work.
- Stream tests must cover at least one external `sessionId` path and assert streamed reasoning is persisted as `thinking` plus `response.thinking`.

#### 7. Wrong vs Correct

##### Wrong

```python
await conv_mgr.add_turn_async(conversation_id, question, answer)
```

##### Correct

```python
await conv_mgr.add_turn_async(
    conversation_id,
    question,
    answer,
    sources=response.sources,
    retrieval_context=response.retrieval_context,
    question_type=response.question_type,
    groundedness=response.groundedness,
)
```

### Scenario: Retrieval Source Filter Equivalence

#### 1. Scope / Trigger

- Trigger: any change to `HybridRetriever` source filters, source alias parsing, query-understanding source extraction, or backend search integration with Elasticsearch/Milvus.
- Reason: user-facing filters such as `EN 1992` must constrain every retrieval path equivalently. If one backend cannot express the fuzzy source filter, off-source vector hits can survive reranking and make users think the target document was not retrieved.

#### 2. Signatures

- Query-understanding filter: `extract_filters(question: str) -> dict[str, str]`.
- Vector retrieval: `HybridRetriever._vector_search(query: str, top_k: int, filters: dict) -> list[dict]`.
- BM25 retrieval: `HybridRetriever._bm25_search(query: str, top_k: int, filters: dict, ...) -> list[dict]`.
- Source helpers: `_build_source_filter_clauses(filters)`, `_build_milvus_source_expr(source)`, `_filter_results_by_source(results, filters)`.

#### 3. Contracts

- `filters["source"]` is a user-facing source selector, not a search boost.
- Elasticsearch and Milvus paths must return semantically equivalent source-constrained results.
- When Milvus cannot express a yearless Eurocode filter such as `EN 1992`, vector results must be filtered after `collection.search()`.
- A yearless `EN 1992` filter may match indexed source IDs for the same document family, including `EN1992-1-1_2004` and guide IDs that embed `EN1992-...`.
- Numeric substrings alone must not match. `Guide 1992 example` and `EN19920` are not valid matches for `EN 1992`.

#### 4. Validation & Error Matrix

- Exact source alias match -> keep the result.
- Yearless Eurocode family match -> keep only sources whose parsed EN code equals the requested code or starts with the requested code plus `-`.
- Plain numeric substring match without an EN code -> drop the result.
- Backend expression is `None` because the backend cannot encode the filter -> apply result-layer filtering before merging/reranking.
- Missing `source` in a row while `filters["source"]` is present -> drop the result.

#### 5. Good/Base/Bad Cases

- Good: `filters={"source": "EN 1992"}` keeps `EN1992-1-1_2004` and `DG_EN1992-1-1__-1-2`, then excludes `DG EN1990`.
- Base: `filters={"source": "EN 1992:2004"}` can be represented as exact aliases and remains backend-filtered.
- Bad: vector search omits the Milvus expression for `EN 1992`, returns all sources, and relies on later reranking to remove off-source chunks.

#### 6. Tests Required

- Unit tests must cover yearless Eurocode filters against positive and negative indexed source IDs.
- Tests must include at least one off-source Eurocode (`DG EN1990`) and one numeric false positive (`Guide 1992 example` or `EN19920`).
- Integration-style retrieval checks should assert final chunks do not include off-source documents when `filters["source"]` is set.

#### 7. Wrong vs Correct

##### Wrong

```python
# Wrong: no backend expr and no post-filter means vector search spans all sources.
expr = _build_milvus_source_expr(filters["source"])
return collection.search(..., expr=expr)
```

##### Correct

```python
# Correct: apply the user-facing source contract even when Milvus expr is absent.
rows = collection.search(..., expr=expr)
return _filter_results_by_source(rows, filters)
```

### Scenario: Repo-Versioned systemd Deployment Units

#### 1. Scope / Trigger

- Trigger: any change that adds or updates `deploy/systemd/*.service` or the accompanying deployment README for running Euro_QA under systemd.
- Reason: systemd deployment is an infra contract. The unit files must keep the backend, frontend, and search stack alive independently of SSH sessions, and they must remain safe to install on a Linux host.

#### 2. Signatures

- Backend unit: `deploy/systemd/euroqa-backend.service`
- Frontend unit: `deploy/systemd/euroqa-frontend.service`
- Search stack unit: `deploy/systemd/euroqa-search-stack.service`
- Documentation: `deploy/systemd/README.md`
- Deployment path contract: `WorkingDirectory=/home/root251/euroqa` by default
- Service identity contract: `User=root251`, `Group=root251` by default

#### 3. Contracts

- Backend unit must:
  - run `uv run uvicorn server.main:app --host 0.0.0.0 --port 8080`
  - omit `--reload`
  - use `Restart=on-failure`
  - depend on the search stack unit before startup
- Frontend unit must:
  - run `pnpm --dir frontend build` before preview start
  - run `pnpm --dir frontend preview --host 0.0.0.0 --port 4173`
  - use `Restart=on-failure`
  - keep the preview command separate from the build step
- Search stack unit must:
  - start the Compose services `milvus-etcd`, `milvus-minio`, `milvus`, and `elasticsearch`
  - stop them with `docker compose stop`
  - use `Restart=on-failure`
- Deployment README must document:
  - install/update commands
  - start/stop/status/log commands
  - rollback/disable commands
  - the path/user replacement step when the host differs from the default
- If the deployment user or path changes, every unit file reference must be updated together:
  - `User=`
  - `Group=`
  - `WorkingDirectory=`
  - `Documentation=`
  - any user-home `PATH` fragment

#### 4. Validation & Error Matrix

- Backend unit contains `--reload` -> invalid for systemd deployment; remove it.
- Frontend unit uses `pnpm dev` -> invalid for a persistent service; use build + preview.
- Frontend unit omits the build pre-step -> invalid; preview must be preceded by `pnpm build`.
- Search unit uses detached Compose startup without a persistent main process -> invalid; systemd must supervise the foreground Compose process.
- Deployment path or user changes partially updated in only one file -> invalid; update all matching unit fields and docs together.
- `systemd-analyze verify` unavailable in the local environment -> acceptable for authoring, but keep the unit syntax simple and structurally valid.

#### 5. Good/Base/Bad Cases

- Good: a repo-versioned `deploy/systemd/*.service` set can be copied to `/etc/systemd/system/`, then enabled with `systemctl`.
- Base: the default Linux host matches `root251` and `/home/root251/euroqa`, so the README commands work as written.
- Bad: a unit file that only works inside the current SSH session or relies on `--reload` for long-lived service execution.

#### 6. Tests Required

- Verify each unit file has valid `[Unit]`, `[Service]`, and `[Install]` sections.
- Verify the backend unit has no `--reload` and targets port `8080`.
- Verify the frontend unit builds before preview and targets port `4173`.
- Verify the search unit references the expected Compose services and stop command.
- Verify the README includes install, start, stop, status, log, and rollback commands.
- When the local environment supports it, run `systemd-analyze verify` on the generated unit files.

#### 7. Wrong vs Correct

##### Wrong

```ini
[Service]
WorkingDirectory=/home/root251/euroqa/frontend
ExecStart=/usr/bin/env pnpm dev
```

##### Correct

```ini
[Service]
WorkingDirectory=/home/root251/euroqa
ExecStartPre=/usr/bin/env pnpm --dir frontend build
ExecStart=/usr/bin/env pnpm --dir frontend preview --host 0.0.0.0 --port 4173
```

### Scenario: PDF Parser Page Metadata Integrity

#### 1. Scope / Trigger

- Trigger: any change to PDF parsing, parser-provider integration, parser output merging, or citation/highlight metadata.
- Reason: LLM answers expose source pages to users. A wrong page citation is worse than a failed parse.

#### 2. Signatures

- Parser entry point: `parse_pdf(pdf_path: Path, output_dir: Path, config: PipelineConfig) -> Path`.
- Successful parser output must be one logical document artifact set:
  - `{doc_id}.md`
  - `{doc_id}_content_list.json`
  - `{doc_id}_meta.json`

#### 3. Contracts

- `content_list[*].page_idx` must always mean the original PDF's 0-based page index before downstream structuring sees it.
- `page_numbers` derived downstream must therefore mean original PDF 1-based page numbers.
- `bbox_page_idx` must use the same original-PDF 0-based coordinate system as `content_list[*].page_idx`.
- If a provider requires internal PDF splitting, split part names and part-local page indexes must not leak into final document identity or citation metadata.

#### 4. Validation & Error Matrix

- Missing `content_list` for split parser output -> fail the parse.
- Empty or non-list `content_list` for split parser output -> fail the parse.
- Any page-bearing item without integer `page_idx` -> fail the parse.
- Any part-local `page_idx < 0` or `page_idx >= part_page_count` -> fail the parse.
- Any merged `page_idx >= original_page_count` -> fail the parse.
- Any inability to read the original PDF page count -> fail the parse.

#### 5. Good/Base/Bad Cases

- Good: a 201-page PDF is split internally; part 2 local `page_idx=0` becomes final `page_idx=200`, downstream `page_numbers=[201]`, and final artifacts keep the original document ID.
- Base: a PDF within provider limits is parsed as one part and still records `original_page_count` in metadata.
- Bad: splitting into user-visible part documents or accepting part-local `page_idx` values in final content lists.

#### 6. Tests Required

- Unit tests must prove page offset propagation from split part output into final `content_list`.
- Tests must prove downstream `parse_markdown_to_tree()` returns original-document `page_file_index`, `page_numbers`, and `bbox_page_idx`.
- Tests must cover non-text page-bearing entries such as image/table entries.
- Tests must assert fail-closed behavior leaves no successful final parse artifacts for invalid page metadata.

#### 7. Wrong vs Correct

##### Wrong

```python
# Wrong: keep part-local page_idx in final content_list.
merged_items.extend(part_content_list["items"])
```

##### Correct

```python
# Correct: convert every item from part-local to original-PDF coordinates.
adjusted = dict(item)
adjusted["page_idx"] = item["page_idx"] + part_page_offset
merged_items.append(adjusted)
```

### Scenario: Citation Document Identity

#### 1. Scope / Trigger

- Trigger: any change to answer source construction, retrieval context export, document ingestion identity, or frontend PDF reference opening.
- Reason: citation links open `/api/v1/documents/{document_id}/file`. If `document_id` is a display-label derivative instead of an existing document id, the endpoint returns JSON 404 and PDF viewers fail with invalid PDF structure.

#### 2. Signatures

- Chunk metadata field: `ChunkMetadata.document_id: str | None`.
- Answer source field: `Source.document_id: str`.
- Retrieval context item field: `retrieval_context.chunks[*]["document_id"]`.
- File endpoint: `GET /api/v1/documents/{doc_id}/file`.

#### 3. Contracts

- `Source.document_id` and retrieval-context `document_id` must identify a document that can be fetched from the document file endpoint.
- If `ChunkMetadata.document_id` is present, source construction must prefer it over deriving an id from `metadata.source`.
- If `metadata.source` is already a `.pdf` filename used by the document list, preserve it exactly, including parentheses and punctuation.
- Only use `_build_document_id()` for legacy non-PDF source labels such as `EN 1990:2002`.
- Frontend reference mapping may use `source.document_id` directly only when it exists in the current document list; otherwise it must fall back to matching `source.file` against the document list.

#### 4. Validation & Error Matrix

- External parse request provides `docId` -> pipeline stores chunks under that `docId`; citations must keep that id.
- Uploaded/indexed document id contains repeated underscores, parentheses, or punctuation -> citations must preserve the exact id when it is the file endpoint id.
- Stale source `document_id` not found in `/documents` but `file` matches a listed document -> frontend must open the matched document id.
- Missing id and non-PDF display label -> legacy normalization may derive a stable id.

#### 5. Good/Base/Bad Cases

- Good: `document_id="huake-doc-123"` and `file="Original File Name.pdf"` opens `/documents/huake-doc-123/file`.
- Base: `file="EN1992-1-1_2004(1).pdf"` opens `/documents/EN1992-1-1_2004(1).pdf/file`.
- Bad: `file="EN1992-1-1_2004(1).pdf"` is rewritten to `EN1992-1-1_2004_1_pdf` and the PDF viewer receives a JSON 404 body.

#### 6. Tests Required

- Backend source-construction tests must cover exact PDF filename preservation.
- Backend source-construction tests must cover explicit external `document_id` precedence.
- Answer generation tests must assert retrieval context exports the resolved `document_id`.
- Frontend tests must cover stale `source.document_id` falling back to file-name document matching.

#### 7. Wrong vs Correct

##### Wrong

```python
document_id = _build_document_id(chunk.metadata.source)
```

##### Correct

```python
document_id = _resolve_document_id(chunk)
```

### Scenario: Token Accounting and Spot-Check Metrics

#### 1. Scope / Trigger

- Trigger: any change to shared token counters, retrieval diagnostic logging, spot-check JSONL fields, or prompt-token accounting.
- Reason: spot-check logs are used to diagnose retrieval/rerank/generation failures. If token counts are estimates when the provider can report exact usage, or if diagnostic fields have unstable shapes, later analysis produces false conclusions.

#### 2. Signatures

- Token counter: `count_for_llm(text: str, model: str) -> tuple[int, bool]`.
- Qwen embedding counter path: `count_for_embedding(text: str, model: str) -> tuple[int, bool]`.
- Rerank diagnostic fields:
  - `rerank_input_tokens: list[dict[str, object]]`
  - `rerank_truncated: list[dict[str, object]]`
- Prompt diagnostic field:
  - `final_prompt_tokens: {"value": int, "is_estimate": bool, "model": str}`

#### 3. Contracts

- Closed-source Qwen LLM models served through DashScope OpenAI-compatible chat completions must be counted via `usage.prompt_tokens`, not `dashscope.Tokenization`.
- Qwen embedding models may keep using DashScope tokenization when the embedding endpoint needs token accounting; do not route embedding counting through chat completions.
- If exact LLM usage is unavailable, token counters must return `(char_estimate, True)` and log a warning without failing answer generation.
- Spot-check diagnostic collection fields must be JSON-native and schema-stable. Per-chunk metrics must use `list[dict]`, not a chunk-id keyed dict that can be confused with recorder field maps or serialized enum objects.
- Any enum-like metadata written to spot-check logs must be converted to its JSON string value before recording.

#### 4. Validation & Error Matrix

- Qwen chat completion returns `usage.prompt_tokens` -> `count_for_llm()` returns that value with `is_estimate=False`.
- Qwen chat completion fails or omits prompt usage -> `count_for_llm()` falls back to char estimate with `is_estimate=True`.
- Qwen embedding tokenization succeeds -> `count_for_embedding()` may return exact embedding input tokens.
- Rerank input token logging sees N candidate chunks -> both `rerank_input_tokens` and `rerank_truncated` contain N dict entries.
- A chunk has `ElementType.TEXT` metadata -> spot-check JSON records `"text"`, not an enum object repr.

#### 5. Good/Base/Bad Cases

- Good: `final_prompt_tokens={"value": 11802, "is_estimate": false, "model": "qwen3.6-flash"}` after a DashScope OpenAI-compatible Qwen answer call.
- Base: unknown LLM aliases fall back to estimates and mark `is_estimate=true`.
- Bad: `dashscope.Tokenization.call(model="qwen3.6-flash")` is used for LLM prompt counting and returns `Model not supported`, forcing avoidable estimates.
- Bad: `rerank_truncated` is recorded as `{"chunk-a": false}` or contains enum objects, making downstream JSONL analysis fragile.

#### 6. Tests Required

- Unit tests must mock OpenAI-compatible Qwen usage and assert exact `prompt_tokens` are returned.
- Unit tests must prove Qwen embedding counting still uses the embedding/tokenization path.
- Unit tests must cover missing usage fallback.
- Retrieval tests must assert `rerank_input_tokens` and `rerank_truncated` are `list[dict]` with JSON-native `element_type` strings.

#### 7. Wrong vs Correct

##### Wrong

```python
# Wrong: new Qwen LLM models can be listed by /v1/models but still rejected by
# the legacy tokenization endpoint.
tokenization.call(model="qwen3.6-flash", prompt=prompt)
```

##### Correct

```python
# Correct: count the actual chat-serving path by reading provider usage.
response = client.chat.completions.create(
    model="qwen3.6-flash",
    messages=[{"role": "user", "content": prompt}],
    max_tokens=1,
)
tokens = response.usage.prompt_tokens
```

##### Wrong

```python
record_spot_check("rerank_truncated", {"chunk-a": False})
```

##### Correct

```python
record_spot_check(
    "rerank_truncated",
    [{"chunk_id": "chunk-a", "tokens": 377, "max_tokens": 8192, "truncated": False}],
)
```

<!-- Patterns that must always be used -->

---

## Testing Requirements

<!-- What level of testing is expected -->

- Parser metadata changes require focused tests for downstream citation metadata, not only provider API request/response behavior.

### Scenario: Parse Context Summary Toggle

#### 1. Scope / Trigger

- Trigger: any change to document parsing, parse queue payloads, or stage 3.5 contextual enrichment.
- Reason: the parse request is accepted by the API first, then consumed later by the worker. If the enable/disable flag is not persisted with the parsed document, async workers and restart/resume flows will ignore the caller's intent.

#### 2. Signatures

- API request model: `DocumentParseRequest.context_summary_enabled: bool = True`
- External JSON field: `contextSummaryEnabled` for `POST /api/v1/documents/parse`
- Multipart field: `contextSummaryEnabled` for `POST /api/v1/documents/upload-to-minio`
- Legacy multipart field: `context_summary_enabled` remains accepted for compatibility
- Pipeline config: `PipelineConfig.context_summary_enabled: bool = True`
- Parse helper: `parse_pdf(..., context_summary_enabled: bool = True) -> Path`
- Worker entry: `run_single_document(doc_id, pipeline_config, on_progress=None) -> dict[str, int]`
- Parse sidecar: `parsed_dir/{doc_id}/parse_options.json`

#### 3. Contracts

- Default behavior must remain enabled. Missing request fields, missing sidecar files, or malformed sidecar payloads should fall back to `True`.
- `POST /api/v1/documents/parse` must persist the effective value before queueing so the worker can read it after the HTTP request returns.
- `POST /api/v1/documents/upload-to-minio` must pass the same flag shape as the JSON parse endpoint.
- When the flag is `false`, stage 3.5 contextual enrichment must be skipped, but parsing, structure, chunking, and indexing still run.
- Batch `parse_all_pdfs()` must also forward the global config flag into `parse_pdf()` so CLI rebuilds respect the same toggle.

#### 4. Validation & Error Matrix

- Missing `contextSummaryEnabled` -> default to `true`
- Invalid or unreadable `parse_options.json` -> worker logs a warning and falls back to `PipelineConfig.context_summary_enabled`
- `false` flag provided -> do not call `enrich_chunks()` and mark stage 3.5 as skipped in pipeline debug output
- `true` flag provided -> call `enrich_chunks()` and preserve existing stage 3.5 behavior

#### 5. Good/Base/Bad Cases

- Good: `contextSummaryEnabled=false` skips stage 3.5 for one upload but still indexes chunks.
- Base: `contextSummaryEnabled=true` continues to generate contextual summaries and embedding text.
- Bad: storing the flag only in the request object and never persisting it for the worker.

#### 6. Tests Required

- API tests must assert `parse_options.json` contains the effective boolean for both `/documents/parse` and `/documents/upload-to-minio`.
- Parse tests must assert `_meta.json` contains `context_summary_enabled`.
- Worker tests must assert `run_single_document()` passes the flag into `parse_pdf()` and skips `enrich_chunks()` when disabled.
- CLI pipeline tests must assert stage 3.5 is skipped when the metadata flag is false.

#### 7. Wrong vs Correct

##### Wrong

```python
async def parse_document(request: DocumentParseRequest, config=Depends(get_config)):
    tm.enqueue(request.doc_id)
```

##### Correct

```python
def _persist_parse_options(request: DocumentParseRequest, config) -> None:
    parsed_dir = Path(config.parsed_dir) / request.doc_id
    (parsed_dir / "parse_options.json").write_text(
        json.dumps({"context_summary_enabled": request.context_summary_enabled}),
        encoding="utf-8",
    )
```

---

### Scenario: Agent Tool-Call Invariants and Dispatch-Layer Guards

#### 1. Scope / Trigger

- Trigger: any change to `server/agents/qa_agent.py` decision schema, agent prompt, `EvidenceBundle` semantics, agent tools that mutate the bundle, or the agent dispatch path in `server/api/v1/query.py`.
- Reason: structured agent decisions (`AgentDecision`) carry an `action` value that downstream code (generation, citation, answerMode mapping) interprets as a promise about tool side effects. When the agent emits `action="compose_rag"` but skips the `retrieve` tool, the bundle stays empty, the generator falls into `groundedness="not_grounded"`, and the user sees a misleading "no evidence" answer that hides a behavior bug. The conversation-history shortcut (LLM treating a prior assistant answer as a substitute for re-retrieving) is the dominant trigger.

#### 2. Signatures

- Agent decision: `AgentDecision(action: Literal["compose_rag","chat","clarify"], direct_reply: str | None)`.
- Evidence bundle: `EvidenceBundle(chunks, parent_chunks, guide_chunks, guide_example_chunks, ref_chunks, scores, glossary_hits, groundedness, resolved_refs, unresolved_refs, tool_trace)`.
- Retrieve tool: `@function_tool retrieve(ctx, query) -> str` (writes `bundle.add_retrieval(result)` and appends `{"tool": "retrieve", ...}` to `bundle.tool_trace`).
- Dispatch guard: `_ensure_retrieve_called_for_compose_rag(*, decision, bundle, deps, question, conversation_id) -> AgentDecision`.
- Agent runner: `run_qa_agent(agent, question, deps, max_turns=5) -> tuple[AgentDecision, EvidenceBundle]`.

#### 3. Contracts

- `action="compose_rag"` is a contract that the agent gathered evidence this turn. The dispatch layer must validate this contract before invoking generation.
- The source of truth for "did the agent call a tool this turn" is `bundle.tool_trace`, not `bundle.is_empty`. `tool_trace` distinguishes "tool not called" (no entry) from "tool called and returned zero chunks" (entry with `chunk_count=0`). These two cases require different remediation.
- If `decision.action == "compose_rag"` and no `retrieve` entry exists in `bundle.tool_trace`, the dispatch must force one `_retrieve_impl(RunContextWrapper(deps), question)` call before continuing.
- If the recovery retrieval still yields `bundle.is_empty`, the dispatch must downgrade the decision to `AgentDecision(action="clarify", direct_reply=<explicit hint>)` rather than emit `answerMode="fallback"` with zero sources. The hint must instruct the user to supply a规范号, 构件类型, or 参数名称.
- The guard must emit `structlog` warning `agent_compose_rag_without_retrieve` with `conversation_id` and `question` fields whenever it fires.
- Both `/query` and `/query/stream` must call the same guard helper. Asymmetric patching of one path but not the other is forbidden.
- Agent prompt rules that gate tool-call obligations must use硬性 / 必须 language at the top of the instructions, not 适用于 / 先调用 buried in section-level guidance. Soft language is structurally insufficient when the SDK's structured-output mode allows tool-free returns.
- Agent prompt must explicitly forbid skipping `retrieve` because conversation history already contains a prior assistant answer to the same question. This is the most common trigger of the bug.
- Do not set `ModelSettings(tool_choice="required")` as a remedy; it breaks the legitimate `chat` and `clarify` paths that must not call tools.

#### 4. Validation & Error Matrix

- `decision.action != "compose_rag"` -> guard is a no-op; return decision unchanged.
- `decision.action == "compose_rag"` and `any(t["tool"] == "retrieve" for t in bundle.tool_trace)` -> guard is a no-op; trust the agent.
- `decision.action == "compose_rag"` and no `retrieve` in `tool_trace` -> log warning, call `_retrieve_impl` once with the original `req.question`.
- After recovery: `bundle.is_empty` is `True` -> downgrade to `clarify` with hint.
- After recovery: `bundle.is_empty` is `False` -> keep `compose_rag`, let `groundedness` flow naturally to `cautious` or `standard`.
- `_retrieve_impl` raises during recovery -> log `agent_compose_rag_recovery_retrieve_failed` and treat as still-empty (downgrade to clarify).
- The dispatch helper `_run_agent_dispatch` must return `(decision, bundle, conv, deps)` (4-tuple) so both call sites can pass `deps` into the guard.

#### 5. Good/Base/Bad Cases

- Good: turn-3 of a repeat-question session. Agent (with hardened prompt) calls `retrieve` even though history has the answer; bundle has 16 chunks; `answerMode="cautious"`; guard never fires.
- Base: turn-1 of any session. Agent calls `retrieve` naturally; same path as Good.
- Base: empty-retrieval case where agent calls `retrieve` and gets zero results legitimately; `bundle.tool_trace` has `chunk_count=0` entry; guard is no-op; `answerMode="fallback"` is the honest representation.
- Bad: dispatch trusts `decision.action == "compose_rag"` and feeds `bundle.chunks=[]` into `generate_answer_stream`. User sees `answerMode="fallback"` with retrieval that actually would have returned 16 chunks. This is the bug class.
- Bad: using `bundle.is_empty` instead of `tool_trace` to detect the skip. The agent might have called retrieve and gotten zero results, which is a legitimate state that does not need recovery — only the "no call at all" case does.
- Bad: prompt that says "compose_rag 适用于明确的规范相关问题。先调用 retrieve 收集证据..." — soft language. The LLM treats it as recommendation, not requirement.

#### 6. Tests Required

- Unit test: `decision.action="compose_rag"` with empty `tool_trace` and a fake `_retrieve_impl` that populates the bundle -> guard returns `compose_rag`, bundle non-empty.
- Unit test: `decision.action="compose_rag"` with empty `tool_trace` and a fake `_retrieve_impl` that returns zero chunks -> guard returns `AgentDecision(action="clarify", direct_reply=...)`.
- Unit test: `decision.action="chat"` and `decision.action="compose_rag"` with `tool_trace` already containing `retrieve` -> guard is no-op, returns original decision identity.
- Prompt assertion test: `_QA_AGENT_INSTRUCTIONS` contains the literal strings `"必须先调用 retrieve"` and `"硬性"` so prompt softening regressions fail in CI.
- Regression test: agent run with `Runner.run` returning `compose_rag` and empty bundle exposes the buggy state without recovery (anchors the bug class for future readers).
- End-to-end manual: same `sessionId` runs `Q1 (规范问题) → Q2 (你好) → Q3 (= Q1)`. Turn-3 `done` event must have `answerMode != "fallback"` and non-empty `retrievalContext.chunks`.

#### 7. Wrong vs Correct

##### Wrong

```python
# Dispatch trusts the agent's structural output without validating tool side effects.
decision, bundle, conv = await _run_agent_dispatch(...)
if decision.action == "compose_rag":
    async for event in generate_answer_stream(chunks=bundle.chunks, ...):
        ...
```

##### Correct

```python
# Validate the compose_rag contract before generation.
decision, bundle, conv, deps = await _run_agent_dispatch(...)
decision = await _ensure_retrieve_called_for_compose_rag(
    decision=decision,
    bundle=bundle,
    deps=deps,
    question=req.question,
    conversation_id=conv.conversation_id,
)
if decision.action == "compose_rag":
    async for event in generate_answer_stream(chunks=bundle.chunks, ...):
        ...
```

##### Wrong

```python
# Soft prompt: LLM treats this as a hint, skips retrieve when history has prior answer.
"""
### action = "compose_rag"
适用于明确的规范相关问题。先调用 retrieve 收集证据。
"""
```

##### Correct

```python
# Hard prompt: explicit precondition + forbidden shortcut.
"""
## 硬性规则（违反将导致系统报错并被拦截）
- 设置 action="compose_rag" 之前，本轮必须先调用 retrieve 工具至少一次
- 不允许以"历史对话已有同样回答"为理由跳过 retrieve
"""
```

##### Wrong

```python
# Conflating "tool not called" with "tool returned empty".
if decision.action == "compose_rag" and bundle.is_empty:
    await _retrieve_impl(...)  # double-retries the legitimate empty case
```

##### Correct

```python
# tool_trace tells you whether the tool was invoked at all.
retrieve_called = any(t.get("tool") == "retrieve" for t in bundle.tool_trace)
if decision.action == "compose_rag" and not retrieve_called:
    await _retrieve_impl(...)
```

---

## Code Review Checklist

<!-- What reviewers should check -->

(To be filled by the team)
