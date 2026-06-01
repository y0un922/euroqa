# 模块: server.agents.qa_agent

## 职责

- 构建 Eurocode QA agent，注册 `retrieve` 与 `lookup_glossary` 工具。
- 将当前问题与有限历史轮次转换为 OpenAI Agents SDK 输入。
- 将 agent 流式事件转换为前端可消费的 thinking、tool_calling、tool_result 事件。

## 行为规范

- `_QA_AGENT_INSTRUCTIONS` 保留“Eurocode 问题必须 retrieve、grounded 后停止、单问题最多 retrieve 2 次”的软约束。
- `_build_input_items` 只压缩历史 assistant answer，不截断当前用户问题。
- 历史 answer 进入 agent 上下文前必须移除 `[Ref-N]` citation marker，并截断到 200 字符；generation 阶段的历史拼接逻辑不属于本模块，不要同步修改。
- agent 达到 max turns 时，如已有 RAG evidence，返回“已检索到相关规范证据，正在整理回答。”以便后续生成阶段继续使用证据。

## 依赖关系

- 依赖 `server.agents.deps.QADeps` 提供 config、retriever、glossary、evidence bundle 和 conversation state。
- 依赖 `server.agents.tools.retrieve` 与 `server.agents.tools.lookup_glossary` 作为 agent tools。
- 依赖 OpenAI Agents SDK `Runner` 执行非流式与流式 agent loop。
