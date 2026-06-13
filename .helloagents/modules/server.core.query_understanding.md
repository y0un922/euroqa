# 模块: server.core.query_understanding

## 职责

- 清理用户问题中的常见 prompt injection 片段
- 从问题中提取 source、目标对象和偏好元素类型
- 调用 LLM 进行三路查询扩展、问题分型、工程上下文识别和检索目标提示
- 为特定高频问题提供稳定的确定性查询扩展兜底

## 行为规范

- `expand_queries()` 会将固定查询扩展规则放入 system prompt，将对话历史、术语提示和当前问题放入 user prompt。
- DashScope/Qwen 且 `LLM_PROMPT_CACHE_ENABLED=true` 时，查询扩展固定 system prompt 会附带 `cache_control={"type":"ephemeral"}`；动态 user prompt 保持普通字符串。
- `_call_llm()` 保留旧的单 user prompt 调用兼容路径；只有传入 `system_prompt` 时才拆分 system/user messages。
- 查询扩展失败或解析失败时必须降级为原始问题，不能中断主检索流程。

## 依赖关系

- 依赖 `shared.llm_clients.get_async_openai_client()` 复用 OpenAI-compatible 客户端
- 依赖 `server.models.schemas` 提供 `QuestionType`、`EngineeringContext`、`GuideHint` 与路由提示模型
