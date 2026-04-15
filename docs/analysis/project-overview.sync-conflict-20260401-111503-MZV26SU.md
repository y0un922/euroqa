# Euro_QA Project Overview

## 本次任务上下文

目标 feature：

- 为单条 LLM 回复增加复制按钮
- 支持导出/复制整个会话
- 输出格式为 Markdown
- 内容必须包含回答原文，以及该轮问答检索召回的全部上下文
- 优先级以数据准确性为主

## 当前系统形态

Euro_QA 当前是一个前后端分离的检索问答演示系统：

- 前端：React 19 + TypeScript + Vite
- 后端：FastAPI + Pydantic + SSE 流式响应
- 检索：Milvus 向量检索 + Elasticsearch BM25 + rerank
- 文档来源：`pipeline/` 生成的 chunk 数据、父 chunk、PDF 定位元数据

核心运行入口：

- 前端入口：`frontend/src/main.tsx` -> `frontend/src/App.tsx`
- 前端状态中心：`frontend/src/hooks/useEuroQaDemo.ts`
- 后端入口：`server/main.py`
- 问答 API：`server/api/v1/query.py`
- 检索核心：`server/core/retrieval.py`
- 生成核心：`server/core/generation.py`

## 构建与运行

前端：

```bash
cd frontend
pnpm install
pnpm dev
```

相关脚本：

- `pnpm dev`
- `pnpm build`
- `pnpm lint`
- `pnpm test`

后端：

```bash
uv run uvicorn server.main:app --reload --host 0.0.0.0 --port 8080
```

项目依赖由 `pyproject.toml` 管理，检索依赖包括 Milvus 与 Elasticsearch。

## 与本次 feature 直接相关的运行时链路

### 1. 前端发起提问

`frontend/src/hooks/useEuroQaDemo.ts`

- `askQuestion()` 创建一个新的 `ChatTurn`
- 先以 `status: "streaming"` 追加到 `messages`
- 优先调用 `queryStream()`
- SSE 失败时回退到 `query()`

### 2. 前端请求层

`frontend/src/lib/api.ts`

- `query()` 调用 `/api/v1/query`
- `queryStream()` 调用 `/api/v1/query/stream`
- SSE 只处理三类事件：
  - `reasoning`
  - `chunk`
  - `done`

当前 `done` payload 只包含：

- `sources`
- `related_refs`
- `confidence`

不包含完整检索上下文。

### 3. 后端问答编排

`server/api/v1/query.py`

非流式链路：

1. `analyze_query()`
2. `retriever.retrieve()`
3. `generate_answer()`
4. 返回 `QueryResponse`
5. `ConversationManager.add_turn()` 只写入 `question` 和 `answer`

流式链路：

1. `analyze_query()`
2. `retriever.retrieve()`
3. `generate_answer_stream()`
4. 边产出 Markdown 边发送 SSE `chunk`
5. `done` 时只回传 `sources / related_refs / confidence`
6. `ConversationManager.add_turn()` 同样只写入 `question` 和 `answer`

### 4. 检索数据生成位置

`server/core/retrieval.py`

- `retrieve()` 返回 `RetrievalResult`
- 结构包含：
  - `chunks`
  - `parent_chunks`
  - `scores`

这些就是回答生成时真正使用的召回上下文。

### 5. 回答 prompt 组装位置

`server/core/generation.py`

- `build_prompt()` 会把以下内容拼进发送给 LLM 的 prompt：
  - 主检索 `chunks`
  - 章节级 `parent_chunks`
  - glossary terms
  - conversation history

这说明“检索召回的全部上下文”当前只存在于后端生成阶段，并没有透传给前端。

### 6. 前端消息渲染与本地持久化

`frontend/src/components/MainWorkspace.tsx`

- 用 `message.answer` 渲染 Markdown
- 用 `message.sources` 渲染“引用来源”

`frontend/src/lib/session.ts`

- 将整个 `messages: ChatTurn[]` 落到 localStorage
- 当前 `ChatTurn` 仅持久化：
  - `question`
  - `answer`
  - `reasoning`
  - `status`
  - `confidence`
  - `sources`
  - `relatedRefs`
  - `degraded`
  - `conversationId`
  - `errorMessage`

没有检索上下文字段。

## 当前数据保真度结论

已经能准确拿到并持久化的数据：

- 单条回答 Markdown 原文：`ChatTurn.answer`
- 深度思考内容：`ChatTurn.reasoning`
- 引用来源元数据与原文片段：`ChatTurn.sources`
- 整个会话的消息序列：`messages`

当前不能在前端准确复原的数据：

- 本轮完整召回的 `chunks`
- 本轮完整召回的 `parent_chunks`
- 本轮 rerank 分数
- 回答生成时真正发给 LLM 的完整 prompt

结论：如果要满足“复制本轮检索召回的全部上下文”，必须扩展后端响应协议和前端消息模型。

## 已观察到的实现边界

- 当前没有任何现成的复制/导出实现
- 整会话导出可以复用前端本地 `messages` 状态完成
- 单条复制与整会话导出都应由前端主导
- 检索上下文如果要进入导出内容，最稳妥的方式是在后端生成结束时一起返回，并写入 `ChatTurn`

## 对本次 feature 的初步影响判断

影响范围覆盖前后端：

- 前端 UI：新增单条回复复制入口、整会话导出入口
- 前端状态：扩展 `ChatTurn` 与 session 持久化结构
- 前端 API：扩展 `QueryResponse` 与 `StreamDonePayload`
- 后端协议：将检索上下文并入 `/query` 和 `/query/stream` 的完成态返回
- 测试：前端 API/session 测试、后端 generation/API 测试都需要补齐

本任务不是单点 UI 改动，而是一个跨前后端的数据链路 feature。
