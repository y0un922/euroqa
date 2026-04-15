# 项目概览

## 任务背景

本轮目标是在现有 Euro_QA 项目中增加一个“复制/导出 LLM 回复”的功能，满足以下要求：

- 支持复制单条 LLM 回复
- 支持导出整个会话
- 输出格式为 Markdown
- 内容必须包含：
  - LLM 回复的原始 Markdown 文本
  - 本轮检索召回的全部上下文，而不是仅最终展示的引用来源

当前仓库不存在 `docs/progress/MASTER.md`，说明这是一次新的规范驱动准备流程，而不是续做任务。

## 架构摘要

项目是一个前后端分离的检索问答系统，整体分为四层：

1. `pipeline/`
   负责将 Eurocode PDF 解析、切块、索引到 Elasticsearch 和 Milvus，并为检索阶段准备 `Chunk` 元数据。

2. `server/`
   提供 FastAPI API，负责查询理解、混合检索、LLM 生成、流式 SSE 返回和会话管理。

3. `frontend/`
   基于 React 19 + Vite 的演示工作台，负责发起提问、消费 SSE、渲染 Markdown 回答、展示引用来源和右侧证据面板。

4. `shared/`
   存放后端与 pipeline 共用的客户端构建逻辑，例如 embedding/rerank/Elasticsearch 连接。

## 运行入口与构建方式

### 前端

- HTML 入口：`frontend/index.html`
- React 启动入口：`frontend/src/main.tsx`
- 应用根组件：`frontend/src/App.tsx`
- 开发命令：
  - `cd frontend && pnpm install`
  - `pnpm dev`
- 构建命令：
  - `pnpm build`
- 校验命令：
  - `pnpm lint`
  - `pnpm test`

### 后端

- FastAPI 入口：`server/main.py`
- v1 路由聚合：`server/api/v1/router.py`
- 关键问答接口：
  - `POST /api/v1/query`
  - `POST /api/v1/query/stream`
- 本地启动方式：
  - 典型为 `uvicorn server.main:app --reload --port 8080`

### 数据与依赖

- Python 依赖：`pyproject.toml`
- 前端依赖与脚本：`frontend/package.json`
- 基础服务：`docker-compose.yml`
  - Milvus
  - Elasticsearch 相关依赖

## 与本 feature 相关的核心请求链路

### 1. 前端提问与本地状态

`frontend/src/hooks/useEuroQaDemo.ts`

- 在 `askQuestion()` 中创建一个新的 `ChatTurn`
- 流式时通过 `queryStream()` 累积：
  - `answer`
  - `reasoning`
  - `sources`
  - `relatedRefs`
  - `confidence`
- 非流式 fallback 时通过 `query()` 一次性写回同样的数据
- 通过 `savePersistedDemoSession()` 持久化到浏览器 localStorage

### 2. 前端回答渲染

`frontend/src/components/MainWorkspace.tsx`

- 将 `message.answer` 作为 Markdown 渲染
- 通过 `linkifyReferenceCitations()` 将正文中的规范引用改写为内部引用
- 根据 `message.sources` 构造引用来源按钮
- 当前没有复制按钮，也没有整会话导出入口

### 3. 后端查询与检索

`server/api/v1/query.py`

- 调用 `analyze_query()` 生成改写查询和过滤条件
- 调用 `HybridRetriever.retrieve()` 得到：
  - `chunks`
  - `parent_chunks`
  - `scores`
- 调用 `generate_answer()` 或 `generate_answer_stream()`

### 4. 后端生成与返回

`server/core/generation.py`

- `build_prompt()` 会把以下内容拼进 LLM prompt：
  - 主检索 `chunks`
  - 截断后的 `parent_chunks`
  - 最近两轮 `conversation_history`
  - glossary 对照
- `_build_sources_from_chunks()` 只从最终 `chunks` 构造 `sources`
- `generate_answer_stream()` 的 `done` 事件只返回：
  - `sources`
  - `related_refs`
  - `confidence`
- `generate_answer()` 的 `QueryResponse` 同样只返回结构化 `sources`

## 当前数据保留能力评估

### 已经具备的数据

- 单条消息的原始 Markdown 回答：
  - 前端 `ChatTurn.answer`
- 推理过程：
  - 前端 `ChatTurn.reasoning`
- 已返回的结构化来源：
  - 前端 `ChatTurn.sources`
- 关联引用：
  - 前端 `ChatTurn.relatedRefs`
- 会话级本地持久化：
  - `frontend/src/lib/session.ts`

### 当前缺失的数据

为了满足“复制本轮检索召回的全部上下文”的目标，当前缺少以下关键能力：

- API 不返回完整检索上下文
  - `RetrievalResult.chunks` 和 `parent_chunks` 只在后端内存中存在
- 前端 `ChatTurn` 不保存检索快照
- localStorage 中也没有保存“当时用于生成答案的检索上下文”
- 后端会话管理只保存最近几轮 `question/answer`，不保存 `sources`、`chunks` 或 `parent_chunks`

结论：当前系统只能可靠复制“回答原文 + 已返回 sources”，不能准确复制“本轮全部召回上下文”。

## 与本 feature 直接相关的候选改动面

### 前端

- `frontend/src/components/MainWorkspace.tsx`
  - 单条回复复制按钮
  - 可能也是整会话导出入口的主要消费方
- `frontend/src/hooks/useEuroQaDemo.ts`
  - 扩展每条消息的数据结构
- `frontend/src/lib/types.ts`
  - 为消息和 API payload 增加检索上下文字段
- `frontend/src/lib/session.ts`
  - 让新增字段进入 localStorage 持久化
- `frontend/src/components/TopBar.tsx` 或 `Sidebar.tsx`
  - 增加“导出整个会话”入口更合理

### 后端

- `server/models/schemas.py`
  - 扩展响应模型，承载完整检索上下文快照
- `server/core/generation.py`
  - 定义“可复制/可导出的检索上下文”结构，并在流式和非流式路径统一构造
- `server/api/v1/query.py`
  - 确保 `/query` 与 `/query/stream` 的新字段行为一致

### 测试

- `tests/server/test_api.py`
- `tests/server/test_generation.py`
- `frontend/src/lib/api.test.ts`
- `frontend/src/lib/session.test.ts`

## 初步实现方向判断

从准确性优先的角度看，最稳妥的方案不是在前端“重新推断”上下文，而是：

1. 后端把本轮用于生成回答的检索快照显式返回给前端
2. 前端把这份快照与 `answer` 一起绑定到 `ChatTurn`
3. 单条复制和整会话导出统一复用同一个 Markdown 序列化器

这样可以保证复制结果与实际生成时使用的数据一致，并避免后续从 `sources` 反推“全部召回上下文”的信息损失。
