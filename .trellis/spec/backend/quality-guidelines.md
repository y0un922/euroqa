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

- Tests for guide retrieval must include an arbitrary guide-like uploaded document name, not a fixed project seed document.
- Tests must prove guide-like chunks are excluded from `RetrievalResult.chunks`.
- Tests must prove `guide_chunks` remains present in API retrieval context for backward compatibility.

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

<!-- Patterns that must always be used -->

---

## Testing Requirements

<!-- What level of testing is expected -->

- Parser metadata changes require focused tests for downstream citation metadata, not only provider API request/response behavior.

---

## Code Review Checklist

<!-- What reviewers should check -->

(To be filled by the team)
