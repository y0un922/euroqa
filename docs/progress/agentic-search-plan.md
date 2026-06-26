# Agentic Search Plan for Euro_QA

## Project Background

Euro_QA is a RAG system for Eurocode and European structural engineering standards. It is used to answer engineering questions that often require clause, table, formula, annex, and cross-standard evidence.

The current backend already has these capabilities:

- Parsed documents are indexed into Elasticsearch and Milvus.
- Chunk metadata includes `source`, `source_title`, `object_label`, `object_aliases`, `object_id`, `clause_ids`, `section_path`, and related fields.
- `HybridRetriever` supports vector search, BM25, RRF fusion, reranking, parent chunk retrieval, and cross-reference closure — all within a single tightly-coupled pipeline.
- The agent layer has a `retrieve(query, top_k)` tool. It first runs `analyze_query`, then calls the retriever.
- Query understanding produces expanded queries, question type, target hint, requested objects, guide hint, engineering context, and intent label.
- `EvidenceBundle` collects chunks, parent chunks, guide chunks, and ref chunks before answer generation.
- The frontend can export full conversations and sources, which is useful for debugging retrieval failures.

Recent failures showed that compound standards questions can be under-retrieved. For example:

> 请给出混凝土结构设计中相关作用荷载和材料的分项系数。

The first answer often retrieved EN 1990 evidence for actions/load factors, but did not reliably retrieve EN 1992 material partial factor tables. A follow-up question could retrieve the missing evidence. This indicates that the core problem is not only answer prompting; it is that retrieval lacks multi-step evidence planning and explicit gap verification.

Some generic infrastructure bugs have already been fixed:

- KB `doc_id` and Elasticsearch `source` naming mismatches, such as `DG_EN1992-1-1__-1-2` vs `DG EN1992-1-1  -1-2`.
- National-prefix source parsing, such as `BS-EN-1990-2023`.
- Exact lookup mismatch between `object_label` and `object_aliases`.
- Inconsistent source filtering across ES, Milvus, and local result filtering.

However, we deliberately removed a different class of patches: hard-coded retrieval rules for `actions/materials`, `Table A1.2`, `Table 2.1N`, `Table 4.3`, `gamma_C/gamma_S`, etc. Those can fix one case, but they turn the system into a collection of per-question patches rather than a real agentic search system.

## Goal

Upgrade Euro_QA retrieval from "single retrieve call returns mixed chunks" to "agentic evidence search":

- The system dynamically plans what evidence is needed by decomposing compound questions into evidence slots.
- Each evidence slot is searched and verified independently.
- If evidence is missing, the system can refine the query and retry.
- Final answers only use verified evidence.
- The exported conversation includes a trace of what was searched, accepted, rejected, and left unresolved.

The goal is not to add more fallback rules. The goal is to make evidence search explicit, inspectable, and driven by a constrained agentic pipeline: the system fixes the stages and budgets, while an LLM planner can make bounded choices inside each stage.

## Non-Goals

- Do not add more topic-specific rules to `retrieval.py`.
- Do not hard-code mappings such as `concrete -> EN1992` or `actions -> EN1990`.
- Do not rely on one top-k rerank pass to decide whether evidence is complete.
- Do not encode one failed question as product logic.
- Do not rebuild a full tree index in the first phase. Start from existing metadata, chunk IDs, parent chunks, and object metadata.
- Do not implement an unbounded free-form agent loop for the first version. Start with a constrained agentic pipeline: fixed stages, schema-validated decisions, strict tool and retry budgets.
- Do not split the existing `HybridRetriever.retrieve()` pipeline into separate keyword/semantic tools for the first version.

## Current Problems

The current `retrieve(query)` tool has these limitations:

- It is too coarse-grained. The agent sends one query and receives a mixed list of chunks.
- Compound questions do not have explicit evidence slots. For example, "action partial factors" and "material partial factors" compete in the same retrieval pool.
- There is no direct tool for reading neighboring chunks around a hit.
- There is no verifier that explicitly decides whether a candidate chunk answers a specific sub-question.
- Conversation export shows sources, but not why those sources were searched, which candidates were rejected, or which evidence slot is missing.
- Groundedness is computed as a single scalar for the entire retrieval result. When one sub-question is grounded but another is missing, the system may report "grounded" overall and skip the missing evidence.

## Design Principles

### Preserve the HybridRetriever Pipeline

The existing `HybridRetriever.retrieve()` is not a simple search wrapper. It is a tightly-coupled pipeline that runs vector + BM25 in parallel, fuses via RRF, reranks, expands parent chunks, and resolves cross-references. Splitting this into separate `search_keyword` / `search_semantic` tools would:

- Lose RRF fusion quality (fusion requires seeing both result sets simultaneously).
- Require reimplementing rerank and post-processing logic in each tool.
- Create coordination complexity between tools that the current pipeline handles internally.

The correct approach is to call `HybridRetriever.retrieve()` once per slot with a slot-specific query, letting the pipeline do its job.

### Constrained Agentic Pipeline First, Free-Form Agent Loop Later

The first version should not be a fully free-form agent loop, but it should still preserve agentic flexibility where it matters. The split is:

- Fixed by the system: stages, feature flag, max slots, max retries, max tool calls, fallback path.
- Chosen by the planner within schema: evidence slots, slot queries, source hints, object labels, retry queries, and whether a slot needs object lookup or chunk opening.

This keeps the implementation controllable while still avoiding a rigid, hand-authored retrieval recipe. A fully free-form agent loop can be added later if this constrained pipeline proves too rigid.

### Rules-Based Verification First, LLM Verifier Later

Rerank scores tell you "this chunk is relevant to the query" but not "this chunk answers the slot." However, a full LLM verifier adds one LLM call per slot per round. For the first version, use tiered rules:

- **Object slot** (slot has explicit object labels like "Table 2.1N"): satisfied only if `object_label` or `object_aliases` matches in the result. Rerank score alone is not sufficient.
- **Ordinary slot** (conceptual sub-question): rerank score >= 0.85 → satisfied, >= 0.5 → partial, < 0.5 → missing. Combined with source trace verification.
- **Required slot override**: if a slot is marked `required` in the evidence plan, it must be independently verified. The system must not skip it because the overall retrieval scored "grounded."
- **Conservative labeling**: when in doubt, label as `partial` or `missing`, not `satisfied`. False negatives (retrying when evidence is actually there) are cheaper than false positives (skipping missing evidence).

LLM-based verification can be added in a later phase for slots where rule-based judgment is insufficient.

## Target Architecture

Add a constrained Agentic Evidence Search layer between `analyze_query` and the answer generator, calling into the existing `HybridRetriever`.

Current flow:

```text
QA Agent
  -> retrieve(query)
      -> analyze_query
      -> HybridRetriever.retrieve(...)
      -> EvidenceBundle
  -> Answer Generator
```

Target flow:

```text
QA Agent
  -> agentic_retrieve(question)
      -> analyze_query (basic query understanding)
      -> list_sources (KB/source inspection)
      -> plan_evidence(QueryAnalysis + source inventory)
      -> parallel: for each slot → HybridRetriever.retrieve(slot.query, slot.sources)
      -> optional per slot: lookup_object / open_chunk
      -> rules-based slot verification
      -> serial retry for missing/partial required slots
      -> VerifiedEvidenceBundle (slots + accepted/rejected/unresolved)
  -> Answer Generator (consumes per-slot evidence)
```

### Slot Search Parallelism

To avoid multiplying latency by slot count, the orchestrator runs the first round of slot searches in parallel:

```python
# Round 1: parallel search for all planned slots
slot_results = await asyncio.gather(*[
    retriever.retrieve(
        queries=slot.search_queries,
        original_query=question,
        filters=slot.source_filters,
        requested_objects=slot.object_labels,
        top_k=slot.top_k,
    )
    for slot in plan.slots
])

# Verify each slot with rules; optional object/open_chunk helpers are
# executed only when requested by the validated slot plan.
for slot, result in zip(plan.slots, slot_results):
    slot.status = evaluate_slot(slot, result)

# Round 2: serial retry for missing required slots only
for slot in [s for s in plan.slots if s.required and s.status == "missing"]:
    retry_result = await retriever.retrieve(
        queries=slot.retry_queries, ...
    )
    slot.status = evaluate_slot(slot, retry_result)
```

Latency for typical compound questions: ~1x retrieve (parallel first round) + ~1x retrieve (at most 1-2 retries).

## Core Data Structures

### EvidencePlan

`analyze_query()` remains responsible for basic understanding: query rewriting, expanded queries, question type, target hints, requested objects, guide hints, engineering context, and intent label.

`plan_evidence()` is a separate, focused planning step. It receives:

- the original question
- `QueryAnalysis`
- `list_sources()` output for the selected KB scope

It produces an `EvidencePlan` with bounded, schema-validated slots. This keeps prompts separated by responsibility: `analyze_query()` does not become a giant prompt, and `plan_evidence()` can reason explicitly about available source metadata.

The planner model should be configurable independently from the main answer model. This allows deployments to use a smaller, faster model for structured planning while keeping the answer model unchanged.

```python
class EvidenceSlot(BaseModel):
    id: str
    description: str                           # what must be answered
    search_queries: list[str]                  # expanded queries for this slot
    source_hints: list[str] | None = None      # optional hints from source inventory
    object_labels: list[str] | None = None     # Table/Figure/Expression to look up
    needs_object_lookup: bool = False
    needs_chunk_context: bool = False
    required: bool = True
    top_k: int = 8
    retry_queries: list[str] | None = None     # alternative queries if first round misses

class EvidencePlan(BaseModel):
    question: str
    source_inventory_summary: str
    slots: list[EvidenceSlot]
    planning_notes: str | None = None
```

For simple questions, `plan_evidence()` may return one slot or choose a fallback marker that tells the orchestrator to use the current retrieve path. For compound questions, it returns 2-4 slots, each with its own queries, source hints, and optional object labels.

Fallback rules:

- If `plan_evidence()` JSON parsing or schema validation fails, fall back to existing single `retrieve`.
- If `slots` is empty, fall back to existing single `retrieve`.
- If `slots` exceeds `AGENTIC_SEARCH_MAX_SLOTS`, keep the highest-priority required slots and record truncation in trace.
- If a slot has no `search_queries`, use `QueryAnalysis.expanded_queries` for that slot.

### EvidenceSlotResult

```json
{
  "slot_id": "slot_id",
  "status": "satisfied | partial | missing",
  "verification_method": "object_match | rerank_score | rule",
  "accepted_chunk_ids": ["..."],
  "rejected": [
    {"chunk_id": "...", "reason": "why not sufficient"}
  ],
  "queries_tried": ["..."],
  "sources_searched": ["..."],
  "rerank_top_score": 0.87,
  "notes": "short verification summary"
}
```

### VerifiedEvidenceBundle

Extension to the existing `EvidenceBundle`:

```python
@dataclass
class EvidenceBundle:
    # ... all existing fields ...
    slot_results: list[EvidenceSlotResult] | None = None  # new
    unresolved_slots: list[str] | None = None             # new
```

The `groundedness` field semantics change: instead of a single scalar from the top rerank score, it becomes "all required slots satisfied" → grounded, "some required slots partial/missing" → partial, "no required slots satisfied" → not_grounded.

## Tool Design

### Existing Tools (unchanged)

#### `retrieve(query, top_k=8)`

The existing agent tool. In the agentic path, it is called internally by the orchestrator per slot rather than directly by the agent. In the non-agentic path (feature flag off), it continues to work as before.

#### `lookup_glossary(term)`

Unchanged.

### New Tools / Planner Inputs

#### `list_sources()`

Input: current request KB scope.

Output: source list with `source`, `source_title`, `doc_id`, document type hints, and optionally object counts.

Purpose: let the planner inspect the available KB scope before searching. The agent should not assume EN 1990 or EN 1992 exists.

This should be a formal tool, not just an internal helper. It is useful beyond search:

- knowledge-base document tagging
- source classification
- version and national annex discovery
- identifying whether a KB contains standards, design guides, examples, or mixed material
- debugging source-scope problems in exported traces

#### `lookup_object(label, sources=None)`

Uses `object_label`, `object_aliases`, and `object_id`.

Best for:

- `Table 2.1N`
- `Expression (6.10)`
- `Clause 2.4.2.4`
- figures and annexes

This reuses the current object alias logic and ES term queries. It is independent of the HybridRetriever pipeline and does not require RRF fusion. In the first version, the orchestrator calls it only when the plan asks for object lookup; later it can also be exposed for direct agent use.

#### `open_chunk(chunk_id, neighbors=1)`

Reads the chunk content, metadata, and neighboring or parent chunks.

Purpose:

- Avoid judging an isolated table without its surrounding clause.
- Give verification and answer generation enough context to decide whether evidence is actually relevant.
- Useful for manual debugging and trace inspection.

## Slot Verification Rules

### Object Slots

A slot that specifies `object_labels` (e.g., `["Table 2.1N"]`) is verified by checking whether any result chunk has a matching `object_label` or `object_aliases` entry. Rerank score alone is not sufficient — a high-scoring chunk about "Table 2.1" from a different standard does not satisfy a request for "Table 2.1N."

```python
def verify_object_slot(slot, chunks):
    target_labels = normalize_labels(slot.object_labels)
    for chunk in chunks:
        chunk_labels = {chunk.metadata.object_label} | set(chunk.metadata.object_aliases)
        if target_labels & normalize_labels(chunk_labels):
            return "satisfied", [chunk.chunk_id]
    return "missing", []
```

### Ordinary Slots

A slot without explicit object labels is verified by rerank score and source trace:

- Top rerank score >= 0.85 → `satisfied`
- Top rerank score >= 0.5 → `partial`
- No results or top score < 0.5 → `missing`

### Required Slot Override

If a slot is `required: true`, it is never automatically satisfied by the overall groundedness signal. Each required slot must pass its own verification independently. This prevents the failure mode where slot A's strong evidence masks slot B's absence.

## Answer Generation

The answer generator should consume slot-level evidence:

Inputs:

- satisfied slots and their accepted chunks
- partial/missing slots
- unresolved slots and reasons

Behavior:

- Cover every required slot.
- Cite accepted evidence per slot.
- If a slot is missing, say so explicitly: "未检索到关于 [slot description] 的相关证据。"
- Do not fill missing values from memory or general knowledge.
- Source ordering follows slot order, then rerank score within each slot.

## Debugging and Export

Conversation export should include an Agentic Search Trace:

```markdown
### Evidence Plan
- slot: action partial factors
  - required: true
  - queries: ["action partial factors EN 1990", ...]
  - object labels: ["Table A1.2(B)"]

- slot: material partial factors
  - required: true
  - queries: ["material partial factors concrete", ...]
  - object labels: ["Table 2.1N"]

### Search Trace
- slot: action partial factors
  - round 1: retrieve(queries=[...], sources=[...])
  - candidates: 8 chunks
  - verification: object_match → Table A1.2(B) found
  - status: satisfied

- slot: material partial factors
  - round 1: retrieve(queries=[...], sources=[...])
  - candidates: 6 chunks
  - verification: object_match → Table 2.1N not found
  - status: missing
  - round 2 (retry): retrieve(queries=[...], sources=[...])
  - candidates: 5 chunks
  - verification: object_match → Table 2.1N found
  - status: satisfied

### Unresolved Slots
- (none)
```

This allows failures to be diagnosed directly:

- The planner did not create a slot for a sub-question.
- The slot query did not match the right source.
- The source does not exist in the selected KB.
- The object alias lookup failed.
- Rerank buried the right chunk.
- A retry found what the first round missed.
- Answer generation ignored verified evidence.

## Implementation Plan

### Phase 0: Evaluation Baseline

**Rationale**: Without a baseline, we cannot know whether slot-based retrieval actually improves recall. This must come first.

Tasks:

- Extend `tests/eval/test_questions.json` with 10-20 compound retrieval questions covering:
  - Cross-standard compound questions (actions + materials).
  - Same table number in different standards.
  - Explicit object lookup (Table X, Expression Y).
  - National annex or version difference.
  - Mixed KB noise.
  - KB missing the required source.
- Run the existing eval harness (`tests/eval/test_eval_retrieval.py`) and record baseline metrics:
  - section_recall, keyword_recall, direct_ref_resolution_rate per question.
  - Per-question pass/fail on compound coverage.
- Save baseline results to `tests/eval/baseline_results.json`.

Acceptance:

- Baseline eval runs and produces reproducible metrics.
- Compound question failure cases are documented with expected evidence.

### Phase 1: Source Inventory Tool

File areas:

- `server/agents/tools/`
- `server/api/v1/query.py`
- `server/services/kb_database.py`
- `tests/server/agents/`

Tasks:

- Add `list_sources` as a formal tool.
- Return selected KB source metadata: indexed source, doc_id, source_title where available, and lightweight type/version hints.
- Reuse existing KB source resolution and source alias normalization.
- Include `list_sources` output in tool trace and future exports.
- Design the output so it can later support document tagging and KB metadata governance.

Acceptance:

- Unit tests cover source listing for KB-scoped requests.
- Tool respects selected KB scope.
- Tool output is serializable and useful for planner input.
- No topic-specific source mapping is introduced.

Implementation status: completed in this iteration for retriever-backed source inventory and the `list_sources` agent tool. KB tag governance remains future metadata work.

### Phase 2: Evidence Planner

File areas:

- `server/agents/agentic_retrieve.py` (new)
- `server/models/schemas.py`
- `server/core/query_understanding.py` (input only; do not overload its prompt)
- `server/config.py` (planner model settings)
- `tests/server/agents/test_agentic_retrieve.py`

Tasks:

- Add `EvidenceSlot` and `EvidencePlan` schemas.
- Implement `plan_evidence(question, analysis, source_inventory)`.
- Keep prompt responsibilities separated:
  - `analyze_query()` handles basic query understanding.
  - `plan_evidence()` handles slot decomposition and source-aware search planning.
- Planner may choose source hints, slot queries, object labels, retry queries, and whether a slot needs object lookup or chunk context.
- Planner uses configurable model settings:
  - `AGENTIC_SEARCH_PLANNER_MODEL`
  - `AGENTIC_SEARCH_PLANNER_BASE_URL`
  - `AGENTIC_SEARCH_PLANNER_API_KEY`
  - fallback to the agent/main LLM config when unset.
- Validate planner JSON/schema.
- Fallback to existing single `retrieve` if planning fails, returns no slots, or exceeds hard budget.

Acceptance:

- Compound questions produce 2-4 bounded slots.
- Simple questions can choose single-slot fallback.
- Source hints come from `list_sources` inventory, not hard-coded mappings.
- Planner failure causes zero behavior change.

Implementation status: completed in this iteration. `EvidenceSlot`, `EvidencePlan`, configurable planner model fallback, LLM JSON validation, and heuristic fallback are implemented in `server/core/evidence_planner.py`.

### Phase 3: Helper Tools and Constrained Orchestrator

File areas:

- `server/agents/agentic_retrieve.py` (new)
- `server/agents/tools/retrieve.py` (integrate orchestrator)
- `server/agents/tools/` (lookup/open helpers)
- `server/agents/evidence.py` (extend EvidenceBundle)
- `server/core/retrieval.py` (reuse object lookup and chunk fetch helpers)
- `server/config.py` (feature flag)
- `tests/server/agents/test_agentic_retrieve.py` (new)

Tasks:

- Implement `agentic_retrieve(question, config)`:
  1. Call `analyze_query()` for basic understanding.
  2. Call `list_sources()` to inspect selected KB scope.
  3. Call `plan_evidence(question, analysis, source_inventory)`.
  4. If planning fails or returns fallback, use existing single-retrieve path.
  5. Round 1: `asyncio.gather()` — call `HybridRetriever.retrieve()` per slot in parallel.
  6. For slots that request `object_labels`, supplement with `lookup_object`.
  7. For slots that request context, use `open_chunk` on accepted candidates.
  8. Apply rules-based slot verification (object match, rerank score, required override).
  9. Round 2: serial retry for `missing` required slots only, with planner-provided `retry_queries`.
  10. Assemble `VerifiedEvidenceBundle` with per-slot results.
- Add `lookup_object` helper/tool: ES term query on `object_label` / `object_aliases` / `object_id`.
- Add `open_chunk` helper/tool: chunk content + metadata + neighbors/parent.
- Add feature flag `AGENTIC_SEARCH_ENABLED=true` to `ServerConfig`.
- When disabled, `retrieve_agentic` uses single-slot fallback without planner LLM.
- Limit: max 4 slots, max 1 retry per slot.

Acceptance:

- Compound questions produce parallel slot searches from a validated plan.
- Missing slots trigger retry with alternative queries.
- Object slots verified by label match, not just rerank score.
- Feature flag off → no planner LLM and no slot split; use single-slot retrieval fallback.
- Search trace is complete and serializable.

Implementation status: partially completed in this iteration.

- Implemented `retrieve_agentic`, `list_sources`, `lookup_object`, and `open_chunk`.
- Implemented constrained slot orchestration over the existing `HybridRetriever.retrieve(...)` pipeline.
- Implemented rule-based slot status and planner-provided retry query support.
- Slot searches currently run serially to keep progress reporting simple; parallel fan-out remains an optimization.
- Slot results are recorded in `tool_trace`; `EvidenceBundle.slot_results` is deferred to Phase 4.

### Phase 4: Answer Generation and Groundedness Update

File areas:

- `server/core/generation/llm.py`
- `server/agents/evidence.py`
- `server/agents/qa_agent.py`

Tasks:

- Extend `EvidenceBundle` with `slot_results` and `unresolved_slots`.
- Update answer generation to consume per-slot evidence:
  - Cover every required slot.
  - Cite accepted evidence per slot.
  - Explicitly state missing slots.
- Update groundedness logic: "grounded" = all required slots satisfied, not just top rerank score.
- Update agent instructions: stop condition changes from "groundedness=grounded" to "all required slots satisfied."

Acceptance:

- Answer covers satisfied slots.
- Missing slots are explicit in the answer.
- Source ordering and citations remain stable.
- Groundedness reflects slot-level completeness.

### Phase 5: Evaluation Comparison

Tasks:

- Run the same eval harness from Phase 0 with `AGENTIC_SEARCH_ENABLED=true`.
- Compare against baseline:
  - section_recall improvement on compound questions.
  - direct_ref_resolution_rate improvement.
  - Latency comparison (single retrieve vs parallel slot retrieve).
  - No regression on simple questions.
- Document results in `tests/eval/agentic_results.json`.

Acceptance:

- Compound question recall improves measurably.
- Simple question quality does not regress.
- Latency is within 2x of single retrieve for typical questions.

### Phase 6: Future Enhancements (not in first version)

Only pursue these if Phase 5 shows the approach works but rule-based verification is insufficient:

- **LLM verifier**: for slots where object match and rerank score cannot determine satisfaction (e.g., "explain the design philosophy of EN 1990" — no object label, conceptual match).
- **Separate `search_keyword` / `search_semantic` tools**: if specific use cases require bypassing the HybridRetriever pipeline (e.g., pure metadata lookup, or pure vector search for cross-lingual matching). This would require reimplementing fusion and rerank.
- **Free-form agent loop**: let the agent decide arbitrary tool sequences per slot, with budget limits. Only if the constrained pipeline proves too rigid for real-world question diversity.
- **Frontend trace UI**: visual display of evidence plan and search trace. The first version uses Markdown export only.

## Feature Flags

```text
AGENTIC_SEARCH_ENABLED=true
AGENTIC_SEARCH_MAX_SLOTS=4
AGENTIC_SEARCH_PLANNER_MODEL=
AGENTIC_SEARCH_PLANNER_BASE_URL=
AGENTIC_SEARCH_PLANNER_API_KEY=
AGENTIC_SEARCH_VERIFIER_MODEL=
AGENTIC_SEARCH_VERIFIER_BASE_URL=
AGENTIC_SEARCH_VERIFIER_API_KEY=
```

Default enabled. Set `AGENTIC_SEARCH_ENABLED=false` to force single-slot fallback without planner LLM.

Planner model settings are used by `plan_evidence()`. If unset, the planner falls back to the existing agent/main LLM configuration. Verifier model settings are reserved for the future LLM verifier phase and should not be required in the first version.

## Risks and Controls

- **Cost increase**: slot searches may run more than one retrieve call. Limit slot count to 4; parallel fan-out is deferred until progress reporting is slot-safe.
- **Planner instability**: if `plan_evidence()` fails, returns no valid slots, or exceeds budget, fall back to the existing single-retrieve path. Zero risk.
- **Verification false negatives**: conservative labeling (partial/missing over satisfied) means unnecessary retries, not missed evidence. Acceptable tradeoff.
- **Verification false positives**: object match is deterministic; rerank threshold is tunable. Monitor in eval.
- **Breaking existing retrieval**: feature flag with clean fallback. Non-agentic path is never modified.
- **Latency**: parallel first round ≈ 1x retrieve. Serial retries add at most 1-2x. Total budget: ≤ 3x single retrieve.

## Review Questions

- Is the rerank score threshold (0.85 satisfied, 0.5 partial) well-calibrated for this corpus? Should we tune it per question type?
- Which model should `plan_evidence()` use by default: the agent model, the main answer model, or a separately configured lightweight planner model?
- When should we move from rule-based verification to LLM verification? What failure patterns would trigger this?
- Is the max 4 slot limit sufficient for the most complex Eurocode questions?

## Expected Benefits

- Compound questions no longer depend on one top-k retrieval pass.
- Missing material/action/table evidence becomes an explicit unresolved slot.
- The system avoids per-question retrieval patches.
- Failures become diagnosable from exported traces.
- Simple questions are unaffected (feature flag + single-slot fallback).
- The project can evolve toward real agentic search while preserving the existing RAG pipeline.
