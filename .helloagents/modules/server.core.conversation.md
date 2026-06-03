# 模块: server.core.conversation

## 职责

- 管理问答会话状态。
- 在 Redis 模式下读写 `context:{sessionId}` 消息列表和 `user:{userId}:sessions` 会话元数据。
- 在无 Redis 模式下提供内存回退会话存储。

## 行为规范

- Redis `context:{sessionId}` 保存 role/content/timestamp 消息，同时兼容旧版 `{question, answer}` 记录读取。
- Redis `user:{userId}:sessions` 保存每个 session 的 `title`、`createdAt`、`updatedAt` 元数据。
- `get_session_async()` 将 Redis 消息还原为前端 `ChatTurn` 列表。
- `get_sessions_async()` 从 Redis 元数据哈希枚举会话摘要，并读取对应消息列表计算 `messageCount`。
- 会话摘要标题优先使用 Redis metadata `title`，为空时使用第一条问题，再回退到 `sessionId`。

## 依赖关系

- 被 `server.api.v1.query` 用于读写问答历史。
- 被 `server.api.v1.sessions` 用于恢复完整会话和列出历史会话摘要。
