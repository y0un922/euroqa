# 模块: server.core.generation

## 职责

- 组装检索上下文 prompt
- 调用 LLM 生成问答内容
- 解析结构化响应
- 构建来源 `Source` 和关联引用
- 在流式与非流式链路中补齐缺失的 `Source.translation`
- 在流式链路中转发可选的 reasoning 内容

## 行为规范

- `build_prompt()` 负责把 chunks、parent chunks、术语表和历史对话拼接成用户提示词。
- `generate_answer()` 负责非流式 JSON 输出；若 `sources[].translation` 缺失，会在返回前统一补齐。
- `generate_answer_stream()` 负责流式 Markdown 输出；若模型返回 `reasoning_content`，会额外发出 `reasoning` 事件；在 `done` 事件中直接返回带翻译的 sources。
- 问答提示词应优先要求模型回答“当前片段可直接确认”的内容；若仅能部分回答，先给已确认结论，再单列缺失条件或需参考的其他规范。
- `Source.original_text` 应保留完整 chunk 内容，不在生成层做固定长度截断。
- source 翻译提示词当前使用完整原文，因此“中文解释”对应全文翻译，不再按固定字数截断。
- source 翻译输出被约束为 Markdown 友好内容，表格/列表应优先转成 GFM 结构，避免直接依赖 HTML。
- source 翻译调用不再显式传 `max_tokens`，避免长表格或长条文在 JSON 输出阶段被本地长度上限截断。
- 当批量 source 翻译返回的 JSON 因长表格或长原文被截断而解析失败时，生成层应自动退回逐条翻译重试，避免整批来源全部丢失中文解释。
- source 翻译补齐失败时保留空字符串，由前端继续走现有空态兜底。
- DashScope/Qwen 链路会自动附带 `enable_thinking`，其他模型即使无 reasoning 也应保持正常回答。

## 依赖关系

- 依赖 `server.models.schemas` 提供 `Chunk`、`Source`、`QueryResponse`
- 依赖 OpenAI-compatible LLM 接口完成回答与来源翻译
