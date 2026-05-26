# Citation Rendering

## Scope

This spec applies to frontend rendering of LLM answer citations and source labels.

## Contracts

- The backend answer may contain inline citations as `[Ref-N]`, grouped citations such as `[Ref-1, Ref-2]`, or parent-context citations such as `[Parent-N]` / `[Ref-1, Parent-3]`.
- `Ref-N` maps to `sources[N - 1]`; this order is a cross-layer contract and must not be reordered in the frontend.
- `Parent-N` refers to supplementary parent context. Unless the frontend receives a dedicated parent-reference record, render it as an unmatched citation badge instead of leaving raw text in the answer.
- User-visible source names should avoid opaque document ids. When `source.file` looks like an opaque id, prefer explicit display-name fields (`source.display_title`, `source.displayTitle`, `source.source_title`, `source.sourceTitle`), then `source.title`, then the matched document name/title, and use the raw id only as a fallback.

## Good / Bad Cases

- Good: `[Ref-1, Ref-2]` renders as two inline citation badges that point to `sources[0]` and `sources[1]`.
- Good: `[Parent-3]` renders as a compact non-clickable parent-context badge.
- Good: a source with `file = "ae71c790b26bdcc126b3be00be4f9825"` and `display_title = "Structural fire design"` displays `Structural fire design`.
- Good: a source with `file = "ae71c790b26bdcc126b3be00be4f9825"` and `displayTitle = "DG_EN1992-1-1, -1-2 混凝土设计指南.pdf"` displays the filename.
- Bad: raw `[Ref-1, Parent-3]` remains in Markdown output.
- Bad: an opaque doc id is shown as the primary document title when `display_title` is available.

## Tests Required

- Add or update `frontend/src/lib/citations.test.ts` when changing citation token parsing.
- Add or update `frontend/src/lib/inlineReferences.test.ts` when changing inline badge labels or tooltips.
- Add or update `frontend/src/lib/api.test.ts` when changing `Source` to `ReferenceRecord` title resolution.
