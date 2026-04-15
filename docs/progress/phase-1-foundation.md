# Phase 1: 基础清理

## 阶段目标

消除测试基础设施缺陷，删除残留冲突文件，建立安全工作基线。

## 并行通道

| 通道 | 任务 | 合并风险 |
|------|------|---------|
| 1-A | P1-T1, P1-T2 | 低 |
| 1-B | P1-T3, P1-T4 | 低 |

## 任务清单

### Lane 1-A

- [ ] **P1-T1**: 删除 sync-conflict 残留文件
  - 删除 `api.sync-conflict-*.ts` 和 `PdfEvidenceViewer.sync-conflict-*.tsx`
  - 验证: `find frontend/src -name "*.sync-conflict*"` 返回空

- [ ] **P1-T2**: evidencePanelLayout.test.ts 改为语义断言
  - 替换硬编码宽度断言为语义检查
  - 验证: clamp 最小值修改不导致测试失败

### Lane 1-B

- [ ] **P1-T3**: pdfLocator.test.ts 补充锚点测试
  - 新增: 短条款 "6.1 Actions" 匹配测试 (FM-9 锚点)
  - 新增: 反向包含测试 (FM-10 锚点)
  - 验证: 现有 22 个测试全通过

- [ ] **P1-T4**: citations.test.ts 补充锚点测试
  - 新增: 跨页 source 匹配测试 (FM-6 锚点)
  - 新增: 部件号优先匹配测试 (FM-5 验证)
  - 验证: 现有 11 个测试全通过

## 阶段验收

- [ ] `pnpm run build` 无 TypeScript 报错
- [ ] `pnpm run test` 所有现有测试通过
- [ ] 无 sync-conflict 残留文件
