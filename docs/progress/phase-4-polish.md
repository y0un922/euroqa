# Phase 4: 打磨与集成

## 阶段目标

响应式改进，端到端验证，文档更新。

## 并行通道

| 通道 | 任务 | 合并风险 |
|------|------|---------|
| 4-A | P4-T1 (响应式抽屉，可选) | 高 |
| 4-B | P4-T2 (E2E 验证) | 无 |
| 4-C | P4-T3 (文档更新) | 低 |

## 任务清单

### Lane 4-A (可选)

- [ ] **P4-T1**: 响应式抽屉回退 (V8)
  - 文件: evidencePanelLayout.ts, EvidencePanel.tsx, App.tsx
  - < xl 时面板以抽屉形式出现
  - App.tsx 添加 isEvidenceDrawerOpen 本地状态

### Lane 4-B

- [ ] **P4-T2**: E2E 集成验证
  - 文本引用 → 高亮定位 + 自动滚动
  - bbox 引用 → 叠加层 + 淡入
  - 跨页引用 → "已定位并高亮"
  - 翻译 toggle → 无抖动
  - mark 颜色 → 青色
  - 无 console.error

### Lane 4-C

- [ ] **P4-T3**: 更新分析文档
  - risk-assessment 标记已修复项
  - module-inventory 更新描述

## 阶段验收

- [ ] E2E 验证清单全部通过
- [ ] 无 console.error
- [ ] `pnpm run test` 全绿
- [ ] `pytest tests/` 全绿
- [ ] 分析文档已更新
