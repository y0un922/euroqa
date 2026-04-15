# Phase 4: UI 集成与交互反馈

## 任务清单

- [x] P4-T1 在前端状态层暴露复制/导出动作与反馈状态。（验收：`useEuroQaDemo` 或等价 action 层向 UI 提供单条复制与整会话导出能力；UI 可感知成功、失败、禁用状态；streaming 与空会话边界条件有统一策略）
- [x] P4-T2 在 `frontend/src/components/MainWorkspace.tsx` 中为每条 assistant 回复增加复制按钮与反馈。（验收：仅 assistant 回复展示复制入口；streaming 中的回复不可复制；成功与失败反馈轻量明确，不打断阅读）
- [x] P4-T3 在全局会话级入口增加整会话导出按钮，优先放在 `TopBar`。（验收：空会话时禁用；导出文件命名稳定且可读；不与现有 LLM 设置入口冲突）
- [x] P4-T4 统一 tooltip、aria label、禁用态文案与布局微调。（验收：交互文案清晰；键盘与屏幕阅读器语义完整；不引入明显布局抖动或消息区拥挤）

## Notes

- 推荐并行 lane：
  - Lane A：P4-T2 单条复制 UI
  - Lane B：P4-T3 整会话导出 UI
- `frontend/src/hooks/useEuroQaDemo.ts` 是热点文件，若多人并行实现，需要明确只有一个任务修改该文件。
