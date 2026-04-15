# 任务清单: frontend-en1992-copy-refresh

> **@status:** completed | 2026-04-01 20:39

```yaml
@feature: frontend-en1992-copy-refresh
@created: 2026-04-01
@status: completed
@mode: R2
```

<!-- LIVE_STATUS_BEGIN -->
状态: completed | 进度: 3/3 (100%) | 更新: 2026-04-01 20:39:21
当前: 已完成实现、验证与知识库同步，准备归档
<!-- LIVE_STATUS_END -->

## 进度概览

| 完成 | 失败 | 跳过 | 总数 |
|------|------|------|------|
| 3 | 0 | 0 | 3 |

---

## 任务列表

### 1. 建议问题与默认引导

- [√] 1.1 在 `server/api/v1/glossary.py` 中更新 `/suggest` 的热门问题，并清理明显过期的默认领域描述 | depends_on: []
- [√] 1.2 在 `frontend/src/components/MainWorkspace.tsx` 中更新欢迎区、推荐问题区和输入框示例文案，使其匹配当前 EN 1992-1-1:2004 文档语境 | depends_on: [1.1]

### 2. 测试验证

- [√] 2.1 在 `tests/server/test_api.py` 中更新 `/api/v1/suggest` 的断言，并执行针对性测试验证 | depends_on: [1.1]

---

## 执行日志

| 时间 | 任务 | 状态 | 备注 |
|------|------|------|------|
| 2026-04-01 20:35:40 | 1.1 | completed | `/api/v1/suggest` 热门问题与 domains 切换到当前 EN 1992-1-1 文档 |
| 2026-04-01 20:36:20 | 1.2 | completed | 首页欢迎区、推荐问题和输入框示例文案改为当前 PDF 语境 |
| 2026-04-01 20:39:21 | 2.1 | completed | `uv run pytest tests/server/test_api.py -q -k test_suggest` 通过，`pnpm --dir frontend lint` 和 `pnpm --dir frontend build` 通过 |

---

## 执行备注

- 保持现有前后端数据流，不在组件内部新增写死问题列表。
- 改动范围限定为展示文案和建议问题，不触及检索、解析、会话持久化和 PDF 预览逻辑。
