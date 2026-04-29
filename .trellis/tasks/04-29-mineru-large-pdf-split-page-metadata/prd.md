# brainstorm: MinerU large PDF split with exact page metadata

## Goal

Support PDFs that exceed MinerU official's 200-page upload limit by automatically splitting, parsing, offsetting, and merging parser outputs while preserving original-document page metadata for LLM citation/source tracing.

## What I already know

* The current MinerU official parse path fails when the remote API returns `number of pages exceeds limit (200 pages), please split the file and try again`.
* The failing document example is `DG_EN1992-1-1__-1-2.pdf`.
* The current official parse path writes a single `{doc_id}.md`, `{doc_id}_content_list.json`, and `{doc_id}_meta.json` from the official `full_zip_url`.
* Downstream page metadata is derived from MinerU `content_list[*].page_idx`.
* `pipeline.content_list.resolve_section_page_metadata()` converts `page_idx` to:
  * `page_file_index`: original 0-based page indexes
  * `page_numbers`: original 1-based page numbers
  * `bbox_page_idx`: page index for bbox highlighting
* Naively parsing split PDFs as independent documents would reset each part to `page_idx=0`, causing incorrect final citations.

## Assumptions (temporary)

* The desired user-facing behavior is one logical document per original PDF, not multiple searchable part documents.
* Split parts should be an internal implementation detail and should not leak into final source names or document IDs.
* Exact original PDF page numbering is more important than parsing throughput.
* PDFs can be split locally before upload.

## Open Questions

* Resolved: use strict fail-closed behavior. If merged page metadata cannot be proven correct, the original document parse must fail and must not enter the index.

## Requirements (evolving)

* Automatically detect MinerU official 200-page failures or pre-detect PDFs with more than 200 pages.
* Split large PDFs into parts under the official page limit.
* Parse each part through MinerU official.
* Merge Markdown outputs into one original-document Markdown file.
* Merge `content_list` outputs into one original-document content list.
* Apply exact `page_idx` offsets to every page-bearing content list entry before downstream structuring.
* Preserve original-document `doc_id`, source title, and output paths.
* Preserve the upload `doc_id` exactly through indexing, answer sources, and PDF viewer URLs. Uploaded files with repeated underscores such as `DG_EN1992-1-1__-1-2.pdf` must not be normalized into `DG_EN1992-1-1_-1-2`.
* Record split metadata in `{doc_id}_meta.json`, including part ranges, offsets, parser batch IDs, and validation results.
* Prevent silent ingestion when page metadata is missing, inconsistent, or unverifiable.
* Fail closed for page metadata integrity: do not emit a final Markdown/content-list pair when page offsets cannot be validated.

## Acceptance Criteria (evolving)

* [x] A PDF with more than 200 pages parses successfully through the official provider by internal splitting.
* [x] Final `content_list[*].page_idx` values refer to the original PDF page indexes, not part-local indexes.
* [x] `page_numbers`, `page_file_index`, and `bbox_page_idx` generated downstream match the original PDF page numbers.
* [x] Split part names and part-local document IDs do not appear as separate final documents.
* [x] Metadata records every part's original page range and offset.
* [ ] After upload and processing, `sources[].document_id` can load `GET /api/v1/documents/{document_id}/file` for the original PDF, including doc IDs with repeated underscores.
* [x] Tests prove that a section on part 2 local page 1 becomes original page `offset + 1`.
* [x] Tests prove bbox page index is offset together with section page metadata.
* [x] Tests prove invalid or missing page metadata fails loudly instead of producing wrong citations.
* [x] Failure cases do not leave a successful original-document parse artifact that downstream indexing could ingest accidentally.

## Definition of Done (team quality bar)

* Tests added/updated for split/merge and page offset behavior.
* Lint / typecheck / CI green where available.
* Docs/notes updated if behavior changes.
* Rollout/rollback considered if risky.

## Out of Scope (explicit)

* Changing the downstream citation model unless required to preserve correctness.
* Treating PDF parts as separate user-visible documents.
* Relaxing citation requirements when page metadata is incomplete.

## Technical Notes

* Relevant code:
  * `pipeline/parse.py`: MinerU local/official parse implementations and parse output writing.
  * `pipeline/content_list.py`: content list normalization and page metadata resolution.
  * `pipeline/structure.py`: Markdown-to-tree parsing and assignment of page metadata/bbox metadata.
  * `pipeline/chunk.py`: chunk metadata propagation into retrieval records.
* `server/models/schemas.py`: `ChunkMetadata`, source citation schemas, and document metadata models.
  * `server/services/pipeline_runner.py`: currently converts `doc_id` to `source_name = doc_id.replace("_", " ")`, which can lose repeated underscore identity when `server/core/generation.py` rebuilds `document_id`.
  * `server/core/generation.py`: `_build_document_id()` normalizes source strings and can collapse repeated separators, causing `/documents/{doc_id}/file` 404 for uploaded files whose real doc_id contains `__`.
* Important invariant: any page-bearing value from split-parser output must be converted from part-local coordinates to original-document coordinates before `parse_markdown_to_tree()` sees it.
* The safest failure mode is to mark the document parse as failed when page offsets cannot be validated, because incorrect citations are worse than no answer.
* User confirmed strict failure strategy on 2026-04-29: page citation correctness is mandatory for final LLM source tracing.
* Implementation completed with focused tests on 2026-04-29.
* Code-spec update: `.trellis/spec/backend/quality-guidelines.md` now records the PDF parser page metadata integrity contract.
