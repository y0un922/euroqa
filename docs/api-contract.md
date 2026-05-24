# API Contract

## `/query/stream`

`/query/stream` 使用 Server-Sent Events 返回流式问答结果。`done` event 的 `data` 字段是 JSON 对象，除答案、引用和置信度外，会包含 `answerMode` 表示本轮回答策略。

### `answerMode` 取值

| 值 | 含义 |
|---|---|
| `standard` | 检索证据充分（`groundedness=grounded`），标准 RAG 回答 |
| `cautious` | 检索证据部分充分（`groundedness=partial`），回答中会提示证据有限 |
| `fallback` | 检索证据不足（`groundedness=not_grounded`），回答会明确说明 |
| `chat` | Agent 判断为闲聊/上下文追问，不走 RAG 直接回答 |
| `clarify` | Agent 判断问题模糊，反问用户补充信息 |

### Progress stage

Agent 编排后，`progress` event 的 `stage` 可能包含 agent-native 名称。前端应兼容未知 stage，并至少识别以下值：

| 值 | 含义 |
|---|---|
| `agent_thinking` | Agent 正在理解问题并决定回答策略，替代旧链路中的 `understanding` 入口阶段 |
| `retrieving` | 正在或已经完成规范证据检索 |
| `generating` | 正在生成 RAG 回答 |
| `composing` | Agent 正在组合最终回答，可按 `generating` 类状态处理 |
| `chat` | Agent 已生成直接闲聊/上下文回复 |
| `clarify` | Agent 已生成澄清问题 |
| `glossary_lookup` | Agent 执行术语查询 |

旧的 `understanding`、`references`、`guide` stage 仍可能在兼容路径中出现，但新 agent 路径会优先使用 `agent_thinking` 等 agent-native stage。
