# PDF 证据面板优化 — 里程碑

## 概览

| 里程碑 | 阶段 | 估算累计 |
|--------|------|---------|
| M1: 干净基线 | Phase 1 | ~3h |
| M2: 匹配修复验证 | Phase 2 | ~9h |
| M3: 视觉重设计完成 | Phase 3 | ~14h |
| M4: 交付 | Phase 4 | ~19h |

---

## M1: 干净基线

| # | 检查项 | 验证方式 |
|---|--------|---------|
| 1 | sync-conflict 文件已删除 | `find frontend/src -name "*.sync-conflict*"` 返回空 |
| 2 | layout test 使用语义断言 | 代码审查 |
| 3 | pnpm run test 全绿 | 终端输出 |
| 4 | 新增 pdfLocator 锚点测试存在 | 代码审查 |
| 5 | 新增 citations 锚点测试存在 | 代码审查 |

---

## M2: 匹配修复验证

| # | 检查项 | 验证方式 |
|---|--------|---------|
| 1 | FM-9: 短条款 "6.1 Actions" 匹配通过 | pdfLocator 锚点测试绿 |
| 2 | FM-10: 反向包含检查通过 | pdfLocator 锚点测试绿 |
| 3 | FM-6: 跨页 source 匹配通过 | citations 锚点测试绿 |
| 4 | FM-16: highlight_text 无 LaTeX 残留 | pytest 绿 |
| 5 | FM-27: scroll-to-highlight 工作 | 目视验证 |
| 6 | 所有 22 个 pdfLocator 测试通过 | pnpm run test |
| 7 | 所有 11 个 citations 测试通过 | pnpm run test |
| 8 | pytest tests/ 全绿 | pytest |
| 9 | pnpm run build 无报错 | 终端输出 |

---

## M3: 视觉重设计完成

| # | 检查项 | 验证方式 |
|---|--------|---------|
| 1 | V1: 无独立标题栏 | 目视 |
| 2 | V2: 所有元数据 >= 12px | DevTools |
| 3 | V2: property chips 样式 | 目视 |
| 4 | V3: PDF 背景暖浅灰 | DevTools |
| 5 | V4: 骨架屏 + 中文提示 | 目视 |
| 6 | V5: 翻译切换无抖动 | 目视 |
| 7 | V6: FileSearch 空状态 | 目视 |
| 8 | V7: bbox 淡入动画 | 目视 |
| 9 | V9: mark 青色高亮 | DevTools |
| 10 | V10: toggle focus ring | 键盘导航 |
| 11 | pnpm run test 全绿 | 终端输出 |
| 12 | pnpm run build 无报错 | 终端输出 |

---

## M4: 交付

| # | 检查项 | 优先级 | 验证方式 |
|---|--------|-------|---------|
| 1 | E2E 引用点击→高亮流程 | P0 | P4-T2 验证清单 |
| 2 | 无 console.error | P0 | F12 控制台 |
| 3 | 跨页引用显示 "已定位并高亮" | P0 | 目视 |
| 4 | 分析文档已更新 | P2 | 代码审查 |
| 5 | 响应式抽屉（可选）| P2 | 窗口缩小至 1024px |
| 6 | pnpm run test 全绿 | P0 | 终端输出 |
| 7 | pytest tests/ 全绿 | P0 | 终端输出 |

---

## 降级条件

| 风险 | 降级处理 |
|------|---------|
| P2-T6 超出 8h | scroll-to-highlight 移入 M4，M3 不受影响 |
| P3-Lane-A 引入回归 | 回滚到最近绿色提交，单步重做 |
| P4-T1 需修改 god-hook | 推迟到下个迭代，M4 不含 P4-T1 |
