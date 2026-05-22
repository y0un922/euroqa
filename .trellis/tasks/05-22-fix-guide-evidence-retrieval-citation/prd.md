# Fix Guide Evidence Retrieval Citation

## Problem

Reranked retrieval candidates from `DG_*` / Designers Guide documents are classified as guide chunks and removed from the main evidence list. In a guide-heavy or guide-only index this makes retrieval return zero final chunks even though vector/BM25 search and rerank succeeded. The prompt also exposes `[Guide-N]` / `[GuideExample-N]` labels that are not part of the frontend citation contract, so guide evidence can influence an answer without a clickable source.

## Requirements

- Preserve reranked guide/designers-guide chunks as citable main evidence instead of removing them from `RetrievalResult.chunks`.
- Keep frontend citation protocol unified around `[Ref-N]`; guide/example evidence that is shown to the LLM as citable evidence must be represented in backend `sources`.
- Do not rely on `question_type` to decide whether guide evidence is allowed into the answer context.
- Keep retrieval context guide fields available for observability/backward compatibility, but they must not be the only path for guide evidence to reach citations.
- Add regression tests for DG-only retrieval and generation citation/source alignment.

## Non-Goals

- Do not implement full question_type removal.
- Do not add T3/T4/T5 auto-merging, exact-ref pinning, or cross-ref redesign.
- Do not redesign frontend UI badges in this task.

## Validation

- Focused backend tests covering retrieval and generation pass.
- A direct retriever smoke check for a DG query returns non-empty chunks.
