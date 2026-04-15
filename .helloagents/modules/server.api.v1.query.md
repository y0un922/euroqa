# 模块: server.api.v1.query

## 职责

- 处理 `/query` 与 `/query/stream` 问答入口
- 在请求进入查询理解与生成层前合成运行时 LLM 配置

## 行为规范

- 当请求未携带 `llm` 覆盖项时，沿用服务端默认 `ServerConfig`。
- 当请求携带 `llm` 覆盖项时，按“非空覆盖值优先、空字符串回退默认值”的规则生成本次请求的运行时配置。
- 运行时配置只影响 LLM 调用链路，不改变检索依赖、embedding 或 rerank 配置。
- `/query` 与 `/query/stream` 必须使用同一套覆盖规则，避免流式和非流式行为不一致。
- 问答入口在调用检索层时，必须同时传入 `analysis.rewritten_query` 和 `analysis.original_question`。
- `rewritten_query` 作为主检索 query，`original_question` 仅作为向量补召回信号，不直接触发中文 BM25。
- 问答入口不再向生成层传递历史问答；每次请求都按独立对话处理。
- `conversation_id` 字段仅作为请求/响应关联标识保留，不再驱动多轮 history 记忆。

## 依赖关系

- 依赖 `server.config.ServerConfig.with_llm_override()` 合成运行时配置
- 依赖 `server.core.query_understanding` 产出 `original_question` 与 `rewritten_query`
- 依赖 `server.core.retrieval` 执行不对称双路召回
- 依赖 `server.core.generation` 消费合成后的配置
- 依赖 `server.core.conversation` 仅生成/复用会话 ID，不再保存问答历史
