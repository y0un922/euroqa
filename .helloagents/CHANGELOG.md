# CHANGELOG

## [0.1.30] - 2026-06-01

### 新增
- **[server.agents.tool_progress / server.agents.tools.retrieve / server.core.query_understanding / server.core.retrieval / tests]**: 实现 Tool Phase 1 后端基础设施，新增可复用 tool 子步骤进度 emitter，`retrieve` 现在可上报 query understanding、hybrid search 及检索内部子步骤；query expansion 同次 LLM 调用接入最近 3 轮对话历史并输出 `rewritten_question`，用于多轮追问指代消解 — by Codex
  - 类型: 标准流程（全自动执行）
  - 文件: server/agents/tool_progress.py; server/agents/deps.py; server/agents/qa_agent.py; server/agents/tools/retrieve.py; server/core/query_understanding.py; server/core/retrieval.py; tests/server/agents/test_tool_progress.py; tests/server/agents/test_retrieve_sub_steps.py; tests/server/core/test_query_rewrite.py
- **[server.api.v1.query / server.api.v1._progress / frontend.api / frontend.useEuroQaDemo / tests]**: 实现 Tool Phase 2 SSE 贯通，流式问答现在将 tool 子步骤通过 `tool_progress` SSE 实时输出，前端 `queryStream` 增加 `onToolProgress` 回调并把子步骤追加到当前 `ChatTurn.toolSubSteps`，不影响既有 progress/chunk/done/commentary 事件 — by Codex
  - 类型: 标准流程（全自动执行）
  - 文件: server/agents/orchestrator.py; server/api/v1/_progress.py; server/api/v1/query.py; frontend/src/lib/types.ts; frontend/src/lib/api.ts; frontend/src/hooks/useEuroQaDemo.ts; frontend/src/lib/api.test.ts; tests/server/test_api.py

## [0.1.29] - 2026-05-31

### 修复
- **[server.core.conversation / server.api.v1.sessions / frontend.session / tests]**: 会话恢复改为以 Redis 为准，新增 `GET /api/v1/sessions/{session_id}` 将 Redis `context:{sessionId}` role 消息还原为前端 `ChatTurn`；前端启动时用本地轻量 session 指针从后端恢复对话，`localStorage` 不再保存完整 `messages/history/retrievalContext`，避免回答完成后引用和证据上下文写爆浏览器配额导致白屏 — by Codex
  - 类型: 标准流程（Trellis 创建失败后降级执行）
  - 文件: server/core/conversation.py; server/api/v1/sessions.py; server/api/v1/router.py; server/models/schemas.py; frontend/src/lib/api.ts; frontend/src/lib/session.ts; frontend/src/lib/types.ts; frontend/src/hooks/useEuroQaDemo.ts; tests/server/test_api.py; frontend/src/lib/api.test.ts; frontend/src/lib/session.test.ts
- **[frontend.lib.session / frontend.hooks.useEuroQaDemo / frontend.components.MainWorkspace / tests]**: 修复流式回答过程中前端可能白屏与刷新后回答状态不一致的问题；会话持久化写入失败现在被安全吞掉并返回 `false`，流式生成期间改为 1s 防抖写入 localStorage，刷新恢复未完成的 streaming turn 时标记为 `error` 并保留已生成正文与中断提示，避免被当作完整回答导出；回答 Markdown 渲染异常时降级为纯文本，避免单条流式内容拖垮整个工作台 — by Codex
  - 类型: 简化流程（Trellis 创建失败后降级执行）
  - 文件: frontend/src/lib/session.ts; frontend/src/hooks/useEuroQaDemo.ts; frontend/src/components/MainWorkspace.tsx; frontend/src/lib/session.test.ts; frontend/src/components/MainWorkspace.test.ts
- **[server.agents / server.api.v1.query / tests]**: 提升 agent 问答链路健壮性，默认 agent 超时从 30s 调整为 60s，单次 agent turn 上限降为 3；prompt 增加 grounded 后禁止重复 retrieve、单问题最多 retrieve 2 次的硬约束；agent 超时但已检索到证据时保留 evidence bundle 继续走 RAG 生成，非流式 `/query` 捕获 QA 域错误并返回 `degraded=true` 响应，避免穿透为 500 — by Codex
  - 类型: 标准流程（Trellis 创建失败后降级执行）
  - 文件: server/config.py; server/agents/qa_agent.py; server/agents/orchestrator.py; server/api/v1/query.py; tests/server/agents/test_qa_agent.py; tests/server/api/v1/test_query_agent_concurrency.py; tests/server/test_api.py
- **[server.agents.tools.retrieve / server.core.retrieval / tests]**: 为 agent `retrieve` 工具新增 `top_k` 参数，由 LLM 按问题复杂度选择 3-12 条证据；工具端会 clamp 非法取值、裁剪主证据及补充证据，并把 `top_k/requested_top_k` 写入 tool trace，底层检索按单次调用派生候选与 rerank 限制，避免污染共享 retriever 配置 — by Codex
  - 类型: 简化流程
  - 文件: server/agents/tools/retrieve.py; server/agents/qa_agent.py; server/core/retrieval.py; tests/server/agents/test_qa_agent.py; tests/server/test_retrieval.py
- **[server.core.retrieval]**: 增强向量/BM25/guide 检索分支失败日志，`vector_search_failed`、`original_query_vector_search_failed` 等 warning 现在包含 `error_type`、`error`、`top_k` 与 filters，便于定位 Milvus、embedding、schema 或网络问题 — by Codex
  - 类型: 快速修改（无方案包）
  - 文件: server/core/retrieval.py

## [0.1.28] - 2026-05-27

### 修复
- **[frontend.lib.auth]**: 前端启动时校验本地访问密码 token 的 `exp`，过期或损坏 token 会立即清理并回到密码输入页，避免旧浏览器会话因过期认证状态卡在空白工作台 — by Codex
  - 类型: 简化流程
  - 文件: frontend/src/lib/auth.ts; frontend/src/lib/auth.test.ts; .helloagents/modules/frontend.lib.auth.md

## [0.1.27] - 2026-05-19

### 快速修改
- **[server.main / tests.server.test_api / 接口文档 / .helloagents.modules.server.api.v1.documents]**: 将应用内业务异常与请求校验异常统一包装为 HTTP 200 响应，业务结果继续由响应体 `code` 表示；批量删除无索引数据现在返回 HTTP 200 + `code=404` — by Codex
  - 类型: 快速修改（无方案包）
  - 文件: server/main.py; tests/server/test_api.py; 接口文档.md; .helloagents/modules/server.api.v1.documents.md

## [0.1.26] - 2026-05-18

### 快速修改
- **[server.api.v1.documents / tests.server.test_api / 接口文档 / .helloagents.modules.server.api.v1.documents]**: 批量删除汇总响应中若 Milvus 与 Elasticsearch 删除数量均为 0，则返回 404 `文档不存在`，与正常删除成功区分 — by Codex
  - 类型: 快速修改（无方案包）
  - 文件: server/api/v1/documents.py; tests/server/test_api.py; 接口文档.md; .helloagents/modules/server.api.v1.documents.md
- **[server.api.v1.documents / server.models.schemas / tests.server.test_api / 接口文档 / .helloagents.modules.server.api.v1.documents]**: 将批量删除接口响应从逐项 `results[]` 改为整体汇总格式 `deleted` + `deletedChunks`，请求内 source 聚合为一次底层批删；任一文档解析中时返回 409，底层删除失败时返回 500 — by Codex
  - 类型: 快速修改（无方案包）
  - 文件: server/api/v1/documents.py; server/models/schemas.py; tests/server/test_api.py; 接口文档.md; .helloagents/modules/server.api.v1.documents.md
- **[server.api.v1.router / server.core.conversation / server.api.v1.documents / tests.server.test_api / 接口文档]**: 对齐外部接口契约，5 个联调接口免后台调试鉴权，Redis 会话 List 改为交替 `role/content/timestamp` 消息并兼容旧 Q&A 格式读取，批量删除单项异常隔离为 `INTERNAL_ERROR`，流式 `done.title` 仅首轮返回 — by Codex
  - 类型: 快速修改（无方案包）
  - 文件: server/api/v1/router.py; server/core/conversation.py; server/api/v1/documents.py; tests/server/test_api.py; 接口文档.md; .helloagents/modules/server.api.v1.documents.md
- **[pipeline.index / server.api.v1.documents / tests.pipeline.test_index / tests.server.test_api / 接口文档 / .helloagents.modules.server.api.v1.documents]**: 将批量删除底层索引从逐 source 循环改为按 `doc_id` 聚合 source 列表后一次提交，Milvus 使用 `source in [...]`，Elasticsearch 使用 `terms` delete_by_query，同时保留逐文档返回结果 — by Codex
  - 类型: 快速修改（无方案包）
  - 文件: pipeline/index.py; server/api/v1/documents.py; tests/pipeline/test_index.py; tests/server/test_api.py; 接口文档.md; .helloagents/modules/server.api.v1.documents.md
- **[server.api.v1.documents / tests.server.test_api / 接口文档 / .helloagents.modules.server.api.v1.documents]**: 将批量删除接口 `POST /documents/delete` 改为 `doc_id` 驱动的幂等索引删除，不再依赖本地 PDF 或解析目录是否存在，删除 0 条索引也按成功返回；单文档 `DELETE /documents/{doc_id}` 保留旧语义 — by Codex
  - 类型: 快速修改（无方案包）
  - 文件: server/api/v1/documents.py; tests/server/test_api.py; 接口文档.md; .helloagents/modules/server.api.v1.documents.md

## [0.1.25] - 2026-05-15

### 新增
- **[server.api.v1.documents / frontend.lib.api / frontend.hooks.useEuroQaDemo]**: 增加浏览器 PDF 后端代理上传到本系统 MinIO 的联调接口，前端上传流程改为单次调用 `/documents/upload-to-minio`，问答请求改发 `sessionId=1001_UUID去横线` 以验证 Redis 会话逻辑 — by Codex
  - 方案: [202605151957_frontend-minio-session-proxy](plan/202605151957_frontend-minio-session-proxy/)
  - 决策: frontend-minio-session-proxy#D001(后端代理上传)

### 优化
- **[server.core.retrieval / server.core.generation / server.api.v1.query]**: 优化检索候选合并与生成前证据去重，`original_query` 仅保留 vector-only 补召回，expanded queries 继续直连检索入口，BM25 默认字段加入标题/章节/条款/对象别名权重，vector/BM25 改用 RRF 融合，回答生成前按 `chunk_id` 去重以减少重复证据污染 — by Codex
  - 类型: 快速修改（无方案包）
  - 文件: server/core/retrieval.py; server/core/generation.py; tests/server/test_retrieval.py; tests/server/test_generation.py; tests/server/test_api.py
- **[server.core.query_understanding / server.core.retrieval / server.core.generation / server.api.v1.query]**: 删除 `answer_mode` 的 exact/open 路由分叉，metadata probe 改为基于 `target_hint`、`intent_label`、`requested_objects` 的通用结构化补召回，`groundedness` 统一由 rerank score 推断为 `grounded` / `partial` / `not_grounded`，生成层同步移除 exact prompt 分支 — by Codex
  - 类型: 快速修改（无方案包）
  - 文件: server/core/query_understanding.py; server/models/schemas.py; server/core/retrieval.py; server/core/generation.py; server/api/v1/query.py; server/debug/answer_variance.py; tests/server/test_query_understanding.py; tests/server/test_generation.py; tests/server/test_retrieval.py; tests/server/test_api.py; tests/server/test_answer_variance_debug.py; tests/eval/eval_retrieval.py; tests/eval/test_eval_retrieval.py; tests/eval/test_questions.json; tests/eval/eval_results.json; tests/eval/eval_results.sync-conflict-20260410-105311-MZV26SU.json
- **[pipeline.index / server.core.retrieval / tests.pipeline.test_index / tests.server.test_retrieval]**: 将 ES 索引映射改为 keyword + text multi-field，`source_title`、`section_path`、`clause_ids`、`object_aliases`、`ref_labels` 继续保留精确过滤能力，同时为 BM25 检索提供 analyzed 文本子字段，检索默认字段同步切到 `.text` 以提升命中质量 — by Codex
  - 类型: 快速修改（无方案包）
  - 文件: pipeline/index.py; server/core/retrieval.py; tests/pipeline/test_index.py; tests/server/test_retrieval.py
- **[server.api.v1.query / server.main / frontend.lib.api / frontend.lib.types]**: 按 `接口文档.md` 对齐外部接口契约，`/api/v1/query/stream` 的 `done` 事件固定补齐 `code`、`confidence`、`questionType`、`answerMode`、`relatedRefs`、`title` 和来源 camelCase 别名，内部 `image` 来源类型对外映射为 `figure`，SSE `error` 与普通 HTTP 错误统一返回 `{code, message, detail?}` 结构 — by Codex
  - 类型: 快速修改（无方案包）
  - 文件: server/api/v1/query.py; server/main.py; frontend/src/lib/api.ts; frontend/src/lib/types.ts; tests/server/test_api.py; frontend/src/lib/api.test.ts; .helloagents/modules/server.api.v1.query.md

## [0.1.24] - 2026-05-15

### 新增
- **[server.api.v1.documents / server.api.v1.query / deployment]**: 补齐本系统部署 MinIO 与 Redis 的接口支撑，文档解析可按 `minioPath=bucket/key` 下载 PDF，`sessionId` 问答会话可读写 Redis 历史并更新会话元数据 — by Codex
  - 方案: [202605151921_minio-redis-integration](archive/2026-05/202605151921_minio-redis-integration/)
  - 决策: minio-redis-integration#D001(Redis 优先，内存回退)

## [0.1.23] - 2026-05-15

### 新增
- **[server.api.v1.documents / server.api.v1.sources / server.api.v1.query]**: 按接口文档补齐外部对接契约，新增文档解析、批量状态、批量删除、独立翻译端点，并让流式问答 `done` 事件补齐 camelCase 元数据与 `sessionId` 兼容 — by Codex
  - 方案: [202605151724_api-interface-contract](archive/2026-05/202605151724_api-interface-contract/)
  - 决策: api_interface_contract#D001(新契约 canonical，旧端点 wrapper)

## [0.1.22] - 2026-04-28

### 快速修改
- **[server.api.v1.query / frontend MainWorkspace]**: 流式问答新增用户友好的检索过程进度事件，前端在回答区展示问题理解、规范检索、引用补齐、指南参考和生成回答的阶段摘要，提升长链路等待体感 — by Codex
  - 类型: 快速修改（无方案包）
  - 文件: server/api/v1/query.py; frontend/src/lib/types.ts; frontend/src/lib/api.ts; frontend/src/hooks/useEuroQaDemo.ts; frontend/src/components/MainWorkspace.tsx; tests/server/test_api.py; frontend/src/lib/api.test.ts; frontend/src/components/MainWorkspace.test.ts

## [0.1.21] - 2026-04-28

### 修复
- **[frontend.components.EvidencePanel / frontend.lib.pdfViewerPage]**: 修复右侧 PDF 阅读器点击上一页/下一页后顶部页码显示不实时更新的问题，所有页码变更入口现在同步更新当前页与页码输入框 — by yangzhuo
  - 方案: [202604282221_pdf-page-number-sync-fix](archive/2026-04/202604282221_pdf-page-number-sync-fix/)
  - 决策: pdf-page-number-sync-fix#D001(页码状态集中解析)

## [0.1.20] - 2026-04-28

### 修复
- **[frontend.components.MainWorkspace]**: 修复流式生成早期“深度思考”面板无法手动折叠的问题，手动展开/折叠偏好现在优先于自动展开条件 — by yangzhuo
  - 方案: [202604282002_thinking-panel-collapse-fix](archive/2026-04/202604282002_thinking-panel-collapse-fix/)
  - 决策: thinking-panel-collapse-fix#D001(手动偏好优先于自动展开)

## [0.1.19] - 2026-04-19

### 快速修改
- **[server.api.v1.glossary / frontend MainWorkspace / frontend Sidebar]**: 继续扩充首页热门问题题库，并把欢迎区与左侧栏的热门问题显示数量分别放宽到 6 条和 10 条，方便直接点选更多问题 — by yangzhuo
  - 类型: 快速修改（无方案包）
  - 文件: server/api/v1/glossary.py; frontend/src/components/MainWorkspace.tsx; frontend/src/components/Sidebar.tsx; frontend/src/components/MainWorkspace.test.ts; frontend/src/components/Sidebar.test.tsx; tests/server/test_api.py

## [0.1.18] - 2026-04-19

### 优化
- **[frontend.components.Sidebar / frontend.hooks.useEuroQaDemo / frontend.lib.session / server.api.v1.glossary]**: 左侧栏移除术语预览，热门问题切换到新的混凝土结构题库，并恢复“新建检索会话→归档当前会话→历史会话可回看”的本地历史流程 — by yangzhuo
  - 方案: [202604191218_layout-hot-questions-session-history](archive/2026-04/202604191218_layout-hot-questions-session-history/)
  - 决策: layout-hot-questions-session-history#D001(历史会话采用浏览器本地归档), layout-hot-questions-session-history#D002(历史会话替换术语预览区)

## [0.1.17] - 2026-04-13

### 快速修改
- **[frontend MainWorkspace]**: 删除回答头部的“详略”切换按钮和 `questionType` 标签，回答区固定展示完整 LLM 正文，减少工程用户界面的内部状态噪音 — by Codex
  - 类型: 快速修改（无方案包）
  - 文件: frontend/src/components/MainWorkspace.tsx; frontend/src/components/MainWorkspace.test.ts; frontend/src/lib/types.ts; .helloagents/modules/frontend.components.MainWorkspace.md

## [0.1.16] - 2026-04-11

### 优化
- **[server.api.v1.query / frontend.hooks.useEuroQaDemo / frontend Sidebar]**: 删除 history 功能，后端不再注入或缓存最近 3 轮问答，前端刷新后不再恢复旧会话，侧边栏同步移除“最近提问”区块 — by yangzhuo
  - 方案: [202604112241_remove-chat-history](archive/2026-04/202604112241_remove-chat-history/)
  - 决策: remove-chat-history#D001(前后端双链路整体移除 history)

## [0.1.15] - 2026-04-07

### 快速修改
- **[docs architecture-flow]**: 将系统架构图节点文案从程序实现表述改为方法与算法表述，并进一步压缩节点长度、移除起止节点 emoji，以减少 Mermaid 渲染时的文字裁切；保留查询理解、混合检索、重排序、上下文扩展与回答生成的主流程 — by yangzhuo
  - 类型: 快速修改（无方案包）
  - 文件: docs/architecture-flow.md:1-75

## [0.1.14] - 2026-04-01

### 快速修改
- **[frontend MainWorkspace]**: 删除输入区上方的“推荐追问”快捷问题胶囊，仅保留当前规范、意图标签和输入框，减少底部干扰元素 — by yangzhuo
  - 类型: 快速修改（无方案包）
  - 文件: frontend/src/components/MainWorkspace.tsx; frontend/src/components/MainWorkspace.test.ts

## [0.1.13] - 2026-04-01

### 优化
- **[server.api.v1.glossary / frontend MainWorkspace]**: 首页热门问题、欢迎区标题说明和输入示例统一切换到当前 `EN 1992-1-1:2004` 混凝土结构文档语境，移除旧的 EN 1990 导向示例文案 — by yangzhuo
  - 方案: [202604012034_frontend-en1992-copy-refresh](archive/2026-04/202604012034_frontend-en1992-copy-refresh/)
  - 决策: frontend-en1992-copy-refresh#D001(保持建议问题的单一数据源)

## [0.1.12] - 2026-03-31

### 快速修改
- **[frontend EvidencePanel / evidence debug]**: 右侧“定位文本对照”从多卡片纵向堆叠改为单卡片标签切换，`PDF 原文`、`Highlight 文本`、`Locator 文本` 仍保持独立视图，但不再一起挤压侧栏高度与 PDF 主区 — by yangzhuo
  - 类型: 快速修改（无方案包）
  - 文件: frontend/src/components/EvidencePanel.tsx; frontend/src/lib/evidenceDebug.ts; frontend/src/lib/evidenceDebug.test.ts; .helloagents/modules/frontend.components.EvidencePanel.md

## [0.1.11] - 2026-03-31

### 快速修改
- **[frontend EvidencePanel / evidence debug]**: 右侧“定位文本对照”区域改为按 `PDF 原文`、`Highlight 文本`、`Locator 文本` 分别渲染独立卡片，不再把多段定位文本挤在同一个调试块里，便于核对 PDF 定位输入与回退文本 — by yangzhuo
  - 类型: 快速修改（无方案包）
  - 文件: frontend/src/components/EvidencePanel.tsx; frontend/src/lib/evidenceDebug.ts; frontend/src/lib/evidenceDebug.test.ts; .helloagents/modules/frontend.components.EvidencePanel.md

## [0.1.10] - 2026-03-28

### 快速修改
- **[frontend MainWorkspace / inline references]**: 对仍未命中当前 `sources` 的正文规范引用，降级展示从单个 `?` 改为条款缩写胶囊（如 `A1.2.1`、`3.3`），减少视觉噪音并保留可读线索 — by yangzhuo
  - 类型: 快速修改（无方案包）
  - 文件: frontend/src/lib/inlineReferences.ts; frontend/src/lib/inlineReferences.test.ts; frontend/src/components/MainWorkspace.tsx; .helloagents/modules/frontend.components.MainWorkspace.md

## [0.1.8] - 2026-03-28

### 快速修改
- **[frontend MainWorkspace / frontend markdown]**: 修复 `react-markdown` 默认 URL 清洗把 `reference://` / `citation://` 内部协议置空的问题，正文中的规范引用现在会真正进入自定义锚点渲染分支，不再退化成普通文本 — by yangzhuo
  - 类型: 快速修改（无方案包）
  - 文件: frontend/src/lib/markdown.ts; frontend/src/lib/markdown.test.ts; frontend/src/components/MainWorkspace.tsx

## [0.1.9] - 2026-03-28

### 快速修改
- **[frontend citations]**: 当前端收到同一 section 的多条来源片段时，正文引用会按条款接近度选择最合适的 source，不再因为“匹配不唯一”直接显示为 `?` — by yangzhuo
  - 类型: 快速修改（无方案包）
  - 文件: frontend/src/lib/citations.ts; frontend/src/lib/citations.test.ts

## [0.1.7] - 2026-03-28

### 优化
- **[frontend MainWorkspace / frontend citations]**: 正文中的 Eurocode 引用改为更轻量的编号锚点，底部“引用来源”列表同步展示对应编号，未命中来源的引用降级为中性提示，减少正文阅读干扰并保留溯源线索 — by yangzhuo
  - 方案: [202603281812_citation-anchor-ui](archive/2026-03/202603281812_citation-anchor-ui/)
  - 决策: citation-anchor-ui#D001(正文引用改为轻量编号锚点)

## [0.1.1] - 2026-03-27

### 修复
- **[server.core.generation]**: 补齐流式与非流式响应中的 `Source.translation`，使来源面板可展示中文解释 — by yangzhuo
  - 方案: [202603271643_source-translation-panel](archive/2026-03/202603271643_source-translation-panel/)
  - 决策: source-translation-panel#D001(以后端补齐 source.translation 为主)

## [0.1.2] - 2026-03-27

### 快速修改
- **[server.core.generation]**: `Source.original_text` 改为保留完整 chunk 原文，不再按 500 字截断 — by yangzhuo
  - 类型: 快速修改（无方案包）
  - 文件: server/core/generation.py:16-17,135-177; server/models/schemas.py:66-73

## [0.1.3] - 2026-03-27

### 快速修改
- **[server.core.generation]**: source 翻译提示词改为使用完整原文，中文解释按全文翻译生成 — by yangzhuo
  - 类型: 快速修改（无方案包）
  - 文件: server/core/generation.py:15-16,154-179; tests/server/test_generation.py:63-90

## [0.1.4] - 2026-03-27

### 新功能
- **[server.core.generation / frontend query workspace]**: 新增流式 `reasoning` 事件和“深度思考”折叠面板，并把来源翻译升级为 Markdown 友好渲染 — by yangzhuo
  - 方案: [202603271755_thinking-panel-evidence-markdown](archive/2026-03/202603271755_thinking-panel-evidence-markdown/)
  - 决策: thinking-panel-evidence-markdown#D001(独立 reasoning SSE 事件), thinking-panel-evidence-markdown#D002(译文走 Markdown 渲染)

## [0.1.5] - 2026-03-27

### 数据更新
- **[data.glossary]**: 从 `术语库1.0-20260326.xlsx` 同步更新运行时术语表，按“Excel 覆盖同名、保留旧项”合并到 `data/glossary.json` — by yangzhuo
  - 方案: [202603271903_glossary-sync-from-xlsx](archive/2026-03/202603271903_glossary-sync-from-xlsx/)
  - 决策: glossary-sync-from-xlsx#D001(采用保守合并，不删除旧有未覆盖项)

## [0.1.6] - 2026-03-28

### 新功能
- **[server.api.v1.settings / server.api.v1.query / frontend TopBar]**: 新增前后端联动的 LLM 设置能力，支持 `api_key`、`base_url`、`model`、`enable_thinking` 的前端配置、本地持久化和请求级生效 — by yangzhuo
  - 类型: 实现（基于 spec + plan）
  - 文档: `docs/superpowers/specs/2026-03-28-llm-settings-design.md`, `docs/superpowers/plans/2026-03-28-llm-settings.md`
  - 文件: server/api/v1/settings.py; server/api/v1/query.py; server/config.py; server/models/schemas.py; frontend/src/components/TopBar.tsx; frontend/src/components/LlmSettingsPanel.tsx; frontend/src/hooks/useEuroQaDemo.ts; frontend/src/lib/api.ts; frontend/src/lib/session.ts; frontend/src/lib/types.ts

### 优化
- **[server.core.retrieval / server.api.v1.query]**: 检索入口改为不对称双路召回，`rewritten_query` 继续走 `vector + BM25`，`original_question` 追加一次 vector-only 补召回，用于降低 query rewrite 偏义带来的结果抖动 — by yangzhuo
  - 类型: 快速修改（无方案包）
  - 文件: server/api/v1/query.py:39-50,78-89; server/core/retrieval.py:157-174,206-218,264-308; tests/server/test_api.py:21-319; tests/server/test_retrieval.py:98-183
- **[server.core.retrieval]**: 单文档或显式 `source` 过滤场景下跳过跨文档聚合，不再被 `max_per_source=3` 硬截断候选 chunk — by yangzhuo
  - 类型: 快速修改（无方案包）
  - 文件: server/core/retrieval.py:190-204,321-325; tests/server/test_retrieval.py:54-92
- **[server.config / server.core.retrieval]**: 默认 `rerank_top_n` 从 `5` 提高到 `8`，让单文档场景在跳过跨文档聚合后保留更宽的 rerank 候选窗口 — by yangzhuo
  - 类型: 快速修改（无方案包）
  - 文件: server/config.py:38-41; tests/test_config.py:10-28
- **[server.core.generation]**: source 翻译补齐在批量 JSON 解析失败时自动降级为逐条重试，同时不再为翻译调用显式设置 `max_tokens`，修复长表格全文翻译时 `Unterminated string` 导致的空翻译问题 — by yangzhuo
  - 类型: 快速修改（无方案包）
  - 文件: server/core/generation.py:21-286; tests/server/test_generation.py:64-145
- **[frontend MainWorkspace / EvidencePanel]**: Markdown 渲染链路接入 `remark-math + rehype-katex`，主回答区与右侧中文解释现在都支持 LaTeX 公式展示 — by yangzhuo
  - 类型: 快速修改（无方案包）
  - 文件: frontend/package.json; frontend/src/lib/markdown.ts; frontend/src/lib/markdown.test.ts; frontend/src/main.tsx; frontend/src/components/MainWorkspace.tsx; frontend/src/components/EvidencePanel.tsx
- **[frontend MainWorkspace]**: 回答正文中的规范引用从方括号文本升级为内联可点击引用标记，点击后直接联动右侧证据面板，底部“引用来源”仍保留 — by yangzhuo
  - 类型: 快速修改（无方案包）
  - 文件: frontend/src/components/MainWorkspace.tsx; frontend/src/lib/citations.ts; frontend/src/lib/citations.test.ts
- **[server.core.generation]**: 问答提示词改为“先回答当前片段可确认内容，再说明仍需补充的信息”，减少回答开头泛化为“根据当前片段无法确认”的保守表述 — by yangzhuo
  - 类型: 快速修改（无方案包）
  - 文件: server/core/generation.py:40-73; tests/server/test_generation.py:21-47
- **[server.api.v1.glossary]**: 首页热门问题改为只包含当前 `EN 1990` 单文档可直接回答的总则问题，避免跨规范和模棱两可的示例提问 — by yangzhuo
  - 类型: 快速修改（无方案包）
  - 文件: server/api/v1/glossary.py; tests/server/test_api.py; .helloagents/modules/server.api.v1.glossary.md
- **[frontend MainWorkspace / citations]**: 正文中的 Eurocode 引用现在会容忍 `3.3(1)P` 和空页码 `p.` 这类模型输出差异，并按“引用来源”同风格渲染为可点击跳转按钮 — by yangzhuo
  - 类型: 快速修改（无方案包）
  - 文件: frontend/src/lib/citations.ts; frontend/src/lib/citations.test.ts; frontend/src/components/MainWorkspace.tsx
- **[frontend citations]**: 正文引用匹配进一步支持 `NOTE` 尾缀、章节前缀到子条款的映射，以及来源中多条款列表的归一化匹配，提升 LLM 自由输出时的点击命中率 — by yangzhuo
  - 类型: 快速修改（无方案包）
  - 文件: frontend/src/lib/citations.ts; frontend/src/lib/citations.test.ts
- **[frontend MainWorkspace / citations]**: 未命中当前 `sources` 的规范引用也会统一渲染为“引用来源”同风格的引用芯片；命中的可点击跳转，未命中的显示为不可跳转占位芯片，不再保留裸方括号文本 — by yangzhuo
  - 类型: 快速修改（无方案包）
  - 文件: frontend/src/lib/citations.ts; frontend/src/lib/citations.test.ts; frontend/src/components/MainWorkspace.tsx
- **[frontend MainWorkspace]**: 正文引用芯片视觉强化，新增更明显的 `引用` 标签、悬停态、阴影和按钮态区分，避免和普通正文文本混在一起看不出可点击性 — by yangzhuo
  - 类型: 快速修改（无方案包）
  - 文件: frontend/src/components/MainWorkspace.tsx
- **[frontend citations]**: 纯文本格式的规范引用（如 `EN 1990:2002 · 2.4(1)`）现在也会被识别并渲染为引用芯片，不再要求模型必须输出方括号格式 — by yangzhuo
  - 类型: 快速修改（无方案包）
  - 文件: frontend/src/lib/citations.ts; frontend/src/lib/citations.test.ts

## [0.1.7] - 2026-04-11

### 数据更新
- **[external glossary / data.glossary]**: 将运行时术语表中 Excel 尚未收录的 28 个 `中文 -> 英文` 词条回填到外部术语库 `术语库1.0-20260407.xlsx`，并保留 Excel 内部 13 组冲突词条待人工复核 — by yangzhuo
  - 方案: [202604112019_glossary-xlsx-runtime-backfill](archive/2026-04/202604112019_glossary-xlsx-runtime-backfill/)
  - 决策: glossary-xlsx-runtime-backfill#D001(仅补缺失词条，不自动修复 Excel 内部冲突)

## [0.1.8] - 2026-04-11

### 数据更新
- **[data.glossary]**: 按 `术语库1.0-20260407.xlsx` 的 `Sheet1` 直接重建运行时术语表，生成 899 个唯一中文术语并移除旧 JSON 中未出现在 xlsx 的历史残留项 — by yangzhuo
  - 方案: [202604112032_glossary-json-from-xlsx](archive/2026-04/202604112032_glossary-json-from-xlsx/)
  - 决策: glossary-json-from-xlsx#D001(xlsx 重复中文按后出现记录覆盖前值)

### 优化
- **[server query stream / frontend MainWorkspace]**: 将旧式检索进度、Agent 活动外框和深度思考面板替换为默认折叠的真实 tool 调用卡片流；后端 SSE `tool:*` 事件补充真实 `tool_args`、`tool_result`、`tool_trace.expanded_queries`，前端不再从普通 progress 或 reasoning 推断 `query_rewrite`/tool result — by Codex
  - 类型: 简化流程实现（Trellis 任务 06-01-tool）
  - 文件: server/agents/qa_agent.py; server/api/v1/query.py; frontend/src/lib/types.ts; frontend/src/components/MainWorkspace.tsx; frontend/src/components/MainWorkspace.test.ts; tests/server/test_api.py; tests/server/agents/test_qa_agent.py
