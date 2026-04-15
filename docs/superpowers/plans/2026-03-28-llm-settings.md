# LLM Settings Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 Euro_QA Demo 增加前后端联动的 LLM 设置功能，让 `api_key`、`base_url`、`model`、`enable_thinking` 可以从前端配置并在下一次问答时立即生效。

**Architecture:** 采用“前端本地持久化 + 请求级运行时覆盖”的方式。前端通过顶部栏设置面板管理本地 `llm` 覆盖项，并在 `/query` 与 `/query/stream` 请求中透传；后端提供只读默认值接口，并在进入问答链路前将请求覆盖项与 `ServerConfig` 合成为本次请求实际使用的运行时配置。

**Tech Stack:** FastAPI, Pydantic, React 19, TypeScript, Vite, Tailwind CSS v4, tsx

---

### Task 1: 扩展后端请求模型与默认值接口

**Files:**
- Modify: `server/models/schemas.py`
- Create or Modify: `server/api/v1/settings.py`
- Modify: `server/api/v1/router.py`
- Test: `tests/server/test_api.py`

- [ ] **Step 1: 先为 `GET /api/v1/settings/llm` 写测试，要求返回 `base_url`、`model`、`enable_thinking`、`api_key_configured`，且不暴露明文 key**
- [ ] **Step 2: 为 `QueryRequest` 的 `llm` 覆盖对象写测试样例，确认可选字段能被 FastAPI 正常接收**
- [ ] **Step 3: 实现 `LlmSettingsOverride` / `LlmSettingsResponse` 等后端 schema**
- [ ] **Step 4: 实现设置默认值接口并注册到 v1 router**
- [ ] **Step 5: 运行 `uv run pytest tests/server/test_api.py -q`，确认新增测试通过**

### Task 2: 实现后端运行时配置覆盖链路

**Files:**
- Modify: `server/config.py`
- Modify: `server/api/v1/query.py`
- Modify: `server/core/query_understanding.py`
- Modify: `server/core/generation.py`
- Test: `tests/server/test_api.py`
- Test: `tests/server/test_generation.py`

- [ ] **Step 1: 先补 failing tests，验证 `/query` 和 `/query/stream` 在携带 `llm` 覆盖项时会把覆盖后的配置传给查询理解与生成层**
- [ ] **Step 2: 实现运行时配置合成函数，规则为“非空覆盖值优先，空字符串回退默认值”**
- [ ] **Step 3: 在 `/query` 与 `/query/stream` 入口接入运行时配置，并透传到 `analyze_query`、`generate_answer`、`generate_answer_stream`**
- [ ] **Step 4: 保持检索依赖不变，避免将本次改造扩散到 embedding / rerank 链路**
- [ ] **Step 5: 运行 `uv run pytest tests/server/test_api.py tests/server/test_generation.py -q`，确认链路测试通过**

### Task 3: 扩展前端类型、API 客户端与本地持久化

**Files:**
- Modify: `frontend/src/lib/types.ts`
- Modify: `frontend/src/lib/api.ts`
- Modify: `frontend/src/lib/session.ts`
- Test: `frontend/src/lib/api.test.ts`
- Test: `frontend/src/lib/session.test.ts`

- [ ] **Step 1: 先为 `query()` / `queryStream()` 携带 `llm` 字段写 failing tests**
- [ ] **Step 2: 再为 session 恢复与保存 `llmSettings` 写 failing tests，包含旧数据迁移场景**
- [ ] **Step 3: 实现前端 `LlmSettings` / `LlmSettingsOverrides` / `LlmSettingsDefaults` 类型**
- [ ] **Step 4: 扩展 API 客户端，新增 `getLlmSettings()` 并让问答请求支持 `llm` 透传**
- [ ] **Step 5: 扩展 session 持久化与恢复逻辑**
- [ ] **Step 6: 运行 `pnpm --dir frontend test`，确认前端基础测试通过**

### Task 4: 实现设置状态管理与顶部栏设置面板

**Files:**
- Modify: `frontend/src/hooks/useEuroQaDemo.ts`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/TopBar.tsx`
- Create: `frontend/src/components/LlmSettingsPanel.tsx`

- [ ] **Step 1: 在 `useEuroQaDemo` 中加载服务端默认设置，并管理本地覆盖值、保存动作、恢复默认动作**
- [ ] **Step 2: 让提问链路在 `query()` / `queryStream()` 时自动附带当前有效 LLM 设置**
- [ ] **Step 3: 实现 `LlmSettingsPanel`，包含字段编辑、保存、恢复默认和服务端默认值提示**
- [ ] **Step 4: 在 `TopBar` 中增加设置按钮与面板开关，不改变现有三栏工作台主结构**
- [ ] **Step 5: 手工检查设置更新后不会打断现有消息、来源面板与深度思考面板**

### Task 5: 最终验证与收尾

**Files:**
- Verify only

- [ ] **Step 1: 运行 `uv run pytest tests/server/test_api.py tests/server/test_generation.py -q`**
- [ ] **Step 2: 运行 `pnpm --dir frontend test`**
- [ ] **Step 3: 运行 `pnpm --dir frontend lint`**
- [ ] **Step 4: 如有需要，运行 `pnpm --dir frontend dev --host 127.0.0.1 --port 4173` 做人工验证**
- [ ] **Step 5: 更新相关文档与知识库记录，确保本次 LLM 设置功能可追溯**
