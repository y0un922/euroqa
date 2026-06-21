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
- 未携带 `sessionId` 时，问答入口不向生成层传递历史问答；每次请求都按独立对话处理。
- `conversation_id` 字段仅作为旧请求/响应关联标识保留，不驱动多轮 history 记忆。
- 携带 `sessionId` 时，问答入口会从 Redis 会话管理器读取 `context:{sessionId}` 历史并在完成后追加本轮 Q&A。
- `/query/stream` 的 `done` 事件会额外补齐外部对接所需的 `code`、`confidence`、`questionType`、`answerMode`、`relatedRefs`、`title` 和来源字段 camelCase 别名；其中内部 `image` 来源类型对外输出为 `figure`。
- `/query/stream` 的 `error` 事件必须输出 `{code, message}`，普通 HTTP 错误由全局异常处理器输出 `{code, message, detail}`。
- 请求体兼容 `sessionId`，并将其视为接口文档定义的外部会话标识。
- 请求体兼容 `kbIds`。未传 `kbIds` 时保持全库检索；传入有效知识库时会解析其文档 `doc_id` 为 source 列表并传给 agent/retrieve。
- 空 `kbIds`、空知识库或无效知识库不得回退到全库检索；非流式接口返回 `confidence=none`、`degraded=true` 的空结果，流式接口对无效知识库输出 SSE error，对空知识库输出空结果 done 事件。

## 依赖关系

- 依赖 `server.config.ServerConfig.with_llm_override()` 合成运行时配置
- 依赖 `server.core.query_understanding` 产出 `original_question` 与 `rewritten_query`
- 依赖 `server.core.retrieval` 执行不对称双路召回
- 依赖 `server.core.generation` 消费合成后的配置
- 依赖 `server.core.conversation` 生成/复用会话 ID，并在 `sessionId` 场景下通过 Redis 保存问答历史
- 依赖 `server.services.kb_database` 将 `kbIds` 解析为文档集合
