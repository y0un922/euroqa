# 模块: frontend.hooks.useEuroQaDemo

## 职责

- 管理 Demo 工作台的初始化加载、提问和流式回答状态
- 加载服务端 LLM 默认值并管理本地 LLM 覆盖设置
- 在问答请求中透传当前有效的 LLM 设置
- 管理当前会话指针、Redis-backed 历史会话摘要、完整会话恢复和切换
- 管理当前聊天限定的知识库选择状态 `selectedKbIds`

## 行为规范

- 初始化阶段并行加载文档、术语、建议问题、`GET /api/v1/settings/llm` 和 `GET /api/v1/sessions?userId=...`。
- LLM 设置默认值接口失败时，不应阻断主问答工作台，只回退到前端内置默认值。
- 浏览器刷新后会从本地轻量指针恢复最近一次当前会话，并从 Redis 会话列表接口恢复侧边栏历史入口。
- `savePersistedDemoSession()` 只保存当前会话指针、草稿、引用定位状态和设置；历史会话列表不再依赖本地持久化。
- 点击“新建检索会话”时，当前非空会话会立即插入本地历史摘要列表；下次刷新后由 Redis 元数据列表恢复。
- 点击历史会话时，前端按 `sessionId` 调用后端单会话恢复接口拉取完整消息。
- 删除历史会话时，前端先从本地摘要列表乐观移除，再调用后端删除接口；当前活动会话不允许从历史列表删除。
- 新建前端会话时生成 `1001_UUID去横线` 格式的外部 `sessionId`，同一会话内提问和重新生成答案复用该 ID。
- 问答请求通过 `sessionId` 字段发送给后端，用于验证 Redis 会话历史读写；旧 `conversationId` 字段只作为本地显示和兼容状态保留。
- 提问时仅在存在本地覆盖设置时才附带 `llm` 请求字段。
- 提问和重新生成答案时，如果 `selectedKbIds` 非空，`buildChatQueryPayload()` 会把该列表作为 `kbIds` 传给后端；空列表表示全库检索，不发送 `kbIds` 字段。

## 依赖关系

- 依赖 `frontend/src/lib/api.ts` 获取服务端默认值、历史会话摘要、完整会话和问答接口
- 依赖 `frontend/src/lib/session.ts` 读写当前会话轻量指针
