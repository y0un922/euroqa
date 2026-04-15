# 任务清单: citation-anchor-ui

> **@status:** completed | 2026-03-28 18:21

```yaml
@feature: citation-anchor-ui
@created: 2026-03-28
@status: completed
@mode: R3
```

<!-- LIVE_STATUS_BEGIN -->
状态: completed | 进度: 6/6 (100%) | 更新: 2026-03-28 18:25:00
当前: 已完成代码实现、验证与知识库同步，等待归档
<!-- LIVE_STATUS_END -->

## 进度概览

| 完成 | 失败 | 跳过 | 总数 |
|------|------|------|------|
| 6 | 0 | 0 | 6 |

---

## 任务列表

### 1. 测试与引用链路

- [√] 1.1 在 `frontend/src/lib/citations.test.ts` 中补充 `EN 1990:2002 · A1.2.1(4)` 这类 plain citation 的回归测试 | depends_on: []
- [√] 1.2 在 `frontend/src/lib/inlineReferences.test.ts` 中补充正文引用编号映射与未命中提示的失败测试 | depends_on: []

### 2. 前端实现

- [√] 2.1 在 `frontend/src/lib/inlineReferences.ts` 中实现正文引用编号与提示元数据组装逻辑 | depends_on: [1.2]
- [√] 2.2 在 `frontend/src/components/MainWorkspace.tsx` 中将正文长文本引用芯片替换为紧凑编号锚点，并为“引用来源”列表加入一致的编号徽标 | depends_on: [1.1, 2.1]

### 3. 验证与同步

- [√] 3.1 运行 `npm test` 验证前端引用识别与渲染辅助逻辑 | depends_on: [2.2]
- [√] 3.2 更新 `.helloagents/modules/frontend.components.MainWorkspace.md` 与 `.helloagents/CHANGELOG.md` 记录本次引用渲染调整 | depends_on: [3.1]

---

## 执行日志

| 时间 | 任务 | 状态 | 备注 |
|------|------|------|------|
| 2026-03-28 18:12:00 | package | completed | 已创建方案包并确认采用轻量编号锚点方案 |
| 2026-03-28 18:16:00 | 1.1 / 1.2 | completed | 新增附件子条款回归测试与编号锚点元数据测试 |
| 2026-03-28 18:19:00 | 2.1 / 2.2 | completed | 新增 inlineReferences 辅助模块并切换正文引用渲染 |
| 2026-03-28 18:23:00 | 3.1 | completed | `npm test`、`npm run lint`、`npm run build` 全部通过 |
| 2026-03-28 18:25:00 | 3.2 | completed | 已同步 MainWorkspace 模块文档与 CHANGELOG |

---

## 执行备注

- TASK_COMPLEXITY: simple
- WORKFLOW_MODE: INTERACTIVE
- 先写失败测试，再修改生产代码与样式
- `npm run build` 仅提示前端 chunk 体积告警，未阻断构建
