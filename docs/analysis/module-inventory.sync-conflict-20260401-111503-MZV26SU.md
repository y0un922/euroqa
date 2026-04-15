# Euro_QA Module Inventory

## 盘点范围说明

本清单聚焦本次 feature 直接相关的模块，而不是对整个仓库做逐文件注释式罗列。复杂度评级基于文件规模、状态集中度、跨模块耦合度和对本次 feature 的影响面。

## 核心模块总览

| 模块 | 关键文件 | 责任 | 主要依赖 | 规模/热点 | 复杂度 |
| --- | --- | --- | --- | --- | --- |
| 前端应用壳层 | `frontend/src/App.tsx` | 组装三栏工作台，向组件透传 demo 状态 | `useEuroQaDemo`, `MainWorkspace`, `EvidencePanel`, `Sidebar`, `TopBar` | 小 | 低 |
| 前端会话状态中心 | `frontend/src/hooks/useEuroQaDemo.ts` | 提问、流式拼接、fallback、引用激活、本地持久化 | `lib/api`, `lib/session`, `types` | 625 行，核心状态汇聚点 | 高 |
| 前端主回答区 | `frontend/src/components/MainWorkspace.tsx` | 渲染问题、LLM 回答、引用来源、深度思考 | `ReactMarkdown`, `citations`, `inlineReferences` | 581 行，UI 复杂度高 | 高 |
| 前端证据面板 | `frontend/src/components/EvidencePanel.tsx` | 展示当前引用的 PDF 定位、译文与元数据 | `PdfEvidenceViewer`, `markdown` | 229 行 | 中 |
| 前端 API 适配层 | `frontend/src/lib/api.ts` | REST/SSE 调用、SSE 解析、source 到 reference 的映射 | 浏览器 `fetch`, `types` | 257 行 | 中 |
| 前端会话持久化 | `frontend/src/lib/session.ts` | `ChatTurn` 的 localStorage 序列化/反序列化与迁移 | `types` | 272 行，迁移逻辑较多 | 高 |
| 前端类型定义 | `frontend/src/lib/types.ts` | 前端请求、响应、消息、source 的共享类型 | 全部前端业务模块 | 129 行 | 中 |
| 后端问答编排层 | `server/api/v1/query.py` | 串联 query understanding、retrieval、generation、SSE | `retrieval`, `generation`, `conversation` | 113 行，协议边界关键点 | 高 |
| 后端生成层 | `server/core/generation.py` | prompt 拼装、LLM 调用、source 构造、流式 done 元数据 | `ServerConfig`, `schemas` | 728 行，全链路关键热点 | 高 |
| 后端检索层 | `server/core/retrieval.py` | 混合检索、融合、rerank、父块补全 | Milvus, ES, rerank client | 364 行 | 高 |
| 后端会话状态 | `server/core/conversation.py` | 内存 TTL 会话，仅保存最近问答历史 | `cachetools` | 小，但字段能力弱 | 中 |
| 后端协议模型 | `server/models/schemas.py` | `QueryResponse`, `Source`, `Chunk`, `QueryRequest` 等 | Pydantic | 145 行 | 高 |
| 服务配置/依赖 | `server/config.py`, `server/deps.py`, `server/main.py` | DI、配置、应用生命周期 | FastAPI, env config | 中 | 中 |
| 文档解析与索引流水线 | `pipeline/*` | 生成 chunk、parent chunk、bbox、content_list | PDF 解析、索引写入 | 大，但本次只读依赖 | 中 |
| 调试与观察性 | `server/api/debug_pipeline.py`, `shared/pipeline_debug.py` | 查看 pipeline artifact | debug store | 与本 feature 直接关系低 | 低 |

## 与 feature 最强相关的数据模型

### 前端 `ChatTurn`

文件：

- `frontend/src/lib/types.ts`
- `frontend/src/lib/session.ts`

当前字段：

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

结论：

- 足以支持“复制单条回答原文”
- 不足以支持“复制该轮完整检索召回上下文”

### 后端 `QueryResponse`

文件：

- `server/models/schemas.py`

当前字段：

- `answer`
- `sources`
- `related_refs`
- `confidence`
- `conversation_id`
- `degraded`

结论：

- 当前 API 契约没有检索上下文字段
- 前端无法从响应中获得完整 `chunks / parent_chunks`

### 后端 `RetrievalResult`

文件：

- `server/core/retrieval.py`

当前字段：

- `chunks`
- `parent_chunks`
- `scores`

结论：

- 这是最接近“真实检索上下文”的内部结构
- 但它停留在后端内部，没有进入 API 响应

## 功能链路中的关键文件

### 单条问答与复制能力最相关

- `frontend/src/hooks/useEuroQaDemo.ts`
  - 负责把后端响应转成前端 `ChatTurn`
- `frontend/src/components/MainWorkspace.tsx`
  - 单条回复按钮最自然的挂载点
- `frontend/src/lib/session.ts`
  - 会话导出能力最终依赖本地持久化结构
- `frontend/src/lib/types.ts`
  - 需要新增消息级导出/检索上下文字段
- `frontend/src/lib/api.ts`
  - 需要扩展非流式和 SSE done payload 类型

### 后端协议最相关

- `server/api/v1/query.py`
  - 决定 `/query` 与 `/query/stream` 最终返回什么
- `server/core/generation.py`
  - 当前最适合把检索上下文转换为前端可消费的导出结构
- `server/models/schemas.py`
  - 需要正式定义新增响应字段

## 当前测试覆盖情况

与本 feature 直接相关的已有测试：

- `tests/server/test_generation.py`
  - 覆盖 source 构造、prompt、stream 行为
- `tests/server/test_api.py`
  - 覆盖 query/query-stream 契约与 override 行为
- `frontend/src/lib/api.test.ts`
  - 覆盖 SSE 解析和 API helper
- `frontend/src/lib/session.test.ts`
  - 覆盖消息持久化与旧数据迁移

结论：

- 后端协议扩展后，这四组测试都需要同步更新
- 如果新增 Markdown 导出拼装函数，前端应增加独立纯函数测试，而不是只靠组件测试

## 额外观察

- 仓库当前是脏工作区，且有不少未提交前端文件
- 存在同步冲突遗留文件：
  - `frontend/src/components/PdfEvidenceViewer.sync-conflict-20260331-154406-MZV26SU.tsx`
  - `frontend/src/lib/api.sync-conflict-20260327-143814-MZV26SU.ts`

这意味着后续实现阶段需要严格避免误改无关文件，并优先在现行主文件上增量修改。
