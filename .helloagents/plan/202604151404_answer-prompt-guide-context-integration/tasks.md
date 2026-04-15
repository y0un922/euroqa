# 任务清单: answer-prompt-guide-context-integration

```yaml
@feature: answer-prompt-guide-context-integration
@created: 2026-04-15
@status: pending
@mode: R3
```

<!-- LIVE_STATUS_BEGIN -->
状态: pending | 进度: 0/7 (0%) | 更新: 2026-04-15 14:07:00
当前: 方案包已创建，待执行 checkpoint commit
<!-- LIVE_STATUS_END -->

## 进度概览

| 完成 | 失败 | 跳过 | 总数 |
|------|------|------|------|
| 0 | 0 | 0 | 7 |

---

## 任务列表

### 1. 回退点与测试约束

- [ ] 1.1 记录当前工作区状态并创建 checkpoint commit，作为本次改造前的回退点。 | depends_on: []
- [ ] 1.2 在 `tests/server/test_generation.py` 与 `tests/server/test_api.py` 中补充新提示词结构和 `guide_context` 透传的失败测试。 | depends_on: [1.1]

### 2. 数据结构与检索链路

- [ ] 2.1 在 `server/models/schemas.py` 中扩展 `RetrievalContext` 和相关返回模型，支持 `guide_chunks` 快照。 | depends_on: [1.2]
- [ ] 2.2 在 `server/core/retrieval.py` 中实现 `guide_context` 条件触发检索，并把结果挂入 `RetrievalResult`。 | depends_on: [2.1]

### 3. 生成与 API 透传

- [ ] 3.1 在 `server/core/generation.py` 中全量替换现有回答模板，按“问题 + 规范证据 + 元数据 + 可选指南证据”重构 prompt 组装。 | depends_on: [2.2]
- [ ] 3.2 在 `server/api/v1/query.py` 中同步 `/query` 与 `/query/stream` 的新上下文透传，确保流式 done payload 与非流式响应一致。 | depends_on: [3.1]

### 4. 验证与收尾

- [ ] 4.1 运行相关后端测试并修复回归，确认新模板、指南链路和流式/非流式一致性。 | depends_on: [3.2]

---

## 执行日志

| 时间 | 任务 | 状态 | 备注 |
|------|------|------|------|

---

## 执行备注

> 记录执行过程中的重要说明、决策变更、风险提示等
>
> - `create_package.py` 第一次以错误根路径调用，额外在 `.helloagents/.helloagents/plan/` 下创建了重复方案包；后续执行以正确路径 `.helloagents/plan/202604151404_answer-prompt-guide-context-integration` 为准。
