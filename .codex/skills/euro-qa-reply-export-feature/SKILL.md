---
name: euro-qa-reply-export-feature
description: "Continue the Euro_QA feature that adds assistant-reply copy and whole-session Markdown export with retrieval-context fidelity. Use when working in this repository on this specific feature: extending backend `/query` and `/query/stream` response contracts, persisting retrieval context in frontend `ChatTurn` state and localStorage, building Markdown export helpers, wiring copy/export UI, updating `docs/progress/*.md`, or validating stream/fallback/session-recovery behavior."
---

# Euro_QA Reply Export Feature

## Overview

Use this skill only for the Euro_QA feature tracked in:

- `docs/progress/MASTER.md`
- `docs/plan/task-breakdown.md`

Treat `MASTER.md` as the source of truth for cross-conversation continuity. Implement the feature phase by phase, update progress immediately after each completed task, and keep stream/non-stream behavior consistent.

## Start Every Session

1. Read `docs/progress/MASTER.md`.
2. Read the current phase file linked from `MASTER.md`.
3. Read supporting plan files only as needed:
   - `docs/plan/task-breakdown.md`
   - `docs/plan/dependency-graph.md`
   - `docs/plan/milestones.md`
4. Resume from the active unchecked task in the current phase file.
5. Before coding, confirm which files are in scope for that task and avoid touching unrelated dirty files.

## Execution Rules

- Implement against the defined feature boundary only:
  - single assistant-reply copy
  - whole-session Markdown export
  - answer markdown + cited sources + full retrieval context snapshot
- Prefer contract-first changes. Freeze backend response shape before extending frontend persistence or UI.
- Keep `/query` and `/query/stream` completion metadata aligned. Do not let fallback non-stream behavior diverge from streaming done payloads.
- Base whole-session export on frontend persisted session data, not on `server/core/conversation.py`.
- Treat retrieval context as an export-ready snapshot, not as a dump of the internal `Chunk` model.
- Keep new persisted fields optional and migration-safe.
- Favor pure formatting helpers for Markdown export. Do not build export strings inline inside React components.

## Phase Guidance

### Phase 1: Backend Contract

- Work in:
  - `server/models/schemas.py`
  - `server/core/generation.py`
  - `server/api/v1/query.py`
- Define retrieval context DTOs that separate:
  - main retrieved chunks
  - parent/extended context
  - rerank score when applicable
- Reuse one snapshot builder for stream and non-stream paths.

### Phase 2: Frontend State

- Work in:
  - `frontend/src/lib/types.ts`
  - `frontend/src/lib/api.ts`
  - `frontend/src/hooks/useEuroQaDemo.ts`
  - `frontend/src/lib/session.ts`
- Extend `ChatTurn` with optional retrieval context.
- Persist and restore the new fields through localStorage migration logic.
- Ensure both streaming completion and non-stream fallback populate the same message shape.

### Phase 3: Markdown Export

- Add a dedicated export module under `frontend/src/lib/`.
- Freeze the Markdown template before wiring UI.
- Keep single-message and whole-session builders as pure functions.
- Decide empty-state formatting once and reuse it everywhere.

### Phase 4: UI Integration

- Work in:
  - `frontend/src/components/MainWorkspace.tsx`
  - `frontend/src/components/TopBar.tsx`
  - shared action exposure in `frontend/src/hooks/useEuroQaDemo.ts`
- Keep single-message copy on the reply card.
- Keep whole-session export at the session/global level.
- Disable copy/export for incomplete streaming content.

### Phase 5: Validation

- Update:
  - `tests/server/test_api.py`
  - `tests/server/test_generation.py`
  - `frontend/src/lib/api.test.ts`
  - `frontend/src/lib/session.test.ts`
  - export-module tests
- Verify these user-critical paths:
  - normal streaming completion
  - stream failure with non-stream fallback
  - page refresh and session restore
  - single-reply copy output
  - whole-session export output

## Parallel Execution Protocol

- Only parallelize tasks already marked as parallel lanes in `docs/plan/task-breakdown.md`.
- Keep a single owner for hotspot files:
  - `frontend/src/hooks/useEuroQaDemo.ts`
  - `server/core/generation.py`
- Recommended parallel windows:
  - Phase 3: single-message builder and whole-session builder after shared helpers are done
  - Phase 4: reply-card UI and top-bar export UI after actions are exposed
  - Phase 5: backend tests and frontend tests
- If two parallel tasks need the same file, re-serialize them unless the write scopes are clearly disjoint.

## Progress Updates

After completing any task:

1. Check the task in the current phase file.
2. Update the task count in `docs/progress/MASTER.md`.
3. Update `Current Status` in `docs/progress/MASTER.md`.
4. Add a short note to the phase file if you made a design decision, hit a blocker, or changed scope.

Do not defer progress-file updates to the end of the session.

## Finish Condition

When all phase files are fully checked:

1. Mark all phases complete in `docs/progress/MASTER.md`.
2. Prepare a concise completion summary.
3. Trigger the cleanup step from the spec-driven workflow:
   ask the user which generated artifacts to keep and which to remove.
