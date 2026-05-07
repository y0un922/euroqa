# 任务清单: answer-prompt-guide-context-integration

```yaml
@feature: answer-prompt-guide-context-integration
@created: 2026-04-15
@status: completed
@mode: R3
```

<!-- LIVE_STATUS_BEGIN -->
状态: completed | 进度: 7/7 (100%) | 更新: 2026-04-15 14:19:30
当前: guide_context 检索透传与统一回答整理模板已完成，并通过后端回归测试
<!-- LIVE_STATUS_END -->

## 进度概览

| 完成 | 失败 | 跳过 | 总数 |
|------|------|------|------|
| 7 | 0 | 0 | 7 |

---

## 任务列表

### 1. 回退点与测试约束

- [√] 1.1 记录当前工作区状态并创建 checkpoint commit，作为本次改造前的回退点。 | depends_on: []
- [√] 1.2 在 `tests/server/test_generation.py` 与 `tests/server/test_api.py` 中补充新提示词结构和 `guide_context` 透传的失败测试。 | depends_on: [1.1]

### 2. 数据结构与检索链路

- [√] 2.1 在 `server/models/schemas.py` 中扩展 `RetrievalContext` 和相关返回模型，支持 `guide_chunks` 快照。 | depends_on: [1.2]
- [√] 2.2 在 `server/core/retrieval.py` 中实现 `guide_context` 条件触发检索，并把结果挂入 `RetrievalResult`。 | depends_on: [2.1]

### 3. 生成与 API 透传

- [√] 3.1 在 `server/core/generation.py` 中全量替换现有回答模板，按“问题 + 规范证据 + 元数据 + 可选指南证据”重构 prompt 组装。 | depends_on: [2.2]
- [√] 3.2 在 `server/api/v1/query.py` 中同步 `/query` 与 `/query/stream` 的新上下文透传，确保流式 done payload 与非流式响应一致。 | depends_on: [3.1]

### 4. 验证与收尾

- [√] 4.1 运行相关后端测试并修复回归，确认新模板、指南链路和流式/非流式一致性。 | depends_on: [3.2]

---

## 执行日志

| 时间 | 任务 | 状态 | 备注 |
|------|------|------|------|
| 2026-04-15 14:12 | 1.1 | completed | 已创建 checkpoint commit `4121381`，提交前排除了 `frontend/node_modules`、`data/debug_runs`、`data/parsed`、`data/pdfs`、`.superpowers` 与误建的 `.helloagents/.helloagents` |
| 2026-04-15 14:16 | 1.2 | completed | 为 `build_prompt`、`generate_answer*`、API done payload 与 retriever 透传补充 `guide_chunks/question_type` 相关断言，并按新模板更新旧断言 |
| 2026-04-15 14:17 | 2.1 | completed | `RetrievalContext` 增加 `guide_chunks` 快照字段，非流式与流式响应结构对齐 |
| 2026-04-15 14:17 | 2.2 | completed | `Retriever.retrieve()` 增加 `question_type` 入参，针对 calculation / parameter 类问题条件触发 `DG EN1990` 指南检索 |
| 2026-04-15 14:18 | 3.1 | completed | `generation.py` 改为统一“回答整理助手”提示词，用户 prompt 重组为问题/规范证据/元数据/指南证据，并保留 exact 证据包分区 |
| 2026-04-15 14:18 | 3.2 | completed | `/query` 与 `/query/stream` 同步透传 `guide_chunks/question_type/engineering_context`，done payload 带回完整 retrieval_context |
| 2026-04-15 14:19 | 4.1 | completed | `uv run pytest tests/server/test_generation.py tests/server/test_api.py -q` 通过，结果为 `98 passed` |

---

## 执行备注

> 记录执行过程中的重要说明、决策变更、风险提示等
>
> - `create_package.py` 第一次以错误根路径调用，额外在 `.helloagents/.helloagents/plan/` 下创建了重复方案包；后续执行以正确路径 `.helloagents/plan/202604151404_answer-prompt-guide-context-integration` 为准。
