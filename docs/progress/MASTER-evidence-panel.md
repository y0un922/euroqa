# PDF 证据面板优化 MASTER

## 任务名称

PDF 证据面板视觉重设计 + 匹配逻辑优化

## 任务描述

目标：
- 视觉重设计：现代简洁 Notion 风格（移除冗余标题栏、property chips 元数据、品牌青色高亮、骨架屏、翻译区稳定）
- 匹配优化：修复 FM-9(短条款阈值)、FM-10(反向包含)、FM-6(页码软 boost)、FM-5(部件号匹配)、FM-16(LaTeX 清理)、FM-27(scroll-to-highlight)

## 分析文档

- [架构总览](../analysis/project-overview-evidence-panel.md)
- [模块盘点](../analysis/module-inventory-evidence-panel.md)
- [风险评估](../analysis/risk-assessment-evidence-panel.md)

## 规划文档

- [任务拆解](../plan/task-breakdown-evidence-panel.md)
- [依赖图](../plan/dependency-graph-evidence-panel.md)
- [里程碑](../plan/milestones-evidence-panel.md)

## 阶段摘要表

| Phase | 名称 | 状态 | 完成度 |
| --- | --- | --- | --- |
| 1 | 基础清理 | 待开始 | 0/4 (0%) |
| 2 | 匹配逻辑修复 | 待开始 | 0/6 (0%) |
| 3 | 视觉重设计 | 待开始 | 0/7 (0%) |
| 4 | 打磨与集成 | 待开始 | 0/3 (0%) |

## Phase Checklist

- [ ] Phase 1: 基础清理 (0/4 tasks) [details](./phase-1-foundation.md)
- [ ] Phase 2: 匹配逻辑修复 (0/6 tasks) [details](./phase-2-matching.md)
- [ ] Phase 3: 视觉重设计 (0/7 tasks) [details](./phase-3-visual.md)
- [ ] Phase 4: 打磨与集成 (0/3 tasks) [details](./phase-4-polish.md)

## Current Status

- 当前阶段：Phase 1 — 基础清理
- 当前任务：待开始
- 当前状态：分析和规划已完成，等待用户确认后开始执行

## Next Steps

- Phase 1 的 Lane 1-A (P1-T1, P1-T2) 和 Lane 1-B (P1-T3, P1-T4) 可并行执行
- Phase 2 有 4 个并行通道可同时启动

## 维护约定

- 每次新会话开始时，先读取本文件，再决定继续哪个阶段
- 任何任务完成后，同时更新：
  - 对应 phase 文件中的 checkbox
  - 本文件中的阶段任务计数
  - 本文件中的 Current Status
