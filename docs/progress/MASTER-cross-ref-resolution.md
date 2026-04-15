# 交叉引用解析专项 MASTER

## 任务名称

规范内部交叉引用解析与证据闭环

## 任务描述

目标：

- 稳定解析规范内部 `Table / Figure / Expression / Clause` 引用
- 在线检索时自动补齐被引对象
- exact 模式下建立“证据闭环”闸门
- 避免无用噪音片段替代真正被引对象
- 为生产上线提供评测、灰度、回滚方案

## 分析文档

- [架构总览](../analysis/project-overview-cross-ref-resolution.md)
- [模块盘点](../analysis/module-inventory-cross-ref-resolution.md)
- [风险评估](../analysis/risk-assessment-cross-ref-resolution.md)

## 规划文档

- [任务拆解](../plan/task-breakdown-cross-ref-resolution.md)
- [依赖图](../plan/dependency-graph-cross-ref-resolution.md)
- [里程碑](../plan/milestones-cross-ref-resolution.md)

## 阶段摘要表

| Phase | 名称 | 状态 | 完成度 |
| --- | --- | --- | --- |
| 1 | 引用对象模型与离线引用图 | 已完成 | 5/5 (100%) |
| 2 | 在线 deterministic resolver | 已完成 | 4/4 (100%) |
| 3 | 生成层证据闸门 | 进行中 | 3/4 (75%) |
| 4 | 专项评测与回归门禁 | 进行中 | 3/4 (75%) |
| 5 | 上线与灰度 | 待开始 | 0/4 (0%) |

## Phase Checklist

- [x] Phase 1: 引用对象模型与离线引用图 (5/5 tasks) [details](./phase-1-reference-graph.md)
- [x] Phase 2: 在线 deterministic resolver (4/4 tasks) [details](./phase-2-online-resolution.md)
- [ ] Phase 3: 生成层证据闸门 (3/4 tasks) [details](./phase-3-evidence-gate.md)
- [ ] Phase 4: 专项评测与回归门禁 (3/4 tasks) [details](./phase-4-eval-guardrail.md)
- [ ] Phase 5: 上线与灰度 (0/4 tasks) [details](./phase-5-rollout.md)

## Current Status

- 当前阶段：Phase 4 — 专项评测与回归门禁
- 当前任务：P4-T4 基线对比与验收
- 当前状态：真实索引环境下已确认 `3.1.7 -> Table 3.1` 与 `Table 3.1` 直查都可达到 `grounded`；剩余工作是刷新完整 `eval_results.json` 基线并继续压低噪音召回

## Next Steps

- 在真实索引环境运行 `tests/eval/eval_retrieval.py`，刷新 `eval_results.json`
- 对比 Phase 4 新指标，确认 `direct_ref_resolution_rate / reference_closure_rate / noise_intrusion_rate`
- 任何实现开始前，先读取本文件和对应 phase 文件

## 维护约定

- 每次新会话先读取本文件
- 任一任务完成后，同时更新：
  - 对应 phase 文件 checkbox
  - 本文件中的完成度
  - 本文件中的 Current Status
