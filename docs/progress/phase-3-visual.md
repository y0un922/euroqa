# Phase 3: 视觉重设计

## 阶段目标

Notion 风格面板，所有文本 >= 12px，品牌青色高亮，翻译区无抖动。

## 并行通道

| 通道 | 任务 | 合并风险 |
|------|------|---------|
| 3-A | P3-T1→T2→T3→T6→T7 (EvidencePanel 串行) ★关键路径 | 中 |
| 3-C | P3-T4 (index.css) | 低 |
| 3-D | P3-T5 (PdfEvidenceViewer) | 低 |

## 任务清单

### Lane 3-A (EvidencePanel 串行链)

- [ ] **P3-T1**: 移除标题栏 + 元数据 property chips (V1+V2)
  - 删除 h-14 标题栏(56px)
  - 所有字体提升到 text-xs(12px)
  - property chips 样式

- [ ] **P3-T2**: PDF 背景色替换 + 骨架屏 (V3+V4)
  - bg-neutral-600 → bg-[#eae9e4]
  - "Loading PDF..." → 骨架屏 + 中文

- [ ] **P3-T3**: 翻译区高度稳定 (V5)
  - min-h-[40px] + AnimatePresence opacity 过渡

- [ ] **P3-T6**: 空状态重设计 (V6)
  - BookOpen → FileSearch；text-pretty 文案

- [ ] **P3-T7**: toggle hover/focus (V10)
  - focus-visible:outline + hover:opacity-90

### Lane 3-C (独立)

- [ ] **P3-T4**: mark 青色样式 (V9)
  - 文件: `frontend/src/index.css`
  - `.react-pdf__Page__textContent mark { background-color: rgba(8, 145, 178, 0.25) }`

### Lane 3-D (独立)

- [ ] **P3-T5**: bbox 叠加层淡入动画 (V7)
  - 文件: `PdfEvidenceViewer.tsx`
  - div → motion.div + opacity 淡入 200ms

## 阶段验收

- [ ] 无独立标题栏
- [ ] 所有元数据 >= 12px
- [ ] PDF 背景暖浅灰
- [ ] 骨架屏 + 中文加载提示
- [ ] 翻译切换无 PDF 抖动
- [ ] mark 青色高亮
- [ ] bbox 淡入动画
- [ ] 空状态 FileSearch 图标
- [ ] toggle 有 focus ring
- [ ] `pnpm run test` 全绿
- [ ] `pnpm run build` 无报错
