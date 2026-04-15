# 模块: frontend.hooks.useEuroQaDemo

## 职责

- 管理 Demo 工作台的初始化加载、提问和流式回答状态
- 加载服务端 LLM 默认值并管理本地 LLM 覆盖设置
- 在问答请求中透传当前有效的 LLM 设置

## 行为规范

- 初始化阶段并行加载文档、术语、建议问题和 `GET /api/v1/settings/llm`。
- LLM 设置默认值接口失败时，不应阻断主问答工作台，只回退到前端内置默认值。
- 浏览器刷新后不恢复旧会话消息、草稿或引用定位状态；每次页面加载都从空白会话开始。
- `savePersistedDemoSession()` 仅用于清理旧 `localStorage` 键，不再持久化问答 history。
- 每次提问和重新生成答案都使用新的 `conversationId`，不复用上一轮问答上下文。
- 提问时仅在存在本地覆盖设置时才附带 `llm` 请求字段。

## 依赖关系

- 依赖 `frontend/src/lib/api.ts` 获取服务端默认值并发起问答请求
- 依赖 `frontend/src/lib/session.ts` 清理历史会话存储键，避免旧数据再次恢复
