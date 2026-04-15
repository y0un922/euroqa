# Phase 2: 前端数据接入与会话持久化

## 任务清单

- [x] P2-T1 扩展前端类型与 API payload，纳入 retrieval context。（验收：`frontend/src/lib/types.ts` 增加 retrieval context 相关类型；`QueryResponse` 与 `StreamDonePayload` 同步扩展；`ChatTurn` 拥有可选且可持久化的新字段）
- [x] P2-T2 在 `frontend/src/hooks/useEuroQaDemo.ts` 中接入 retrieval context，覆盖流式完成、非流式 fallback 和错误分支。（验收：流式完成时写入对应 `ChatTurn`；fallback 非流式路径也写入同样结构；错误分支保持稳定空值；刷新页面后消息结构不丢失）
- [x] P2-T3 扩展 `frontend/src/lib/session.ts` 的 localStorage 序列化、恢复与迁移逻辑。（验收：旧 session 仍可恢复；新 session 可完整恢复 retrieval context；`frontend/src/lib/session.test.ts` 覆盖新旧结构；恢复后的 streaming 消息仍按既有规则降级为 error）

## Notes

- 本阶段不建议并行，`types`、`hook`、`session` 之间是强依赖关系。
- 所有新增字段都应优先设计为可选，以降低历史会话迁移风险。
