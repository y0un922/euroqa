# Answer Depth Reconstruction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild Eurocode QA answer prompts so responses become more detailed, engineer-friendly, and project-usable for Chinese engineers unfamiliar with Eurocode, while preserving strict evidence constraints and preventing over-answering.

**Architecture:** Keep the existing `open`, `exact`, and `exact_not_grounded` generation split. Rework only the generation-layer prompt builders so each mode has a new explanation structure and explicit safety boundaries. Lock the behavior with generation-layer tests that assert both richer instructional guidance and continued anti-hallucination guardrails.

**Tech Stack:** Python 3.12, pytest, FastAPI backend generation layer

---

## File Structure

**Generation**

- Modify: `server/core/generation.py`
  Rebuild the three mode-specific system prompts while keeping routing and evidence-pack assembly unchanged.

**Tests**

- Modify: `tests/server/test_generation.py`
  Add failing tests first for the new prompt structures, instructional constraints, and anti-overreach guardrails.

**Documentation**

- Modify: `docs/superpowers/specs/2026-04-10-answer-depth-reconstruction-design.md`
  Sync any implementation-driven clarification if the final prompt structure differs from the draft spec.

---

### Task 1: Write failing tests for the new answer-depth contract

**Files:**
- Modify: `tests/server/test_generation.py`

- [ ] **Step 1: Add failing tests for the `open` prompt structure**

Add assertions that `build_open_system_prompt(None, None)` includes the new instructional sections and constraints:

- `### 先说结论`
- `### 这条规则在说什么`
- `### 适用条件与边界`
- `### 工程上怎么用`
- `### 容易出错的点`
- `### 当前依据`
- `### 还需要补充确认的内容`

Also assert the prompt explicitly mentions:

- `中国工程师`
- `不熟悉 Eurocode`
- `工程上怎么用`
- `适用边界`
- `容易出错的点`

- [ ] **Step 2: Add failing tests for the `exact` prompt structure**

Add assertions that `build_exact_system_prompt()`:

- includes `### 直接答案`
- includes `### 关键依据`
- includes `### 这条规定应如何理解和使用`
- includes `### 使用时要再核对的条件`
- does **not** include the old 8-section path
- still emphasizes direct answers before longer explanation

- [ ] **Step 3: Add failing tests for the `exact_not_grounded` prompt structure**

Add assertions that `build_exact_not_grounded_system_prompt()`:

- includes `### 当前能确认的内容`
- includes `### 为什么还不能直接下结论`
- includes `### 对工程决策的影响`
- includes `### 下一步应优先补查什么`
- still forbids packaging related material as direct evidence

- [ ] **Step 4: Add failing tests for prompt-selection continuity**

Keep or extend existing tests so `generate_answer()` and `generate_answer_stream()` still choose prompts by `answer_mode + groundedness`, proving the deeper explanation rewrite does not break mode routing.

- [ ] **Step 5: Run generation tests and verify failure**

Run: `uv run pytest tests/server/test_generation.py -q`
Expected: FAIL because the current prompts still use the old section structure and do not include the new teaching-oriented constraints.

---

### Task 2: Implement the minimal prompt changes to satisfy the new contract

**Files:**
- Modify: `server/core/generation.py`

- [ ] **Step 1: Rebuild the `open` prompt**

Update `build_stream_system_prompt()` and/or `build_open_system_prompt()` so open answers:

- target Chinese engineers unfamiliar with Eurocode
- explain rule meaning before engineering application
- explicitly cover boundaries, engineering actions, and common mistakes
- remain evidence-constrained

Do not change `decide_generation_mode()` or retrieval context assembly.

- [ ] **Step 2: Rebuild the `exact` prompt**

Update `build_exact_system_prompt()` so exact answers:

- remain short-to-medium length
- lead with a direct answer
- add only necessary explanation for interpretation and use
- avoid regressing into a long-form lecture

- [ ] **Step 3: Rebuild the `exact_not_grounded` prompt**

Update `build_exact_not_grounded_system_prompt()` so insufficient-evidence answers:

- explain what is confirmed
- explain why a direct conclusion is still unsafe
- explain impact on engineering decisions
- prioritize next retrieval steps

- [ ] **Step 4: Keep JSON and stream prompt selection aligned**

Verify `_build_json_system_prompt()` and `_build_stream_mode_system_prompt()` still route each mode to the correct rebuilt prompt without changing response contracts.

- [ ] **Step 5: Run generation tests and verify pass**

Run: `uv run pytest tests/server/test_generation.py -q`
Expected: PASS

---

### Task 3: Clean up wording drift and sync documentation

**Files:**
- Modify: `server/core/generation.py`
- Modify: `docs/superpowers/specs/2026-04-10-answer-depth-reconstruction-design.md`

- [ ] **Step 1: Refactor prompt wording if needed**

After tests are green, do a minimal cleanup pass:

- remove duplicated prompt instructions
- keep wording consistent across the three modes
- ensure no instruction accidentally encourages unsupported conclusions

- [ ] **Step 2: Sync the design doc if implementation wording changed**

If the final prompt section names or boundaries changed during implementation, update the design doc so it matches the shipped behavior.

- [ ] **Step 3: Re-run generation tests**

Run: `uv run pytest tests/server/test_generation.py -q`
Expected: PASS

- [ ] **Step 4: Optional targeted smoke check**

If feasible, run one targeted API-level generation smoke test that exercises prompt selection without requiring full external dependencies. If not feasible in the local environment, document the gap.

---

### Task 4: Final verification and commit preparation

**Files:**
- Modify: `server/core/generation.py`
- Modify: `tests/server/test_generation.py`
- Modify: `docs/superpowers/specs/2026-04-10-answer-depth-reconstruction-design.md` (if needed)

- [ ] **Step 1: Run the final verification command**

Run: `uv run pytest tests/server/test_generation.py -q`
Expected: PASS

- [ ] **Step 2: Review diff for scope control**

Confirm the change set is limited to prompt builders, prompt tests, and any minimal spec sync. No retrieval or frontend behavior should be changed in this task.

- [ ] **Step 3: Prepare commit**

```bash
git add server/core/generation.py tests/server/test_generation.py docs/superpowers/specs/2026-04-10-answer-depth-reconstruction-design.md
git commit -m "feat(generation): deepen eurocode answers for engineer-facing guidance"
```
