# Exact QA Routing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade the Eurocode QA backend from relevance-first answering to evidence-constrained exact-vs-open routing, so definition/assumption/applicability/formula/limit/clause-lookup questions can either answer from direct normative evidence or safely downgrade instead of over-answering.

**Architecture:** `server/core/query_understanding.py` becomes the routing entry that emits `answer_mode`, `intent_label`, `target_hint`, and confidence. `server/core/retrieval.py` adds an exact-only probe path plus groundedness evaluation based on title/clause/phrase anchors. `server/core/generation.py` stops forcing one long template for every question and instead renders `exact`, `open`, or `exact_not_grounded` prompts according to retrieval evidence. The regression safety net expands from recall-only checks to routing, anchor hit, and over-answer behavior.

**Tech Stack:** Python 3.12, FastAPI, Pydantic, pytest, JSON eval fixtures

---

## File Structure

**Routing and schemas**

- Modify: `server/models/schemas.py`
  Add routing/result models that can be shared across query understanding, retrieval, and generation.
- Modify: `server/core/query_understanding.py`
  Extend LLM output parsing and `QueryAnalysis` with exact/open routing metadata.

**Retrieval**

- Modify: `server/core/retrieval.py`
  Add exact probe, anchor extraction, groundedness scoring, and mode-aware retrieval output.

**Generation**

- Modify: `server/core/generation.py`
  Split prompt selection into `exact`, `open`, and `exact_not_grounded`, with short-answer constraints for exact routes.
- Modify: `server/api/v1/query.py`
  Thread new routing/groundedness metadata through `/query` and `/query/stream`.

**Tests and evaluation**

- Modify: `tests/server/test_query_understanding.py`
  Add routing schema and fallback tests.
- Modify: `tests/server/test_retrieval.py`
  Add exact probe and groundedness behavior tests.
- Modify: `tests/server/test_generation.py`
  Add template-selection and over-answer suppression tests.
- Modify: `tests/server/test_api.py`
  Verify end-to-end metadata propagation and request plumbing.
- Modify: `tests/eval/test_questions.json`
  Expand with exact-question fixtures and expected routing metadata.
- Modify: `tests/eval/eval_retrieval.py`
  Add `anchor_hit_rate`, `grounded_mode_accuracy`, and `over_answer_rate`.

**Documentation**

- Modify: `docs/superpowers/specs/2026-04-10-exact-qa-routing-design.md`
  Sync any plan-driven clarifications discovered during implementation.

---

### Task 1: Add routing metadata and failing tests first

**Files:**
- Modify: `server/models/schemas.py`
- Modify: `server/core/query_understanding.py`
- Modify: `tests/server/test_query_understanding.py`

- [ ] **Step 1: Write failing tests for routing metadata parsing**

Add tests that expect `expand_queries()` / `analyze_query()` to preserve:

```python
{
    "answer_mode": "exact",
    "intent_label": "assumption",
    "target_hint": {"document": "EN 1992-1-1", "clause": "6.1", "object": "basic assumptions"},
    "confidence": 0.92,
    "reason_short": "asks for direct normative assumptions"
}
```

Also add one low-confidence / malformed-response case that must fall back safely.

- [ ] **Step 2: Run the query-understanding tests and verify failure**

Run: `uv run pytest tests/server/test_query_understanding.py -q`
Expected: FAIL because the current parser and `QueryAnalysis` do not expose the new routing fields.

- [ ] **Step 3: Extend shared schemas for routing output**

In `server/models/schemas.py`, add focused types for:

- `AnswerMode`: `exact`, `open`, `exact_not_grounded` if needed at response stage
- `RoutingTargetHint`
- `RoutingDecision`

Keep them small and reusable. Do not over-generalize into a generic “classifier framework”.

- [ ] **Step 4: Extend `QueryAnalysis` and expansion parsing**

Update `server/core/query_understanding.py` so:

- `QueryAnalysis` carries `answer_mode`, `intent_label`, `intent_confidence`, `target_hint`, `reason_short`
- `_parse_expansion_result()` reads the new JSON shape
- invalid or missing routing fields degrade to `None`, not exceptions

- [ ] **Step 5: Add LLM prompt instructions for routing**

Update the LLM prompt in `expand_queries()` so it returns the new routing fields alongside the existing query-expansion outputs. Keep backward compatibility: if the model returns only the old fields, retrieval should still work.

- [ ] **Step 6: Re-run tests and verify pass**

Run: `uv run pytest tests/server/test_query_understanding.py -q`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add server/models/schemas.py server/core/query_understanding.py tests/server/test_query_understanding.py
git commit -m "feat(routing): add exact-open routing metadata to query understanding"
```

---

### Task 2: Build the exact-question evaluation dataset before changing retrieval logic

**Files:**
- Modify: `tests/eval/test_questions.json`
- Modify: `tests/eval/eval_retrieval.py`

- [ ] **Step 1: Add failing exact-question fixtures**

Append at least 8 exact-oriented questions to `tests/eval/test_questions.json`, covering:

- definition
- assumption
- applicability
- formula
- limit
- clause lookup

Each fixture should include:

```json
{
  "expected_mode": "exact",
  "expected_document": "EN 1992-1-1:2004",
  "expected_sections": ["6.1"],
  "expected_anchor_phrases": ["plane sections remain plane"],
  "must_not_include": ["5.8.9", "双向弯曲简化公式"]
}
```

- [ ] **Step 2: Extend the eval script data loader**

Update `tests/eval/eval_retrieval.py` to read the new fixture keys while remaining compatible with older entries that only provide `expected_sections` and `expected_keywords`.

- [ ] **Step 3: Add new metrics with placeholder logic**

Add scaffolding for:

- `anchor_hit_rate`
- `grounded_mode_accuracy`
- `over_answer_rate`

At this stage the values may be partial or always zero; the point is to make the eval surface fail visibly when data is missing.

- [ ] **Step 4: Run the eval script in dry mode or unit-test the helpers**

If local services are unavailable, at minimum add helper-level tests or run a short smoke command:

Run: `uv run python tests/eval/eval_retrieval.py --top-k 3`
Expected: Either metrics print successfully, or service-unavailable behavior is explicit and non-crashing.

- [ ] **Step 5: Commit**

```bash
git add tests/eval/test_questions.json tests/eval/eval_retrieval.py
git commit -m "test(eval): add exact-question fixtures and routing metrics scaffold"
```

---

### Task 3: Implement exact probe and groundedness checks in retrieval

**Files:**
- Modify: `server/core/retrieval.py`
- Modify: `tests/server/test_retrieval.py`

- [ ] **Step 1: Write failing tests for exact probe behavior**

Add tests that assert:

- exact questions prefer title/clause/phrase hits over generic semantic hits
- groundedness becomes `grounded` when a chunk contains a direct anchor phrase
- groundedness becomes `exact_not_grounded` or equivalent when only related sections are found

Use fake chunks like:

```python
_make_chunk("exact", "When determining the ultimate moment resistance ... the following assumptions are made: plane sections remain plane.")
_make_chunk("related", "Biaxial bending may be verified by ...")
```

- [ ] **Step 2: Run retrieval tests and verify failure**

Run: `uv run pytest tests/server/test_retrieval.py -q`
Expected: FAIL because current retrieval has no exact probe or groundedness logic.

- [ ] **Step 3: Introduce exact-probe helper methods**

In `server/core/retrieval.py`, add focused helpers for:

- identifying exact-intent queries
- phrase/title/clause boosting candidates
- extracting anchor matches by `intent_label`
- computing groundedness status

Keep helpers local to `HybridRetriever`. Do not create a new service layer yet.

- [ ] **Step 4: Update retrieval flow**

Modify `retrieve()` so that when `answer_mode == "exact"`:

- it runs an exact probe path first
- it evaluates groundedness before final chunk selection
- it returns groundedness metadata alongside chunks/scores/ref_chunks

Preserve existing non-exact retrieval behavior as much as possible.

- [ ] **Step 5: Re-run retrieval tests**

Run: `uv run pytest tests/server/test_retrieval.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add server/core/retrieval.py tests/server/test_retrieval.py
git commit -m "feat(retrieval): add exact probe and groundedness evaluation"
```

---

### Task 4: Thread routing and groundedness through the API contract

**Files:**
- Modify: `server/api/v1/query.py`
- Modify: `server/models/schemas.py`
- Modify: `tests/server/test_api.py`

- [ ] **Step 1: Write failing API tests for metadata propagation**

Add tests that assert `/api/v1/query` and `/api/v1/query/stream` propagate:

- routing decision or answer mode
- groundedness status
- any retrieval metadata needed by generation

Mock `analyze_query()` and `retriever.retrieve()` to return explicit exact-route values.

- [ ] **Step 2: Run API tests and verify failure**

Run: `uv run pytest tests/server/test_api.py -q`
Expected: FAIL because the current endpoint plumbing does not pass or return the new metadata.

- [ ] **Step 3: Extend result models only as needed**

Add small response-side fields to the relevant schema models. Keep API surface conservative: only expose fields needed by generation or future debugging, not every internal score.

- [ ] **Step 4: Update `/query` and `/query/stream` plumbing**

Ensure:

- `analysis.answer_mode` and `analysis.intent_label` reach retrieval/generation
- retrieval groundedness reaches generation
- streaming and non-streaming paths stay aligned

- [ ] **Step 5: Re-run API tests**

Run: `uv run pytest tests/server/test_api.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add server/api/v1/query.py server/models/schemas.py tests/server/test_api.py
git commit -m "feat(api): thread routing and groundedness metadata through query endpoints"
```

---

### Task 5: Split generation into `exact`, `open`, and `exact_not_grounded`

**Files:**
- Modify: `server/core/generation.py`
- Modify: `tests/server/test_generation.py`

- [ ] **Step 1: Write failing prompt-selection tests**

Add tests that assert:

- exact questions no longer force the 8-section template
- exact_not_grounded suppresses long-form expansion
- open questions retain the richer explanation path

At minimum assert on prompt content, section headers, and guardrail sentences.

- [ ] **Step 2: Run generation tests and verify failure**

Run: `uv run pytest tests/server/test_generation.py -q`
Expected: FAIL because the current generation layer still assumes one primary structured template.

- [ ] **Step 3: Add mode-aware system prompt builders**

In `server/core/generation.py`, introduce focused prompt builders such as:

- `build_exact_system_prompt(...)`
- `build_open_system_prompt(...)`
- `build_exact_not_grounded_system_prompt(...)`

Do not try to parameterize one giant prompt builder with dozens of flags.

- [ ] **Step 4: Route generation by groundedness**

Update both `generate_answer()` and `generate_answer_stream()` so final template selection uses:

- `exact` when evidence is grounded
- `exact_not_grounded` when exact intent lacks direct anchors
- `open` otherwise

Evidence state must override the original LLM route when they conflict.

- [ ] **Step 5: Add hard shortening rules for exact routes**

Exact routes should:

- lead with direct conclusion
- prioritize direct references
- avoid long engineering action prose

Exact-not-grounded routes should:

- state what is confirmed
- state what is not directly located
- avoid pretending related material is direct evidence

- [ ] **Step 6: Re-run generation tests**

Run: `uv run pytest tests/server/test_generation.py -q`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add server/core/generation.py tests/server/test_generation.py
git commit -m "feat(generation): add exact and exact-not-grounded answer modes"
```

---

### Task 6: Close the loop with eval metrics and targeted regression checks

**Files:**
- Modify: `tests/eval/eval_retrieval.py`
- Modify: `tests/eval/test_questions.json`
- Modify: `docs/superpowers/specs/2026-04-10-exact-qa-routing-design.md`

- [ ] **Step 1: Finish metric implementations**

Use retrieval results and generated outputs to calculate:

- section hit
- anchor hit
- grounded mode accuracy
- over-answer rate

If `over-answer_rate` cannot be measured in the current script without generation, add a clearly named placeholder stage and document the limitation rather than silently faking the metric.

- [ ] **Step 2: Add the known regression examples explicitly**

Ensure the dataset includes the motivating failure cases, especially:

- 截面计算基本假设
- 适用条件/适用区域
- 公式定位
- 限值定位

- [ ] **Step 3: Run the targeted regression test suite**

Run:

```bash
uv run pytest tests/server/test_query_understanding.py tests/server/test_retrieval.py tests/server/test_generation.py tests/server/test_api.py -q
```

Expected: PASS

- [ ] **Step 4: Run retrieval evaluation**

Run:

```bash
uv run python tests/eval/eval_retrieval.py --top-k 5
```

Expected: Script completes and reports the new metrics; exact-question entries should show direct anchors or conservative downgrade behavior.

- [ ] **Step 5: Sync design doc if implementation refined thresholds or states**

Update `docs/superpowers/specs/2026-04-10-exact-qa-routing-design.md` only if implementation forced a real design change, not for incidental wording cleanup.

- [ ] **Step 6: Commit**

```bash
git add tests/eval/eval_retrieval.py tests/eval/test_questions.json docs/superpowers/specs/2026-04-10-exact-qa-routing-design.md
git commit -m "test(eval): validate exact-qa routing and grounded answering behavior"
```

---

## Notes for Implementation

- Preserve backward compatibility where practical. Existing open-ended questions should keep working even if they do not benefit from exact routing.
- Keep routing and groundedness logic explicit and inspectable. Debugging this feature will depend on understanding why a question was routed one way or another.
- Prefer adding small helper functions close to the current modules instead of introducing new abstraction layers prematurely.
- The exact route must fail safe. If classification is uncertain or evidence is weak, downgrade rather than over-answer.

---

## Definition of Done

- `QueryAnalysis` carries exact/open routing metadata from the LLM classifier.
- Retrieval can distinguish “directly grounded exact evidence” from “only related material”.
- Generation no longer forces one long answer shape onto exact questions.
- The motivating failure mode stops appearing: related clauses must no longer masquerade as direct normative answers.
- Tests and eval fixtures cover the exact-question category as a first-class regression surface.
