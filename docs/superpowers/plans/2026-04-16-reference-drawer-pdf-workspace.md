# Reference Drawer PDF Workspace Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把右侧证据区改造成整页 PDF 阅读工作区，并使用可拖拽的底部引用抽屉展示原文与翻译。

**Architecture:** 以 `EvidencePanel` 为主协调层，`PdfEvidenceViewer` 负责整页 PDF 阅读，抽屉开合和高度计算下沉到独立工具模块，减少 JSX 内联状态机复杂度。

**Tech Stack:** React 19, TypeScript, motion/react, react-pdf, node:test

---

### Task 1: Port PDF workspace helpers

**Files:**
- Create: `frontend/src/lib/evidencePanelPdf.ts`
- Create: `frontend/src/lib/pdfViewerPage.ts`
- Test: `frontend/src/components/EvidencePanel.test.tsx`

- [ ] **Step 1: Add failing/static coverage for full-page PDF payload expectations**
- [ ] **Step 2: Port `buildPdfViewerPayload()` from reference project**
- [ ] **Step 3: Port page navigation helpers for PDF viewer**
- [ ] **Step 4: Run `node --test frontend/src/components/EvidencePanel.test.tsx`**

### Task 2: Add drawer layout utility

**Files:**
- Create: `frontend/src/lib/evidenceDrawerLayout.ts`
- Test: `frontend/src/lib/evidenceDrawerLayout.test.ts`

- [ ] **Step 1: Write failing tests for min/max/default drawer height behavior**
- [ ] **Step 2: Implement clamp/default/drag height helpers**
- [ ] **Step 3: Run `node --test frontend/src/lib/evidenceDrawerLayout.test.ts`**

### Task 3: Replace `PdfEvidenceViewer` with full-page reader

**Files:**
- Modify: `frontend/src/components/PdfEvidenceViewer.tsx`
- Reference: `/Volumes/software/webdav/Euro_QA_pageindex/frontend/src/components/PdfEvidenceViewer.tsx`

- [ ] **Step 1: Replace highlight-first viewer with full-page navigation viewer**
- [ ] **Step 2: Keep `page` as requested initial page and preserve `onLocationResolved`**
- [ ] **Step 3: Run targeted frontend tests**

### Task 4: Rebuild `EvidencePanel` as PDF + overlay drawer

**Files:**
- Modify: `frontend/src/components/EvidencePanel.tsx`
- Modify: `frontend/src/index.css`
- Test: `frontend/src/components/EvidencePanel.test.tsx`

- [ ] **Step 1: Add failing static-render tests for drawer button/content states**
- [ ] **Step 2: Introduce drawer open state, default-open-on-reference, and overlay layout**
- [ ] **Step 3: Add drag handle and pointer-based resize behavior using `evidenceDrawerLayout.ts`**
- [ ] **Step 4: Preserve translation toggle/loading/error states inside the drawer**
- [ ] **Step 5: Add copy-original action and polish button states**
- [ ] **Step 6: Run targeted tests**

### Task 5: Validate end to end

**Files:**
- Modify if needed: `frontend/src/components/EvidencePanel.tsx`
- Modify if needed: `frontend/src/components/PdfEvidenceViewer.tsx`

- [ ] **Step 1: Run `pnpm --prefix frontend test`**
- [ ] **Step 2: Run `pnpm --prefix frontend lint`**
- [ ] **Step 3: Fix regressions**
