# 模块: server.agents.tools.retrieve

## 职责

- 为 QA agent 提供 `retrieve(query, top_k=8)` 工具。
- 执行 query understanding、混合检索、证据裁剪，并把结果写入 `EvidenceBundle`。
- 生成返回给 agent 的检索 Observation 摘要。

## 行为规范

- `_retrieve_impl` 入口必须先检查 `ctx.context.bundle.groundedness`；当已为 `grounded` 时，跳过 `_clamp_top_k`、`analyze_query` 和底层 retriever，避免重复消耗 LLM/检索/rerank 流水线。
- grounded 拦截需要写入 `bundle.tool_trace`：`tool=retrieve`、原始 `query`、`skipped=true`、`reason=already_grounded`。
- grounded 拦截返回文本需包含当前 `chunk_count`，并明确要求 agent 基于已有证据回复。
- 正常检索返回 grounded Observation 时，必须包含“无需再次检索”类停止指令。
- Top hits 摘要最多展示前三条，每条应包含 source、section 和 80 字符以内的 content preview；preview 需要将换行替换为空格。
- `top_k` 仍由 `_clamp_top_k` 限制在 3-12，非法值回退到默认 8。

## 依赖关系

- 依赖 `server.core.query_understanding.analyze_query` 生成 expanded queries、filters 和结构化 hint。
- 依赖 `server.core.retrieval.HybridRetriever.retrieve` 执行底层检索。
- 依赖 `server.agents.tool_progress.ToolProgressEmitter` 上报 query understanding 与 hybrid search 子步骤。
