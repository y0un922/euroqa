# 任务清单: source-translation-panel

> **@status:** completed | 2026-03-27 16:53

```yaml
@feature: source-translation-panel
@created: 2026-03-27
@status: completed
@mode: R2
```

<!-- LIVE_STATUS_BEGIN -->
状态: completed | 进度: 4/4 (100%) | 更新: 2026-03-27 16:55:00
当前: 开发实施完成，待迁移归档
<!-- LIVE_STATUS_END -->

## 进度概览

| 完成 | 失败 | 跳过 | 总数 |
|------|------|------|------|
| 4 | 0 | 0 | 4 |

---

## 任务列表

### 1. 后端生成链路

- [√] 1.1 在 `server/core/generation.py` 中实现 source 翻译补齐辅助逻辑，并为流式 `done` 事件生成中文解释 | depends_on: []
- [√] 1.2 在 `server/core/generation.py` 中统一非流式返回的空 `translation` 回填行为 | depends_on: [1.1]

### 2. 测试与展示验证

- [√] 2.1 在 `tests/server/test_generation.py` 中补充流式 source translation 与空翻译回填测试 | depends_on: [1.1, 1.2]
- [√] 2.2 验证 `frontend/src/components/EvidencePanel.tsx` 展示链路可直接消费补齐后的 `translation`，如无必要不改 UI 结构 | depends_on: [1.1]

---

## 执行日志

| 时间 | 任务 | 状态 | 备注 |
|------|------|------|------|
| 2026-03-27 16:43:00 | 方案包初始化 | completed | 已创建 proposal.md 与 tasks.md |
| 2026-03-27 16:45:00 | 方案设计 | completed | 确认采用后端补 translation、前端直接消费的最小方案 |
| 2026-03-27 16:50:00 | 1.1-1.2 | completed | 已在 generation.py 增加 source translation 补齐逻辑，并接入流式/非流式链路 |
| 2026-03-27 16:52:00 | 2.1 | completed | `uv run pytest tests/server/test_generation.py -q` 通过 |
| 2026-03-27 16:54:00 | 2.2 | completed | 确认 EvidencePanel 直接消费 `source.translation`；`pnpm --dir frontend test` 通过 |

---

## 执行备注

> 记录执行过程中的重要说明、决策变更、风险提示等

- 当前问题根因位于后端流式链路，不是前端渲染缺失。
- 若翻译补齐实现带来明显尾延迟，需要在本次实现中保留失败兜底与长度限制。
- 本次未调整 `frontend/src/components/EvidencePanel.tsx` 结构，仅修复后端数据供给。
