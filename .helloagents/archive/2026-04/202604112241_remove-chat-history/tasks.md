# 任务清单: remove-chat-history

```yaml
@feature: remove-chat-history
@created: 2026-04-11
@status: completed
@mode: R2
```

<!-- LIVE_STATUS_BEGIN -->
状态: completed | 进度: 4/4 (100%) | 更新: 2026-04-11 22:56:00
当前: 所有任务已完成，待归档
<!-- LIVE_STATUS_END -->

## 进度概览

| 完成 | 失败 | 跳过 | 总数 |
|------|------|------|------|
| 4 | 0 | 0 | 4 |

---

## 任务列表

### 1. 后端去除会话历史注入

- [√] 1.1 在 `tests/server/test_api.py` 中新增回归测试，验证 `/api/v1/query` 与 `/api/v1/query/stream` 不再向生成层传入历史问答，也不再写回历史 | depends_on: []
- [√] 1.2 在 `server/api/v1/query.py` 与 `server/core/conversation.py` 中移除历史问答的读写逻辑，同时保留 `conversation_id` 响应兼容 | depends_on: [1.1]

### 2. 前端去除本地 history 与最近提问展示

- [√] 2.1 在 `frontend/src/lib/session.test.ts` 中新增回归测试，验证会话持久化被禁用且旧 key 会被清理 | depends_on: []
- [√] 2.2 在 `frontend/src/lib/session.ts`、`frontend/src/hooks/useEuroQaDemo.ts`、`frontend/src/components/Sidebar.tsx`、`frontend/src/App.tsx` 中移除本地恢复与“最近提问”链路 | depends_on: [2.1, 1.2]

---

## 执行日志

| 时间 | 任务 | 状态 | 备注 |
|------|------|------|------|
| 2026-04-11 22:45 | 方案确认 | completed | 采用单方案：前后端同步去 history，保留当前页即时消息展示 |
| 2026-04-11 22:48 | 1.1 | completed | 新增后端回归测试，先验证旧逻辑仍会透传 history |
| 2026-04-11 22:49 | 2.1 | completed | 新增前端 session 回归测试，锁定“禁用持久化”语义 |
| 2026-04-11 22:52 | 1.2 | completed | query / query_stream 不再向生成层传递或写回 conversation history |
| 2026-04-11 22:53 | 2.2 | completed | 去掉 localStorage 恢复、最近提问展示，并改为每次提问生成新 conversationId |

---

## 执行备注

> 记录执行过程中的重要说明、决策变更、风险提示等
