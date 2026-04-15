# 模块清单

以下清单按“对本次 feature 的相关度”组织，覆盖本项目中需要理解或可能改动的主要模块。

复杂度评级约定：

- `Low`：职责单一，变更面窄
- `Medium`：有状态或协议转换，需要同步多个调用点
- `High`：跨层数据边界、协议兼容或检索/生成核心逻辑

规模评级约定：

- `S`：小
- `M`：中
- `L`：大

## 前端模块

| 模块 | 主要文件 | 职责 | 依赖 | 规模 | 复杂度 | 与本 feature 的关系 |
| --- | --- | --- | --- | --- | --- | --- |
| 应用装配 | `frontend/src/main.tsx`, `frontend/src/App.tsx` | 装配三栏工作台和全局状态源 | React, `useEuroQaDemo` | S | Low | 需要接入新增导出入口或透传新状态 |
| 工作台状态 | `frontend/src/hooks/useEuroQaDemo.ts` | 管理提问、流式响应、引用状态、本地持久化输入 | `lib/api`, `lib/session`, `lib/types` | L | High | 单条复制和整会话导出的数据来源核心模块 |
| 主回答区 | `frontend/src/components/MainWorkspace.tsx` | 渲染问答消息、Markdown、引用来源、reasoning 折叠区 | `lib/citations`, `lib/markdown`, `lib/api` | L | High | 单条复制按钮最可能落在这里 |
| 顶栏 | `frontend/src/components/TopBar.tsx` | 状态显示、LLM 设置入口 | `LlmSettingsPanel` | S | Low | 整会话导出入口的候选位置 |
| 侧栏 | `frontend/src/components/Sidebar.tsx` | 新建会话、最近提问、文档切换、热门问题 | `useEuroQaDemo` 输出 | M | Low | 也可放会话级导出入口 |
| 证据面板 | `frontend/src/components/EvidencePanel.tsx`, `PdfEvidenceViewer.tsx` | 展示被选中的 citation 原文、PDF、高亮、译文 | `buildDocumentFileUrl`, `pdfLocator` | M | Medium | 提供来源查看能力，但不是复制数据源本体 |
| API 客户端 | `frontend/src/lib/api.ts` | REST/SSE 封装、解析 `done` 事件、构造引用记录 | Fetch, `types.ts` | M | High | 必须扩展新响应字段，保证流式/非流式一致 |
| 数据模型 | `frontend/src/lib/types.ts` | 定义 `ChatTurn`、`Source`、请求响应类型 | 前端全局依赖 | M | High | 需要新增“检索上下文快照”类型 |
| 本地持久化 | `frontend/src/lib/session.ts` | `ChatTurn` 与会话状态序列化到 localStorage | `types.ts` | M | High | 导出整会话依赖其数据完整性 |
| Markdown 与引用辅助 | `frontend/src/lib/markdown.ts`, `citations.ts`, `inlineReferences.ts` | Markdown 渲染、安全 URL 处理、正文 citation 联动 | `react-markdown` | M | Medium | 回答正文复制时需要保留 raw markdown，不应从渲染后 DOM 反取 |

## 后端模块

| 模块 | 主要文件 | 职责 | 依赖 | 规模 | 复杂度 | 与本 feature 的关系 |
| --- | --- | --- | --- | --- | --- | --- |
| 服务入口 | `server/main.py`, `server/api/v1/router.py` | FastAPI 装配、路由注册 | FastAPI | S | Low | 直接改动概率低 |
| 问答接口 | `server/api/v1/query.py` | 组织 query/query-stream 请求链路 | `query_understanding`, `retrieval`, `generation` | M | High | 需要透传新增上下文字段 |
| 查询理解 | `server/core/query_understanding.py` | 问题改写、意图识别、过滤条件生成 | glossary, LLM config | M | Medium | 间接相关，不太需要改 |
| 混合检索 | `server/core/retrieval.py` | 向量检索、BM25、重排、父块召回 | Milvus, ES, rerank client | L | High | 负责产出完整 `chunks + parent_chunks`，是“全部召回上下文”的唯一真实来源 |
| 回答生成 | `server/core/generation.py` | prompt 拼接、LLM 调用、SSE token 流、source 构造 | OpenAI client, schemas | L | High | 需要定义并构建可复制的上下文快照 |
| 会话管理 | `server/core/conversation.py` | 最近几轮问答缓存 | `cachetools` | S | Medium | 当前只存 `question/answer`，不够支撑服务端重构导出 |
| 依赖注入 | `server/deps.py` | 构造配置、retriever、conversation manager | `config.py` | S | Low | 无直接改动预期 |
| 响应模型 | `server/models/schemas.py` | `QueryResponse`, `Source`, `Chunk` 等 schema | Pydantic | M | High | 必须定义新的导出/复制上下文字段 |
| 文档与来源接口 | `server/api/v1/documents.py`, `server/api/v1/sources.py` | 提供 PDF 文件和按需 source 翻译 | parsed/pdf data | M | Medium | 间接相关，可能帮助整会话导出的元信息补充 |

## 支撑模块

| 模块 | 主要文件 | 职责 | 依赖 | 规模 | 复杂度 | 与本 feature 的关系 |
| --- | --- | --- | --- | --- | --- | --- |
| 共享客户端 | `shared/model_clients.py`, `shared/elasticsearch_client.py` | 构造 embedding/rerank/ES 客户端 | 外部服务 | M | Medium | 无直接改动预期 |
| 数据构建 pipeline | `pipeline/*.py` | PDF 解析、chunk 构建、元数据生成 | MinerU, ES, Milvus | L | High | 本次不改，但决定 `Chunk` 元数据质量 |

## 测试模块

| 模块 | 主要文件 | 职责 | 规模 | 复杂度 | 与本 feature 的关系 |
| --- | --- | --- | --- | --- | --- |
| 后端 API/生成测试 | `tests/server/test_api.py`, `tests/server/test_generation.py` | 验证 query/query-stream 返回结构和生成层逻辑 | M | Medium | 需要增加新字段和兼容性测试 |
| 前端 API/会话测试 | `frontend/src/lib/api.test.ts`, `frontend/src/lib/session.test.ts` | 验证 SSE 解析与本地持久化 | M | Medium | 需要覆盖新字段的解析和存储 |
| 现有引用渲染测试 | `frontend/src/lib/citations.test.ts`, `markdown.test.ts` | 保证 Markdown/citation 行为稳定 | S | Low | 间接防回归 |

## 关键模块结论

本次 feature 的核心改动面集中在 6 个文件族：

1. `server/models/schemas.py`
2. `server/core/generation.py`
3. `server/api/v1/query.py`
4. `frontend/src/lib/types.ts`
5. `frontend/src/hooks/useEuroQaDemo.ts`
6. `frontend/src/components/MainWorkspace.tsx`

如果要支持“整会话导出”，通常还需要补充：

7. `frontend/src/lib/session.ts`
8. `frontend/src/components/TopBar.tsx` 或 `frontend/src/components/Sidebar.tsx`
9. 一个新的前端导出/序列化辅助模块，例如 `frontend/src/lib/export.ts`

## 现有能力与缺口归纳

### 现有能力

- 回答原始 Markdown 文本已保存在 `ChatTurn.answer`
- 会话消息列表已在前端完整维护并可持久化到 localStorage
- `sources` 已能表达最终展示出来的引用来源

### 缺口

- `ChatTurn` 没有“完整检索上下文”字段
- API schema 没有“retrieval snapshot”字段
- 会话导出没有统一序列化层
- UI 没有复制/导出控件

因此，本次 feature 是一次“跨前后端协议扩展 + 前端交互补齐”的增量开发，而不是纯 UI 修改。
