# PDF Citation Location And Source Translation Toggle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the right-side chunk preview with a PDF-first citation viewer that jumps to the cited page, highlights the cited text when possible, and makes citation translation an opt-in user-controlled feature.

**Architecture:** Backend `Source` payloads become PDF-location-aware by carrying stable `document_id` and `locator_text`, `/api/v1/query*` stops auto-filling source translations, `/api/v1/documents/{doc_id}/file` serves the raw PDF, and `/api/v1/sources/translate` translates one citation on demand. Frontend persists a `sourceTranslationEnabled` toggle in session state, renders a PDF.js-based viewer for the active citation, and lazily fetches/caches per-citation translations while guarding against stale in-flight requests.

**Tech Stack:** FastAPI, Pydantic, PyMuPDF, React 19, TypeScript, Vite, `react-pdf`, `pdfjs-dist`, `node:test`, `pytest`

---

## File Structure

**Backend**

- Modify: `server/models/schemas.py`
  Adds `document_id` and `locator_text` to `Source`, plus request/response models for the new source-translation endpoint.
- Modify: `server/core/generation.py`
  Enriches sources with PDF-location fields and removes automatic source translation from `generate_answer()` / `generate_answer_stream()`.
- Modify: `server/api/v1/documents.py`
  Adds a raw PDF file endpoint alongside the existing page-preview PNG endpoint.
- Create: `server/api/v1/sources.py`
  Exposes `POST /api/v1/sources/translate` and reuses the existing source-translation helper path.
- Modify: `server/api/v1/router.py`
  Registers the new sources router.
- Modify: `tests/server/test_generation.py`
  Covers enriched `Source` payloads and verifies query paths no longer auto-translate.
- Modify: `tests/server/test_api.py`
  Covers raw PDF serving and on-demand source translation API behavior.

**Frontend**

- Modify: `frontend/package.json`
  Adds PDF viewer dependencies.
- Modify: `frontend/pnpm-lock.yaml`
  Records the resolved dependency graph after adding the viewer packages.
- Modify: `frontend/src/lib/types.ts`
  Extends `Source` and session-related types.
- Modify: `frontend/src/lib/api.ts`
  Adds `buildDocumentFileUrl()`, `translateSource()`, and stops relying on fuzzy document matching when `document_id` is available.
- Modify: `frontend/src/lib/api.test.ts`
  Covers the new client helpers and richer source payload handling.
- Modify: `frontend/src/lib/session.ts`
  Persists `sourceTranslationEnabled` and validates the extended `Source` payload.
- Modify: `frontend/src/lib/session.test.ts`
  Covers the new persisted flag and richer restored source structure.
- Create: `frontend/src/lib/pdfLocator.ts`
  Houses text-normalization and page-level highlight status helpers.
- Create: `frontend/src/lib/pdfLocator.test.ts`
  Covers normalization and fallback behavior for locator text matching.
- Create: `frontend/src/components/PdfEvidenceViewer.tsx`
  Renders the PDF, jumps to the active page, and highlights matched text when available.
- Modify: `frontend/src/components/EvidencePanel.tsx`
  Replaces image preview + chunk block with PDF-first layout, per-spec status UI, and the citation-translation toggle/result block.
- Modify: `frontend/src/hooks/useEuroQaDemo.ts`
  Adds toggle state, citation-translation cache, stale-request protection, and PDF location status wiring.
- Modify: `frontend/src/App.tsx`
  Passes the new props required by `EvidencePanel`.

---

### Task 1: Enrich `Source` payloads and remove automatic source translation

**Files:**
- Modify: `server/models/schemas.py`
- Modify: `server/core/generation.py`
- Modify: `tests/server/test_generation.py`

- [ ] **Step 1: Write a failing test that `_build_sources_from_chunks()` includes `document_id` and `locator_text`**

```python
def test_build_sources_from_chunks_populates_document_id_and_locator_text():
    sources = _build_sources_from_chunks([chunk])
    assert sources[0].document_id == "EN1990_2002"
    assert sources[0].locator_text.startswith("Design working life")
```

- [ ] **Step 2: Run the targeted backend test and verify it fails for the expected reason**

Run: `uv run pytest tests/server/test_generation.py -q`
Expected: FAIL because `Source` has no `document_id` / `locator_text` yet.

- [ ] **Step 3: Write a failing test that `generate_answer_stream()` no longer auto-fills `translation`**

```python
with patch("server.core.generation._fill_missing_source_translations", AsyncMock()) as mock_fill:
    events = [event async for event in generate_answer_stream(...)]
assert events[-1][1]["sources"][0]["translation"] == ""
mock_fill.assert_not_awaited()
```

- [ ] **Step 4: Extend `Source` in `server/models/schemas.py`**

```python
class Source(BaseModel):
    file: str
    title: str
    section: str
    page: int | str
    clause: str
    original_text: str
    translation: str
    document_id: str
    locator_text: str
```

- [ ] **Step 5: Implement minimal source enrichment in `server/core/generation.py`**

```python
def _build_locator_text(content: str, max_length: int = 220) -> str:
    normalized = " ".join(content.split())
    return normalized[:max_length].strip()

def _build_sources_from_chunks(chunks: list[Chunk], limit: int = 5) -> list[Source]:
    ...
    Source(
        ...,
        translation="",
        document_id=meta.source.replace(":", "").replace(" ", "_"),
        locator_text=_build_locator_text(chunk.content),
    )
```

- [ ] **Step 6: Remove the automatic `_fill_missing_source_translations()` calls from both answer paths**

```python
sources = _build_sources_from_chunks(chunks)
# no automatic translation fill here
```

- [ ] **Step 7: Re-run backend tests and verify they pass**

Run: `uv run pytest tests/server/test_generation.py -q`
Expected: PASS for the new source contract and “no auto-translation” assertions.

- [ ] **Step 8: Commit the backend source-contract change**

```bash
git add server/models/schemas.py server/core/generation.py tests/server/test_generation.py
git commit -m "feat(server): enrich source payloads for pdf citation location"
```

### Task 2: Add raw PDF and on-demand citation translation APIs

**Files:**
- Modify: `server/models/schemas.py`
- Modify: `server/api/v1/documents.py`
- Create: `server/api/v1/sources.py`
- Modify: `server/api/v1/router.py`
- Modify: `tests/server/test_api.py`

- [ ] **Step 1: Write a failing API test for `GET /api/v1/documents/{doc_id}/file`**

```python
def test_documents_file_endpoint_returns_pdf_bytes(client, tmp_path):
    response = client.get("/api/v1/documents/EN1990_2002/file")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
```

- [ ] **Step 2: Write a failing API test for `POST /api/v1/sources/translate`**

```python
def test_sources_translate_returns_translation(client):
    response = client.post("/api/v1/sources/translate", json={
        "document_id": "EN1990_2002",
        "page": "18",
        "original_text": "Design working life ...",
        "locator_text": "Design working life ..."
    })
    assert response.status_code == 200
    assert response.json()["translation"]
```

- [ ] **Step 3: Add request/response models for the new route**

```python
class SourceTranslationRequest(BaseModel):
    document_id: str
    file: str
    section: str
    clause: str
    page: int | str
    original_text: str
    locator_text: str

class SourceTranslationResponse(BaseModel):
    translation: str
```

- [ ] **Step 4: Implement the raw PDF endpoint in `server/api/v1/documents.py`**

```python
@router.get("/documents/{doc_id}/file")
async def get_document_file(doc_id: str, config=Depends(get_config)) -> Response:
    pdf_path = Path(config.pdf_dir) / f"{doc_id}.pdf"
    return Response(content=pdf_path.read_bytes(), media_type="application/pdf")
```

- [ ] **Step 5: Create `server/api/v1/sources.py` with a minimal translation route**

```python
@router.post("/sources/translate", response_model=SourceTranslationResponse)
async def translate_source(req: SourceTranslationRequest, config=Depends(get_config)):
    source = Source(..., translation="")
    translated = await _fill_missing_source_translations([source], config)
    return SourceTranslationResponse(translation=translated[0].translation)
```

- [ ] **Step 6: Register the new router**

```python
from server.api.v1 import documents, glossary, query, settings, sources
router.include_router(sources.router, tags=["Sources"])
```

- [ ] **Step 7: Re-run API tests and verify the new routes are green**

Run: `uv run pytest tests/server/test_api.py -q`
Expected: PASS for raw PDF download and on-demand source translation.

- [ ] **Step 8: Commit the API additions**

```bash
git add server/models/schemas.py server/api/v1/documents.py server/api/v1/sources.py server/api/v1/router.py tests/server/test_api.py
git commit -m "feat(api): add pdf file and source translation endpoints"
```

### Task 3: Extend frontend source types, API clients, and persisted toggle state

**Files:**
- Modify: `frontend/src/lib/types.ts`
- Modify: `frontend/src/lib/api.ts`
- Modify: `frontend/src/lib/api.test.ts`
- Modify: `frontend/src/lib/session.ts`
- Modify: `frontend/src/lib/session.test.ts`

- [ ] **Step 1: Write a failing frontend API test for `buildDocumentFileUrl()` and `translateSource()`**

```typescript
test("translateSource posts a single citation payload", async () => {
  await translateSource({ document_id: "EN1990_2002", ... });
  assert.deepEqual(JSON.parse(seenBodies[0]), { document_id: "EN1990_2002", ... });
});
```

- [ ] **Step 2: Write a failing session test for `sourceTranslationEnabled` persistence**

```typescript
assert.equal(restored?.sourceTranslationEnabled, true);
```

- [ ] **Step 3: Extend `Source` and add request/response helpers in `types.ts`**

```typescript
export type Source = {
  file: string;
  title: string;
  section: string;
  page: number | string;
  clause: string;
  original_text: string;
  translation: string;
  document_id: string;
  locator_text: string;
};
```

- [ ] **Step 4: Implement new API helpers in `frontend/src/lib/api.ts`**

```typescript
export function buildDocumentFileUrl(documentId: string): string { ... }

export async function translateSource(payload: SourceTranslationRequest): Promise<SourceTranslationResponse> {
  return fetchJson("/api/v1/sources/translate", { method: "POST", body: JSON.stringify(payload) });
}
```

- [ ] **Step 5: Stop relying on fuzzy matching when the backend already sends `document_id`**

```typescript
documentId: source.document_id || matchSourceToDocumentId(source.file, documents)
```

- [ ] **Step 6: Persist the toggle in `session.ts` and keep legacy-session migration intact**

```typescript
export type PersistedDemoSession = {
  ...
  sourceTranslationEnabled: boolean;
};
```

- [ ] **Step 7: Re-run frontend library tests**

Run: `pnpm --dir frontend test`
Expected: PASS for API helpers and session persistence.

- [ ] **Step 8: Commit the frontend plumbing change**

```bash
git add frontend/src/lib/types.ts frontend/src/lib/api.ts frontend/src/lib/api.test.ts frontend/src/lib/session.ts frontend/src/lib/session.test.ts
git commit -m "feat(frontend): add citation location and translation client state"
```

### Task 4: Add PDF viewer dependencies and page-level locator helpers

**Files:**
- Modify: `frontend/package.json`
- Modify: `frontend/pnpm-lock.yaml`
- Create: `frontend/src/lib/pdfLocator.ts`
- Create: `frontend/src/lib/pdfLocator.test.ts`
- Create: `frontend/src/components/PdfEvidenceViewer.tsx`

- [ ] **Step 1: Add PDF viewer dependencies**

Run: `pnpm --dir frontend add react-pdf pdfjs-dist`
Expected: `package.json` and `pnpm-lock.yaml` update cleanly.

- [ ] **Step 2: Write a failing test for locator-text normalization**

```typescript
test("normalizeLocatorText collapses whitespace and preserves searchable text", () => {
  assert.equal(normalizeLocatorText("Design\n   working  life"), "design working life");
});
```

- [ ] **Step 3: Write a failing test for page-only fallback status**

```typescript
test("resolveLocationStatus falls back to page_only when no match range exists", () => {
  assert.equal(resolveLocationStatus(null), "page_only");
});
```

- [ ] **Step 4: Implement `pdfLocator.ts`**

```typescript
export type PdfLocationStatus = "idle" | "highlighted" | "page_only" | "error";

export function normalizeLocatorText(text: string): string { ... }
export function clipLocatorText(text: string, maxLength = 220): string { ... }
```

- [ ] **Step 5: Implement `PdfEvidenceViewer.tsx` using `react-pdf`**

```tsx
export default function PdfEvidenceViewer({ fileUrl, page, locatorText, onLocationResolved }: Props) {
  return (
    <Document file={fileUrl}>
      <Page pageNumber={page} renderTextLayer renderAnnotationLayer={false} />
    </Document>
  );
}
```

- [ ] **Step 6: Add minimal current-page text highlighting and fallback reporting**

```tsx
if (matchedRange) {
  onLocationResolved("highlighted");
} else {
  onLocationResolved("page_only");
}
```

- [ ] **Step 7: Run frontend tests and type-check**

Run: `pnpm --dir frontend test && pnpm --dir frontend lint`
Expected: PASS with no TypeScript errors.

- [ ] **Step 8: Commit the PDF viewer foundation**

```bash
git add frontend/package.json frontend/pnpm-lock.yaml frontend/src/lib/pdfLocator.ts frontend/src/lib/pdfLocator.test.ts frontend/src/components/PdfEvidenceViewer.tsx
git commit -m "feat(frontend): add pdf citation viewer foundation"
```

### Task 5: Integrate the PDF-first evidence panel and lazy citation translation flow

**Files:**
- Modify: `frontend/src/hooks/useEuroQaDemo.ts`
- Modify: `frontend/src/components/EvidencePanel.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/lib/session.ts`
- Modify: `frontend/src/lib/session.test.ts`

- [ ] **Step 1: Write a failing session test that restores `sourceTranslationEnabled` for a saved session**

```typescript
assert.deepEqual(restored?.sourceTranslationEnabled, true);
```

- [ ] **Step 2: Add toggle, cache, and request-guard state to `useEuroQaDemo.ts`**

```typescript
const [sourceTranslationEnabled, setSourceTranslationEnabled] = useState(
  persistedSession?.sourceTranslationEnabled ?? false
);
const [sourceTranslationCache, setSourceTranslationCache] = useState<Record<string, string>>({});
const [pdfLocationStatus, setPdfLocationStatus] = useState<PdfLocationStatus>("idle");
```

- [ ] **Step 3: Implement lazy translation fetch on toggle-on and active-reference changes**

```typescript
async function ensureActiveReferenceTranslation(reference: ReferenceRecord) {
  if (!sourceTranslationEnabled) return;
  if (sourceTranslationCache[key]) return;
  const result = await translateSource(...);
  if (activeReferenceId === reference.id) { ... }
}
```

- [ ] **Step 4: Replace the image preview layout in `EvidencePanel.tsx`**

```tsx
<PdfEvidenceViewer
  fileUrl={buildDocumentFileUrl(activeReference.documentId)}
  locatorText={activeReference.source.locator_text}
  page={toPreviewPage(activeReference.source.page)}
  onLocationResolved={onPdfLocationResolved}
/>
```

- [ ] **Step 5: Render the right-panel toggle and status text per spec**

```tsx
<button aria-pressed={sourceTranslationEnabled}>引用翻译</button>
{pdfLocationStatus === "page_only" ? "已定位到页，但未能精确高亮" : null}
```

- [ ] **Step 6: Update `App.tsx` to pass the new props without touching `TopBar`**

```tsx
<EvidencePanel
  activeReference={demo.activeReference}
  pdfLocationStatus={demo.pdfLocationStatus}
  sourceTranslationEnabled={demo.sourceTranslationEnabled}
  ...
/>
```

- [ ] **Step 7: Re-run frontend verification**

Run: `pnpm --dir frontend test && pnpm --dir frontend lint && pnpm --dir frontend build`
Expected: PASS, no stale-request errors, and the production bundle builds.

- [ ] **Step 8: Commit the integrated UI flow**

```bash
git add frontend/src/hooks/useEuroQaDemo.ts frontend/src/components/EvidencePanel.tsx frontend/src/App.tsx frontend/src/lib/session.ts frontend/src/lib/session.test.ts
git commit -m "feat(frontend): integrate pdf-first evidence panel"
```

### Task 6: Final verification across backend and frontend

**Files:**
- Modify: none required unless verification uncovers issues

- [ ] **Step 1: Run targeted backend verification**

Run: `uv run pytest tests/server/test_generation.py tests/server/test_api.py -q`
Expected: PASS for source construction, raw PDF serving, and on-demand source translation.

- [ ] **Step 2: Run targeted frontend verification**

Run: `pnpm --dir frontend test && pnpm --dir frontend lint && pnpm --dir frontend build`
Expected: PASS for API/session helpers, PDF locator helpers, and TypeScript build output.

- [ ] **Step 3: Perform a manual smoke check in the browser**

Run: `pnpm --dir frontend dev`
Expected:
- Clicking a citation opens the correct PDF page on the right.
- Successful matches show visible highlight.
- Failed matches stay on the correct page with the page-only notice.
- Turning on `引用翻译` immediately populates the active citation translation.
- Turning it off stops auto-fetching for newly selected citations.

- [ ] **Step 4: Commit any final verification fixes**

```bash
git add -A
git commit -m "fix: polish pdf citation location flow"
```
