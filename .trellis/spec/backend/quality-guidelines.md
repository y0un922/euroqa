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
- Reason: answers must cite normative standard evidence for conclusions. Guide or commentary PDFs may help users understand a calculation path, but they must not become primary normative evidence.

#### 2. Contracts

- `RetrievalResult.chunks` must contain normative evidence only.
- `RetrievalResult.guide_chunks` and `RetrievalResult.guide_example_chunks` are the only retrieval result fields for guide/commentary/example evidence.
- Prompt builders must render normative evidence and guide evidence in separate sections.
- Response `sources` must be built from citable normative chunks and cross-reference chunks, not guide-only chunks.
- Guide retrieval must classify guide documents from generic uploaded-document metadata such as `source`, `source_title`, `section_path`, or `clause_ids`; it must not filter for a fixed uploaded PDF name.

#### 3. Tests Required

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

#### 4. Validation & Error Matrix

- Assistant answer has sources -> Redis assistant message includes `sources`.
- Assistant answer has retrieval context -> Redis assistant message includes `retrievalContext`.
- Stream emits reasoning events -> Redis assistant message includes `thinking`, and `response.thinking` matches it.
- Stream persists an external session -> Redis assistant message includes `response` with the final done payload snapshot.
- Metadata is absent or empty -> Redis assistant message may omit that optional field.
- Legacy Redis messages without metadata -> history loading still returns Q&A history.
- Legacy in-memory/test manager lacks metadata kwargs -> helper falls back to the three-argument call.

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

- Tests for guide retrieval must include an arbitrary guide-like uploaded document name, not a fixed project seed document.
- Tests must prove guide-like chunks are excluded from `RetrievalResult.chunks`.
- Tests must prove `guide_chunks` remains present in API retrieval context for backward compatibility.

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

---

## Code Review Checklist

<!-- What reviewers should check -->

(To be filled by the team)
