# 模块: server.api.v1.sessions

## 职责

- 提供前端会话恢复接口。
- 提供 Redis-backed 用户会话摘要列表接口。

## 行为规范

- `GET /api/v1/sessions/{session_id}` 保持外部契约公开，用于按 `sessionId` 恢复完整消息。
- `GET /api/v1/sessions?userId=...` 返回指定用户的会话摘要列表，字段包含 `sessionId`、`conversationId`、`title`、`updatedAt`、`messageCount`。
- 会话列表接口必须显式执行 `require_auth`，避免仅凭 `userId` 枚举会话标题摘要。
- `DELETE /api/v1/sessions/{session_id}` 删除一个历史会话，返回 `{sessionId, deleted}`；该接口必须执行 `require_auth`。
- Redis 管理器从 `user:{user_id}:sessions` 读取会话元数据，并结合 `context:{session_id}` 计算问答条数。
- 删除 Redis 会话时必须同时清理 `context:{session_id}` 消息列表和 `user:{user_id}:sessions` 元数据字段。
- 会话摘要按 `updatedAt` 倒序返回；元数据标题为空时回退到首个问题，再回退到会话 ID。

## 依赖关系

- 依赖 `server.core.conversation.RedisConversationManager` 读取 Redis 会话元数据和消息。
- 依赖 `server.models.schemas.ConversationSessionListResponse` 和 `ConversationSessionResponse` 输出 camelCase 前端契约。
