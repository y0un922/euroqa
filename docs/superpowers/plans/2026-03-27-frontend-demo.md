# Euro_QA Frontend Demo Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 基于现有 `prototype/` 视觉方向，创建一个真实连接 FastAPI 后端的 `frontend/` 演示前端。

**Architecture:** 新前端沿用三栏工作台结构，使用 React + Vite + TypeScript。数据层直接对接 `/api/v1/query`, `/api/v1/query/stream`, `/api/v1/documents`, `/api/v1/glossary`, `/api/v1/suggest`, `/api/v1/documents/{id}/page/{page}`，其中会话历史在前端本地维护，流式回答通过 `fetch` + SSE 文本解析实现。

**Tech Stack:** React 19, TypeScript, Vite, Tailwind CSS v4, lucide-react, motion, tsx

---

### Task 1: 建立前端工程骨架

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/tsconfig.json`
- Create: `frontend/vite.config.ts`
- Create: `frontend/index.html`
- Create: `frontend/src/main.tsx`
- Create: `frontend/src/index.css`

- [ ] **Step 1: 复制并精简 `prototype` 的工程配置**
- [ ] **Step 2: 增加测试脚本，预留 `tsx --test` 用于纯 TS 单元测试**
- [ ] **Step 3: 运行 `pnpm install` 安装依赖**
- [ ] **Step 4: 运行 `pnpm --dir frontend lint` 验证工程可编译**

### Task 2: 写流式解析与来源映射的 failing tests

**Files:**
- Create: `frontend/src/lib/api.test.ts`
- Create: `frontend/src/lib/api.ts`

- [ ] **Step 1: 先为 SSE 文本解析写 failing test**
- [ ] **Step 2: 运行 `pnpm --dir frontend test` 确认测试正确失败**
- [ ] **Step 3: 再为来源数据映射与引用 ID 生成写 failing test**
- [ ] **Step 4: 再次运行测试，确认仍为红灯**

### Task 3: 实现真实 API 客户端

**Files:**
- Modify: `frontend/src/lib/api.ts`
- Create: `frontend/src/lib/types.ts`

- [ ] **Step 1: 实现基础 REST 请求封装**
- [ ] **Step 2: 实现 `query`, `queryStream`, `documents`, `glossary`, `suggest` 客户端**
- [ ] **Step 3: 实现 SSE `event/data` 文本解析**
- [ ] **Step 4: 运行 `pnpm --dir frontend test` 验证变绿**

### Task 4: 实现工作台状态与布局

**Files:**
- Create: `frontend/src/App.tsx`
- Create: `frontend/src/hooks/useEuroQaDemo.ts`
- Create: `frontend/src/components/TopBar.tsx`
- Create: `frontend/src/components/Sidebar.tsx`
- Create: `frontend/src/components/MainWorkspace.tsx`
- Create: `frontend/src/components/EvidencePanel.tsx`

- [ ] **Step 1: 建立全局页面状态，管理问题、回答、来源、当前文档、最近提问**
- [ ] **Step 2: 接入 `suggest` 与 `documents` 初始化加载**
- [ ] **Step 3: 接入真实提问与流式回答**
- [ ] **Step 4: 实现来源点击与右侧证据联动**
- [ ] **Step 5: 实现 PDF 页面预览图片加载**

### Task 5: 视觉收尾与可用性修正

**Files:**
- Modify: `frontend/src/index.css`
- Modify: `frontend/src/components/*.tsx`

- [ ] **Step 1: 删除所有明显假数据文案与假指标**
- [ ] **Step 2: 保留原型视觉语言，但改为真实数据态、空态、加载态、错误态**
- [ ] **Step 3: 修正移动端与窄屏下的布局退化**

### Task 6: 最终验证

**Files:**
- Verify only

- [ ] **Step 1: 运行 `pnpm --dir frontend test`**
- [ ] **Step 2: 运行 `pnpm --dir frontend build`**
- [ ] **Step 3: 如有需要，运行 `pnpm --dir frontend dev --host 127.0.0.1 --port 4173` 做人工验证**
