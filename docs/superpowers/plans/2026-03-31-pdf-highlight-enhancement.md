# PDF Highlight Enhancement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace text-matching-based PDF citation highlighting with bbox coordinate overlays propagated from MinerU's content_list, and redesign the right-side evidence panel for a PDF-first layout.

**Architecture:** Pipeline propagates `bbox` and `bbox_page_idx` from MinerU `content_list.json` through `ContentListEntry` → `DocumentNode` → `ChunkMetadata` → ES index → `Source`. The frontend `PdfEvidenceViewer` renders a positioned overlay div using the 0-1000 normalized coordinates, falling back to existing text matching when bbox is absent. `EvidencePanel` is restructured into three layers: compact header (48px) + PDF viewer (flex-1) + collapsible translation bar.

**Tech Stack:** Python 3.12, FastAPI, Pydantic, pytest, React 19, TypeScript, Vite, `react-pdf`, `pdfjs-dist`, `node:test`

---

## File Structure

**Pipeline**

- Modify: `pipeline/content_list.py`
  Extends `ContentListEntry` with `bbox` and `element_type` fields; validates bbox on extraction.
- Modify: `pipeline/structure.py`
  Extends `DocumentNode` with `bbox` and `bbox_page_idx`; backfills from matched content_list entries.
- Modify: `pipeline/chunk.py`
  Propagates `bbox` and `bbox_page_idx` from `DocumentNode` into `ChunkMetadata` during chunk construction.
- Modify: `pipeline/index.py`
  Adds `bbox` (float array) and `bbox_page_idx` (integer) to ES mapping.

**Backend**

- Modify: `server/models/schemas.py`
  Adds `bbox` and `bbox_page_idx` fields to `ChunkMetadata`.
- Modify: `server/core/generation.py`
  Uses `ChunkMetadata.bbox` directly instead of runtime content_list traversal; resolves `Source.page` from `bbox_page_idx`.
- Modify: `server/core/retrieval.py`
  No code change required — `_fetch_chunks` already uses `ChunkMetadata.model_fields` for dynamic field mapping.

**Frontend**

- Modify: `frontend/src/lib/pdfLocator.ts`
  Adds `bboxToOverlayStyle()` utility for 0-1000 → CSS percentage conversion.
- Modify: `frontend/src/lib/pdfLocator.test.ts`
  Tests for bbox conversion, edge cases, and fallback logic.
- Modify: `frontend/src/components/PdfEvidenceViewer.tsx`
  Uses bbox overlay for all element types; always renders text layer; fixes coordinate division bug.
- Modify: `frontend/src/components/EvidencePanel.tsx`
  Three-layer layout: compact header + flex-1 PDF viewer + collapsible translation bar.
- Modify: `frontend/src/lib/evidencePanelLayout.ts`
  Updates panel class names for new layout.
- Modify: `frontend/src/lib/evidenceDebug.ts`
  No structural change — existing code already handles bbox display.

**Tests**

- Modify: `tests/conftest.py`
  Adds `bbox` and `bbox_page_idx` to sample fixtures.
- Modify: `tests/pipeline/test_structure.py`
  Verifies bbox backfill from content_list to DocumentNode.
- Modify: `tests/pipeline/test_chunk.py`
  Verifies bbox inheritance from DocumentNode to ChunkMetadata.
- Modify: `tests/server/test_generation.py`
  Verifies `_build_sources_from_chunks` uses metadata bbox and bbox_page_idx for page.
- Modify: `frontend/src/lib/pdfLocator.test.ts`
  Adds bbox-to-CSS conversion tests.

---

### Task 1: Extend `ChunkMetadata` with bbox fields and update fixtures

**Files:**
- Modify: `server/models/schemas.py`
- Modify: `tests/conftest.py`

- [ ] **Step 1: Write a failing test that ChunkMetadata accepts bbox fields**

Add to a new test in `tests/test_config.py` or verify inline: create a `ChunkMetadata` with `bbox=[100, 200, 300, 400]` and `bbox_page_idx=5`. This will fail because the fields don't exist yet.

Run: `uv run python -c "from server.models.schemas import ChunkMetadata; ChunkMetadata(source='x', source_title='x', section_path=[], page_numbers=[], page_file_index=[], clause_ids=[], element_type='text', bbox=[100,200,300,400], bbox_page_idx=5)"`
Expected: FAIL — `bbox` and `bbox_page_idx` are unexpected fields.

- [ ] **Step 2: Add bbox and bbox_page_idx to ChunkMetadata**

In `server/models/schemas.py`, add to `ChunkMetadata`:

```python
class ChunkMetadata(BaseModel):
    source: str
    source_title: str
    section_path: list[str]
    page_numbers: list[int]
    page_file_index: list[int]
    clause_ids: list[str]
    element_type: ElementType
    cross_refs: list[str] = []
    parent_chunk_id: Optional[str] = None
    parent_text_chunk_id: Optional[str] = None
    bbox: list[float] = []
    bbox_page_idx: int = -1
```

- [ ] **Step 3: Verify the field addition works**

Run: `uv run python -c "from server.models.schemas import ChunkMetadata; m = ChunkMetadata(source='x', source_title='x', section_path=[], page_numbers=[], page_file_index=[], clause_ids=[], element_type='text', bbox=[100,200,300,400], bbox_page_idx=5); print(m.bbox, m.bbox_page_idx)"`
Expected: `[100.0, 200.0, 300.0, 400.0] 5`

- [ ] **Step 4: Update test fixtures in conftest.py**

Add `bbox` and `bbox_page_idx` to both `sample_text_chunk` and `sample_table_chunk`:

```python
@pytest.fixture
def sample_text_chunk() -> Chunk:
    return Chunk(
        ...
        metadata=ChunkMetadata(
            ...
            bbox=[186, 362, 858, 420],
            bbox_page_idx=27,
        ),
    )

@pytest.fixture
def sample_table_chunk() -> Chunk:
    return Chunk(
        ...
        metadata=ChunkMetadata(
            ...
            bbox=[186, 591, 858, 768],
            bbox_page_idx=27,
        ),
    )
```

- [ ] **Step 5: Run existing tests to confirm nothing breaks**

Run: `uv run pytest tests/ -q --tb=short`
Expected: All existing tests PASS. The new fields have defaults so old code is unaffected.

- [ ] **Step 6: Commit**

```bash
git add server/models/schemas.py tests/conftest.py
git commit -m "feat(schemas): add bbox and bbox_page_idx to ChunkMetadata"
```

---

### Task 2: Extend ContentListEntry with bbox and element_type

**Files:**
- Modify: `pipeline/content_list.py`
- Modify: `tests/pipeline/test_structure.py` (content_list tests are here)

- [ ] **Step 1: Write a failing test for ContentListEntry bbox extraction**

Add to `tests/pipeline/test_structure.py` (or a new `tests/pipeline/test_content_list.py`):

```python
from pipeline.content_list import ContentListEntry, resolve_section_page_metadata

class TestContentListBbox:
    def test_extracts_bbox_via_resolve(self):
        """Test bbox extraction through the public API."""
        segments = [(2, "Design working life", "body text")]
        raw = [
            {"type": "text", "text": "Design working life", "page_idx": 27,
             "text_level": 2, "bbox": [186, 362, 858, 420]}
        ]
        results = resolve_section_page_metadata(segments, raw)
        page_numbers, page_file_indexes, bbox, bbox_page_idx = results[0]
        assert bbox == [186, 362, 858, 420]
        assert bbox_page_idx == 27

    def test_rejects_invalid_bbox_via_resolve(self):
        segments = [(2, "Hello", "body")]
        raw = [
            {"type": "text", "text": "Hello", "page_idx": 0,
             "text_level": 2, "bbox": [100, 200]}
        ]
        results = resolve_section_page_metadata(segments, raw)
        _, _, bbox, _ = results[0]
        assert bbox == []

    def test_rejects_out_of_range_bbox(self):
        segments = [(2, "Hello", "body")]
        raw = [
            {"type": "text", "text": "Hello", "page_idx": 0,
             "text_level": 2, "bbox": [100, 200, 1500, 400]}
        ]
        results = resolve_section_page_metadata(segments, raw)
        _, _, bbox, _ = results[0]
        assert bbox == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/pipeline/test_structure.py::TestContentListBbox -v`
Expected: FAIL — `resolve_section_page_metadata` returns 2-tuples, not 4-tuples.

- [ ] **Step 3: Extend ContentListEntry and _normalize_content_list**

In `pipeline/content_list.py`:

```python
@dataclass(frozen=True)
class ContentListEntry:
    """Flattened MinerU content_list entry used for section-page matching."""
    index: int
    page_idx: int
    text: str
    text_level: int
    bbox: list[float] = field(default_factory=list)
    element_type: str = ""
```

Add a validation helper:

```python
def _validate_bbox(raw_bbox: object) -> list[float]:
    """Validate and return bbox, or empty list if invalid."""
    if not isinstance(raw_bbox, list) or len(raw_bbox) != 4:
        return []
    values = []
    for v in raw_bbox:
        if not isinstance(v, (int, float)):
            return []
        if v < 0 or v > 1000:
            return []
        values.append(float(v))
    return values
```

Update `_normalize_content_list` to extract bbox and type:

```python
entries.append(
    ContentListEntry(
        index=index,
        page_idx=page_idx,
        text=text,
        text_level=text_level,
        bbox=_validate_bbox(item.get("bbox")),
        element_type=str(item.get("type", "")),
    )
)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/pipeline/test_structure.py::TestContentListBbox -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add pipeline/content_list.py tests/pipeline/test_structure.py
git commit -m "feat(pipeline): extract bbox and element_type in ContentListEntry"
```

---

### Task 3: Propagate bbox from content_list to DocumentNode

**Files:**
- Modify: `pipeline/structure.py`
- Modify: `pipeline/content_list.py` (expose entries for bbox backfill)
- Modify: `tests/pipeline/test_structure.py`

- [ ] **Step 1: Write a failing test for DocumentNode bbox backfill**

```python
class TestDocumentNodeBbox:
    def test_section_node_receives_bbox_from_content_list(self):
        md = "## 2.3 Design working life\n\n(1) The design working life should be specified.\n"
        content_list = [
            {"type": "text", "text": "2.3 Design working life",
             "page_idx": 27, "text_level": 2, "bbox": [186, 362, 858, 420]},
            {"type": "text", "text": "The design working life should be specified.",
             "page_idx": 27, "text_level": 0, "bbox": [186, 430, 858, 470]},
        ]
        tree = parse_markdown_to_tree(md, source="EN 1990:2002", content_list=content_list)
        section = tree.children[0]
        assert section.bbox == [186, 362, 858, 420]
        assert section.bbox_page_idx == 27
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/pipeline/test_structure.py::TestDocumentNodeBbox -v`
Expected: FAIL — `DocumentNode` has no `bbox` field.

- [ ] **Step 3: Add bbox and bbox_page_idx to DocumentNode**

In `pipeline/structure.py`:

```python
@dataclass
class DocumentNode:
    title: str
    content: str = ""
    element_type: ElementType = ElementType.SECTION
    level: int = 0
    page_numbers: list[int] = field(default_factory=list)
    page_file_index: list[int] = field(default_factory=list)
    clause_ids: list[str] = field(default_factory=list)
    cross_refs: list[str] = field(default_factory=list)
    children: list[DocumentNode] = field(default_factory=list)
    source: str = ""
    bbox: list[float] = field(default_factory=list)
    bbox_page_idx: int = -1
```

- [ ] **Step 4: Backfill bbox during page metadata resolution**

Modify `resolve_section_page_metadata` (or add a new `backfill_bbox_from_content_list` function) so that when a heading is matched to a `ContentListEntry`, the entry's `bbox` and `page_idx` are written to the corresponding `DocumentNode`.

This requires `resolve_section_page_metadata` to return bbox data alongside page data, or a separate pass that takes the matched heading indexes and writes bbox back to nodes.

Extend `resolve_section_page_metadata` to return bbox data per segment:

```python
def resolve_section_page_metadata(
    segments: list[tuple[int, str, str]],
    content_list: object,
) -> list[tuple[list[int], list[int], list[float], int]]:
```

Each returned tuple becomes `(page_numbers, page_file_indexes, bbox, bbox_page_idx)`. For matched headings, `bbox` and `bbox_page_idx` come from the matched `ContentListEntry`. For unmatched headings, return `([], [], [], -1)`.

Then update the destructuring in `structure.py` (line 209):

```python
for (level, title, body), (page_numbers, page_file_index, bbox, bbox_page_idx) in zip(
    segments,
    section_pages,
    strict=False,
):
    node = DocumentNode(
        title=title,
        element_type=ElementType.SECTION,
        level=level,
        page_numbers=page_numbers,
        page_file_index=page_file_index,
        source=source,
        bbox=bbox,
        bbox_page_idx=bbox_page_idx,
    )
```

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/pipeline/test_structure.py -v`
Expected: PASS for the new bbox test and all existing tests.

- [ ] **Step 6: Commit**

```bash
git add pipeline/content_list.py pipeline/structure.py tests/pipeline/test_structure.py
git commit -m "feat(pipeline): propagate bbox from content_list to DocumentNode"
```

---

### Task 4: Propagate bbox from DocumentNode to ChunkMetadata

**Files:**
- Modify: `pipeline/chunk.py`
- Modify: `tests/pipeline/test_chunk.py`

- [ ] **Step 1: Write a failing test for chunk bbox inheritance**

```python
class TestChunkBboxInheritance:
    def test_child_text_chunk_inherits_section_bbox(self):
        md = "## 2.3 Design working life\n\n(1) The design working life.\n"
        tree = parse_markdown_to_tree(md, source="EN 1990:2002")
        # Manually set bbox on the section node to simulate content_list backfill
        tree.children[0].bbox = [186, 362, 858, 420]
        tree.children[0].bbox_page_idx = 27
        chunks = create_chunks(tree, source_title="Basis")
        text_chunks = [c for c in chunks if c.metadata.element_type.value == "text"]
        assert len(text_chunks) >= 1
        assert text_chunks[0].metadata.bbox == [186, 362, 858, 420]
        assert text_chunks[0].metadata.bbox_page_idx == 27

    def test_special_chunk_inherits_parent_section_bbox(self):
        md = (
            "## 2.3 Design working life\n\n"
            "(1) Specified.\n\n"
            "| Cat | Years |\n|---|---|\n|1|10|\n"
        )
        tree = parse_markdown_to_tree(md, source="EN 1990:2002")
        tree.children[0].bbox = [186, 362, 858, 420]
        tree.children[0].bbox_page_idx = 27
        chunks = create_chunks(tree, source_title="Basis")
        table_chunks = [c for c in chunks if c.metadata.element_type.value == "table"]
        assert len(table_chunks) >= 1
        # Table chunk inherits section bbox as fallback (pipeline doesn't yet resolve per-element bbox)
        assert table_chunks[0].metadata.bbox == [186, 362, 858, 420]

    def test_parent_chunk_uses_first_child_bbox(self):
        md = (
            "# Section 2\n\n"
            "## 2.1 Basic\n\n(1) A structure.\n\n"
            "## 2.3 Design\n\n(1) Specified.\n"
        )
        tree = parse_markdown_to_tree(md, source="EN 1990:2002")
        tree.children[0].children[0].bbox = [100, 200, 300, 400]
        tree.children[0].children[0].bbox_page_idx = 10
        tree.children[0].children[1].bbox = [100, 500, 300, 600]
        tree.children[0].children[1].bbox_page_idx = 12
        chunks = create_chunks(tree, source_title="Basis")
        parents = [c for c in chunks if c.metadata.parent_chunk_id is None
                   and "Section 2" in str(c.metadata.section_path)]
        assert len(parents) >= 1
        assert parents[0].metadata.bbox == [100, 200, 300, 400]
        assert parents[0].metadata.bbox_page_idx == 10
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/pipeline/test_chunk.py::TestChunkBboxInheritance -v`
Expected: FAIL — ChunkMetadata constructed without bbox.

- [ ] **Step 3: Pass bbox through chunk construction**

In `_build_child_text_chunk`:

```python
metadata=ChunkMetadata(
    ...
    bbox=list(node.bbox),
    bbox_page_idx=node.bbox_page_idx,
),
```

In `_build_special_chunk`:

```python
metadata=ChunkMetadata(
    ...
    bbox=list(special_node.bbox) if special_node.bbox else list(parent_section.bbox),
    bbox_page_idx=special_node.bbox_page_idx if special_node.bbox_page_idx >= 0 else parent_section.bbox_page_idx,
),
```

In `_build_parent_chunk`, after the existing metadata aggregation loop, add:

```python
first_bbox: list[float] = []
first_bbox_page_idx = -1
for child in child_chunks:
    if child.metadata.bbox:
        first_bbox = list(child.metadata.bbox)
        first_bbox_page_idx = child.metadata.bbox_page_idx
        break

return Chunk(
    ...
    metadata=ChunkMetadata(
        ...
        bbox=first_bbox,
        bbox_page_idx=first_bbox_page_idx,
    ),
)
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/pipeline/test_chunk.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add pipeline/chunk.py tests/pipeline/test_chunk.py
git commit -m "feat(pipeline): propagate bbox from DocumentNode to ChunkMetadata"
```

---

### Task 5: Add bbox to ES mapping and update source construction

**Files:**
- Modify: `pipeline/index.py`
- Modify: `server/core/generation.py`
- Modify: `tests/server/test_generation.py`

- [ ] **Step 1: Write a failing test that _build_sources_from_chunks uses metadata bbox**

```python
class TestBuildSourcesBbox:
    def test_uses_metadata_bbox_for_text_chunk(self, sample_text_chunk):
        sources = _build_sources_from_chunks([sample_text_chunk])
        assert sources[0].bbox == [186, 362, 858, 420]
        assert sources[0].page == "28"  # bbox_page_idx 27 + 1

    def test_uses_metadata_bbox_for_table_chunk(self, sample_table_chunk):
        sources = _build_sources_from_chunks([sample_table_chunk])
        assert sources[0].bbox == [186, 591, 858, 768]

    def test_falls_back_to_page_numbers_when_no_bbox(self, sample_text_chunk):
        no_bbox_chunk = sample_text_chunk.model_copy(
            update={"metadata": sample_text_chunk.metadata.model_copy(
                update={"bbox": [], "bbox_page_idx": -1, "page_numbers": [30]}
            )}
        )
        sources = _build_sources_from_chunks([no_bbox_chunk])
        assert sources[0].bbox == []
        assert sources[0].page == "30"  # from page_numbers[0], NOT bbox_page_idx
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/server/test_generation.py::TestBuildSourcesBbox -v`
Expected: FAIL — current code only resolves bbox for TABLE type.

- [ ] **Step 3: Update _build_sources_from_chunks to use metadata bbox**

In `server/core/generation.py`, replace the current bbox/page resolution block:

```python
def _build_sources_from_chunks(
    chunks: list[Chunk],
    limit: int = 5,
    config: ServerConfig | None = None,
) -> list[Source]:
    sources: list[Source] = []
    cfg = config or ServerConfig()
    for chunk in chunks[:limit]:
        meta = chunk.metadata
        document_id = _build_document_id(meta.source)

        # Primary: use bbox from pipeline metadata
        bbox = list(meta.bbox) if meta.bbox else []
        resolved_page = str(meta.bbox_page_idx + 1) if meta.bbox_page_idx >= 0 else ""

        # Fallback for table: runtime content_list traversal (legacy data without pipeline bbox)
        if not bbox and meta.element_type == ElementType.TABLE:
            bbox, resolved_page = _resolve_table_source_geometry(chunk, document_id, cfg)

        sources.append(
            Source(
                file=meta.source,
                document_id=document_id,
                element_type=meta.element_type,
                bbox=bbox,
                title=meta.source_title,
                section=" > ".join(meta.section_path),
                page=resolved_page or (str(meta.page_numbers[0]) if meta.page_numbers else ""),
                clause=", ".join(meta.clause_ids[:2]) if meta.clause_ids else "",
                original_text=chunk.content,
                locator_text=_build_locator_text(chunk.content),
                highlight_text=_build_highlight_text(chunk.content, meta.page_numbers),
                translation="",
            )
        )
    return sources
```

- [ ] **Step 4: Add bbox fields to ES mapping**

In `pipeline/index.py`, add to `_ES_MAPPING["mappings"]["properties"]`:

```python
"bbox": {"type": "float"},
"bbox_page_idx": {"type": "integer"},
"page_file_index": {"type": "integer"},
```

Note: `page_file_index` was already missing from the mapping but was indexed via `model_dump()`. Adding it explicitly is a good hygiene fix. These mapping changes only take effect on a **fresh** ES index (the code skips `create` if the index exists). For existing deployments, a reindex is required — delete and recreate the index, then rerun the pipeline index stage.

- [ ] **Step 5: Run all backend tests**

Run: `uv run pytest tests/ -q --tb=short`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add pipeline/index.py server/core/generation.py tests/server/test_generation.py
git commit -m "feat(server): use pipeline bbox for source construction, add bbox to ES mapping"
```

---

### Task 6: Add bbox-to-CSS conversion utility and tests

**Files:**
- Modify: `frontend/src/lib/pdfLocator.ts`
- Modify: `frontend/src/lib/pdfLocator.test.ts`

- [ ] **Step 1: Write failing tests for bboxToOverlayStyle**

In `frontend/src/lib/pdfLocator.test.ts`:

```typescript
test("bboxToOverlayStyle converts 0-1000 bbox to CSS percentages", () => {
  const style = bboxToOverlayStyle([100, 200, 500, 600]);
  assert.deepEqual(style, {
    left: "10%",
    top: "20%",
    width: "40%",
    height: "40%",
  });
});

test("bboxToOverlayStyle returns null for invalid bbox", () => {
  assert.equal(bboxToOverlayStyle([100, 200]), null);
  assert.equal(bboxToOverlayStyle([]), null);
  assert.equal(bboxToOverlayStyle(undefined as any), null);
});

test("bboxToOverlayStyle clamps negative values to zero", () => {
  const style = bboxToOverlayStyle([-10, -20, 500, 600]);
  assert.equal(style?.left, "0%");
  assert.equal(style?.top, "0%");
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pnpm --dir frontend test`
Expected: FAIL — `bboxToOverlayStyle` not exported.

- [ ] **Step 3: Implement bboxToOverlayStyle**

In `frontend/src/lib/pdfLocator.ts`:

```typescript
export type BboxOverlayStyle = {
  left: string;
  top: string;
  width: string;
  height: string;
};

export function bboxToOverlayStyle(
  bbox: number[] | null | undefined
): BboxOverlayStyle | null {
  if (!Array.isArray(bbox) || bbox.length !== 4) {
    return null;
  }
  if (!bbox.every((v) => Number.isFinite(v))) {
    return null;
  }

  const [x0, y0, x1, y1] = bbox;
  const left = Math.max(0, Math.min(x0, x1)) / 1000;
  const top = Math.max(0, Math.min(y0, y1)) / 1000;
  const right = Math.min(1000, Math.max(x0, x1)) / 1000;
  const bottom = Math.min(1000, Math.max(y0, y1)) / 1000;

  return {
    left: `${(left * 100).toFixed()}%`,
    top: `${(top * 100).toFixed()}%`,
    width: `${((right - left) * 100).toFixed()}%`,
    height: `${((bottom - top) * 100).toFixed()}%`,
  };
}
```

- [ ] **Step 4: Run tests**

Run: `pnpm --dir frontend test`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/pdfLocator.ts frontend/src/lib/pdfLocator.test.ts
git commit -m "feat(frontend): add bboxToOverlayStyle conversion utility"
```

---

### Task 7: Update PdfEvidenceViewer for bbox-first highlighting

**Files:**
- Modify: `frontend/src/components/PdfEvidenceViewer.tsx`

- [ ] **Step 1: Remove the elementType === "table" guard**

Change line 52 from:

```typescript
const useBboxOverlay = elementType === "table" && hasUsablePdfBbox(bbox);
```

To:

```typescript
const useBboxOverlay = hasUsablePdfBbox(bbox);
```

- [ ] **Step 2: Always render the text layer**

Change `renderTextLayer={!useBboxOverlay}` (line 142) to:

```typescript
renderTextLayer
```

This ensures text remains selectable even when bbox overlay is active.

- [ ] **Step 3: Fix the overlay coordinate calculation**

Replace the existing `overlayStyle` useMemo (lines 90-109) with one that uses the new `bboxToOverlayStyle`:

```typescript
import { bboxToOverlayStyle } from "../lib/pdfLocator";

const overlayStyle = useMemo(() => {
  if (!useBboxOverlay) {
    return null;
  }
  return bboxToOverlayStyle(bbox);
}, [bbox, useBboxOverlay]);
```

This replaces the buggy `pageViewport`-based division with correct `/1000` normalization. Remove the `pageViewport` dependency from this calculation.

- [ ] **Step 4: Update the overlay reporting logic**

The existing `useEffect` that reports `highlighted` when `overlayStyle` is set (lines 111-116) can remain as-is, but remove the `!useBboxOverlay` guard since we now always allow bbox overlay:

```typescript
useEffect(() => {
  if (!overlayStyle || hasFatalErrorRef.current) {
    return;
  }
  reportStatus("highlighted");
}, [overlayStyle]);
```

- [ ] **Step 5: Remove elementType from PdfEvidenceViewerProps (optional cleanup)**

The `elementType` prop is no longer used for overlay gating. It can remain for potential future use but is no longer required for overlay decisions.

- [ ] **Step 6: Run frontend type check and tests**

Run: `pnpm --dir frontend test && pnpm --dir frontend lint`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/PdfEvidenceViewer.tsx
git commit -m "feat(frontend): use bbox overlay for all element types, fix coordinate bug"
```

---

### Task 8: Redesign EvidencePanel layout

**Files:**
- Modify: `frontend/src/components/EvidencePanel.tsx`
- Modify: `frontend/src/lib/evidencePanelLayout.ts`

- [ ] **Step 1: Rewrite EvidencePanel with three-layer structure**

Replace the entire JSX return of the active-reference branch with:

**Layer 1: Compact header (48px)**

```tsx
<div className="flex h-12 shrink-0 items-center justify-between border-b border-stone-200 bg-stone-50/80 px-4">
  <div className="flex items-center gap-2 overflow-hidden">
    <ShieldCheck className="h-3.5 w-3.5 shrink-0 text-cyan-700" />
    <span className="truncate font-mono text-[11px] font-semibold text-stone-700">
      {activeReference.documentId ?? activeReference.source.document_id ?? ""}
    </span>
    {activeReference.source.clause ? (
      <span className="text-[10px] text-stone-400">§{activeReference.source.clause}</span>
    ) : null}
    <span className="text-[10px] text-stone-400">p.{activeReference.source.page}</span>
    <span className={`rounded-full px-2 py-0.5 text-[9px] font-semibold ${getPdfLocationTone(pdfLocationStatus)}`}>
      {getPdfLocationLabel(pdfLocationStatus)}
    </span>
  </div>
  <div className="flex items-center gap-2">
    <span className="text-[10px] text-stone-500">翻译</span>
    <button
      aria-pressed={sourceTranslationEnabled}
      className={`relative h-[18px] w-9 rounded-full transition-colors ${
        sourceTranslationEnabled ? "bg-cyan-600" : "bg-stone-300"
      }`}
      disabled={!onSourceTranslationEnabledChange}
      onClick={() => onSourceTranslationEnabledChange?.(!sourceTranslationEnabled)}
      type="button"
    >
      <span className={`absolute top-[2px] h-[14px] w-[14px] rounded-full bg-white shadow transition-[left] ${
        sourceTranslationEnabled ? "left-[18px]" : "left-[2px]"
      }`} />
    </button>
  </div>
</div>
```

**Layer 2: PDF viewer (flex-1)**

```tsx
<div className="relative min-h-0 flex-1 bg-neutral-600">
  {pdfFileUrl || activeReference.documentId || activeReference.source.document_id ? (
    <PdfEvidenceViewer
      fileUrl={pdfFileUrl ?? buildDocumentFileUrl(activeReference.documentId ?? activeReference.source.document_id ?? "")}
      elementType={activeReference.source.element_type}
      bbox={activeReference.source.bbox}
      highlightText={activeReference.source.highlight_text?.trim() || ""}
      locatorText={activeReference.source.locator_text?.trim() || activeReference.source.original_text || ""}
      onLocationResolved={onPdfLocationResolved}
      page={toPdfPage(activeReference.source.page)}
    />
  ) : (
    <div className="flex h-full items-center justify-center px-4 text-center text-sm text-stone-400">
      当前引用未提供可用文档 ID。
    </div>
  )}
</div>
```

**Layer 3: Translation bar (auto height)**

```tsx
<div className="shrink-0 border-t border-stone-200 bg-stone-50/80">
  {!sourceTranslationEnabled ? (
    <div className="px-4 py-2.5 text-[11px] text-stone-400">引用翻译已关闭</div>
  ) : sourceTranslationLoading ? (
    <div className="flex items-center gap-2 px-4 py-2.5 text-[11px] text-stone-500">
      <LoaderCircle className="h-3 w-3 animate-spin text-cyan-600" />
      正在生成引用翻译…
    </div>
  ) : sourceTranslationError ? (
    <div className="px-4 py-2.5 text-[11px] text-rose-600">翻译失败：{sourceTranslationError}</div>
  ) : resolvedTranslation.trim() ? (
    <div className="max-h-40 overflow-y-auto px-4 py-3">
      <div className={translationMarkdownClassName}>
        <ReactMarkdown rehypePlugins={markdownRehypePlugins} remarkPlugins={markdownRemarkPlugins}>
          {resolvedTranslation}
        </ReactMarkdown>
      </div>
    </div>
  ) : (
    <div className="px-4 py-2.5 text-[11px] text-stone-400">已开启，暂无译文</div>
  )}
</div>
```

- [ ] **Step 2: Remove debug sections from main view**

Remove the entire "定位文本对照" section and "原文引用的其他标准" section from the main layout. The debug imports (`buildEvidenceDebugFields`, `getDefaultEvidenceDebugSectionKey`, `resolveActiveEvidenceDebugField`, `activeDebugSectionKey` state, `activeDebugField`) can be removed.

Keep the `evidenceDebug.ts` module intact — it can be wired into a debug popover in a follow-up if needed.

- [ ] **Step 3: Remove the fixed h-[340px] PDF container**

The old `<div className="h-[340px] bg-stone-100">` is gone, replaced by the flex-1 layer above.

- [ ] **Step 4: Run type check and build**

Run: `pnpm --dir frontend lint && pnpm --dir frontend build`
Expected: PASS with no TypeScript errors.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/EvidencePanel.tsx frontend/src/lib/evidencePanelLayout.ts
git commit -m "feat(frontend): redesign EvidencePanel with three-layer PDF-first layout"
```

---

### Task 9: End-to-end verification

**Files:**
- No new files unless fixes needed

- [ ] **Step 1: Run full backend test suite**

Run: `uv run pytest tests/ -q --tb=short`
Expected: All PASS

- [ ] **Step 2: Run full frontend test suite**

Run: `pnpm --dir frontend test && pnpm --dir frontend lint && pnpm --dir frontend build`
Expected: All PASS, production build succeeds.

- [ ] **Step 3: Manual smoke check in browser**

Run: `pnpm --dir frontend dev`

Verify:
- Clicking a citation opens the correct PDF page on the right
- bbox overlay appears as a semi-transparent cyan rectangle over the cited content
- The overlay position matches the actual content location on the PDF page
- The compact header shows document name, clause, page, and status badge
- The translation toggle works: on → loads translation in bottom bar; off → hides it
- When bbox is missing (old data), text matching still works as fallback
- PDF text remains selectable even with bbox overlay active

- [ ] **Step 4: Commit any fixes discovered during verification**

```bash
git add -u
git commit -m "fix: address issues found during e2e verification"
```
