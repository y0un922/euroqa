# Phase 5: 回归验证与交付收口

## 任务清单

- [x] P5-T1 补齐后端回归测试。（验收：`tests/server/test_api.py` 覆盖 `/query` 与 `/query/stream` 新字段；`tests/server/test_generation.py` 覆盖 retrieval context builder 与空值行为）
- [x] P5-T2 补齐前端回归测试。（验收：`frontend/src/lib/api.test.ts` 覆盖 stream done 新字段；`frontend/src/lib/session.test.ts` 覆盖新旧 session 迁移；新增导出器测试覆盖单条与整会话 Markdown 输出）
- [ ] P5-T3 执行人工验证清单并记录边界行为。（验收：验证流式成功路径、流式失败后 fallback 非流式路径、刷新后恢复会话、单条复制内容正确、整会话导出内容正确）

## Notes

- 推荐并行 lane：
  - Lane A：P5-T1 后端测试
  - Lane B：P5-T2 前端测试
- 人工验证应在自动化测试通过后进行，避免把实现缺陷误判为交互问题。
