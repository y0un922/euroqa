# Phase 2: 匹配逻辑修复

## 阶段目标

修复高频匹配失败模式，锚点测试全绿，`highlighted` 命中率可见提升。

## 并行通道

| 通道 | 任务 | 合并风险 |
|------|------|---------|
| 2-A | P2-T1 (后端) | 低 |
| 2-B | P2-T2 → P2-T3 (pdfLocator) | 低 |
| 2-C | P2-T4 → P2-T5 (citations) | 低 |
| 2-D | P2-T6 (PdfEvidenceViewer) ★关键路径 | 低 |

## 任务清单

### Lane 2-A (后端)

- [ ] **P2-T1**: 清理 highlight_text 中的 LaTeX/Markdown 标记 (FM-16)
  - 文件: `server/core/generation.py` (`_build_highlight_text`)
  - 追加 LaTeX `$$..$$` 和 Markdown `**` 剥离
  - 验证: `pytest tests/` 全绿

### Lane 2-B (pdfLocator)

- [ ] **P2-T2**: 降低 isStrongHighlightCandidate 阈值 (FM-9)
  - 文件: `frontend/src/lib/pdfLocator.ts`
  - 最小长度 12→6，最小 4+token 数 3→2
  - 验证: P1-T3 锚点测试 1 变绿

- [ ] **P2-T3**: findBestContainedWindow 反向包含检查 (FM-10)
  - 文件: `frontend/src/lib/pdfLocator.ts`
  - 增加 `candidate.includes(normalizedHighlight)` 检查
  - 验证: P1-T3 锚点测试 2 变绿

### Lane 2-C (citations)

- [ ] **P2-T4**: page 过滤改为软 boost (FM-6)
  - 文件: `frontend/src/lib/citations.ts`
  - 删除硬过滤，改为评分 boost (+50/+20/-100)
  - 验证: P1-T4 跨页锚点测试变绿

- [ ] **P2-T5**: 标准 ID 兜底增加前缀匹配 (FM-5)
  - 文件: `frontend/src/lib/citations.ts`
  - 增加 `refStdId.startsWith(citationStdId + "-")` 容错
  - 验证: "EN 1997" 能匹配 EN 1997-1

### Lane 2-D (scroll-to-highlight) ★关键路径

- [ ] **P2-T6**: 实现 scroll-to-highlight (FM-27)
  - 文件: `frontend/src/components/PdfEvidenceViewer.tsx`
  - 添加 scrollContainerRef + mark.scrollIntoView + overlayRef.scrollIntoView
  - 验证: 高亮自动出现在视口中部

## 阶段验收

- [ ] 所有 Phase 1 锚点测试全绿
- [ ] `pnpm run test` 全通过
- [ ] `pytest tests/` 全绿
- [ ] `pnpm run build` 无报错
