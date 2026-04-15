# PDF 证据面板优化 — 任务拆解

## 概述

目标：优化右侧 PDF 证据溯源面板，分两个维度：
1. 视觉重设计 — 现代简洁 Notion 风格
2. 匹配逻辑优化 — 提升引用 → PDF 高亮成功率

分 4 个阶段执行，每阶段内并行通道标注于任务旁。每阶段结束时项目处于可运行状态。

---

## Phase 1: Foundation（基础清理）

**阶段目标**: 消除测试基础设施缺陷，删除残留冲突文件，建立安全工作基线。

### P1-T1: 删除 sync-conflict 残留文件

| 字段 | 内容 |
|------|------|
| 优先级 | P0 |
| 工作量 | S |
| 并行通道 | 1-A |
| 依赖 | 无 |

**修改文件**:
- `frontend/src/lib/api.sync-conflict-20260327-143814-MZV26SU.ts` — 删除
- `frontend/src/components/PdfEvidenceViewer.sync-conflict-20260331-154406-MZV26SU.tsx` — 删除

**验收标准**:
- `find frontend/src -name "*.sync-conflict*"` 返回空
- `pnpm run build` 无报错

---

### P1-T2: evidencePanelLayout.test.ts 改为语义断言

| 字段 | 内容 |
|------|------|
| 优先级 | P0 |
| 工作量 | S |
| 并行通道 | 1-A |
| 依赖 | 无 |

**修改文件**: `frontend/src/lib/evidencePanelLayout.test.ts`

**变更描述**: 替换硬编码 `w-[clamp(420px,34vw,560px)]` 断言为三个语义断言：
1. className 包含 `w-[clamp(` — 响应式宽度
2. className 包含 `xl:flex` — 大屏可见
3. className 包含 `hidden` — 小屏默认隐藏

**验收标准**: 测试通过，修改 clamp 最小值不导致测试失败

---

### P1-T3: pdfLocator.test.ts 补充锚点测试

| 字段 | 内容 |
|------|------|
| 优先级 | P1 |
| 工作量 | M |
| 并行通道 | 1-B |
| 依赖 | 无 |

**修改文件**: `frontend/src/lib/pdfLocator.test.ts`

**新增测试**:
1. 短条款文本 "6.1 Actions" 匹配（FM-9 锚点，P2-T2 后变绿）
2. 短 highlight 在长 item 中的反向包含（FM-10 锚点，P2-T3 后变绿）

**验收标准**: 现有 22 个测试全通过，新增 2 个锚点测试有 TODO 注释

---

### P1-T4: citations.test.ts 补充锚点测试

| 字段 | 内容 |
|------|------|
| 优先级 | P1 |
| 工作量 | M |
| 并行通道 | 1-B |
| 依赖 | 无 |

**修改文件**: `frontend/src/lib/citations.test.ts`

**新增测试**:
1. 跨页 source (page="28-29") 匹配引用 "p.29"（FM-6 锚点，P2-T4 后变绿）
2. EN 1997-2 vs EN 1997-1 部件号优先匹配（FM-5 验证）

**验收标准**: 现有 11 个测试全通过

---

**Phase 1 并行通道**

| 通道 | 任务 | 估算 | 合并风险 |
|------|------|------|---------|
| 1-A | P1-T1, P1-T2 | ~1h | 低 |
| 1-B | P1-T3, P1-T4 | ~3h | 低 |

---

## Phase 2: Matching Logic Fixes（匹配逻辑修复）

**阶段目标**: 修复高频匹配失败模式，锚点测试全绿，`highlighted` 命中率可见提升。

### P2-T1: 清理 highlight_text 中的 LaTeX/Markdown 标记（FM-16）

| 字段 | 内容 |
|------|------|
| 优先级 | P0 |
| 工作量 | M |
| 并行通道 | 2-A（后端） |
| 依赖 | P1-T1 |

**修改文件**: `server/core/generation.py`（`_build_highlight_text`）

**变更**: 追加 LaTeX `$$..$$`/`$...$` 剥离 + Markdown `**/**` 强调剥离

**验收标准**: `pytest tests/` 全绿

---

### P2-T2: 降低 isStrongHighlightCandidate 阈值（FM-9）

| 字段 | 内容 |
|------|------|
| 优先级 | P0 |
| 工作量 | M |
| 并行通道 | 2-B |
| 依赖 | P1-T3 |

**修改文件**: `frontend/src/lib/pdfLocator.ts`（`isStrongHighlightCandidate`）

**变更**: 最小长度 12→6，最小 4+字符 token 数 3→2

**验收标准**: P1-T3 锚点测试 1 变绿；`isStrongHighlightCandidate("6.1 Actions")` = true

---

### P2-T3: findBestContainedWindow 增加反向包含检查（FM-10）

| 字段 | 内容 |
|------|------|
| 优先级 | P1 |
| 工作量 | M |
| 并行通道 | 2-B |
| 依赖 | P2-T2 |

**修改文件**: `frontend/src/lib/pdfLocator.ts`（`findBestContainedWindow`）

**变更**: 在正向 `normalizedHighlight.includes(candidate)` 外增加反向 `candidate.includes(normalizedHighlight)`

**验收标准**: P1-T3 锚点测试 2 变绿

---

### P2-T4: page 过滤改为软 boost（FM-6）

| 字段 | 内容 |
|------|------|
| 优先级 | P1 |
| 工作量 | M |
| 并行通道 | 2-C |
| 依赖 | P1-T4 |

**修改文件**: `frontend/src/lib/citations.ts`（`matchCitationToReference`）

**变更**: 删除页码硬过滤 `return null`，改为评分 boost（精确+50 / 范围包含+20 / 不匹配-100）

**验收标准**: P1-T4 跨页锚点测试变绿

---

### P2-T5: 标准 ID 兜底增加前缀匹配（FM-5）

| 字段 | 内容 |
|------|------|
| 优先级 | P1 |
| 工作量 | S |
| 并行通道 | 2-C |
| 依赖 | P2-T4 |

**修改文件**: `frontend/src/lib/citations.ts`

**变更**: stdId 过滤增加 `refStdId.startsWith(citationStdId + "-")` 容错，前缀匹配得分上限 199

**验收标准**: "EN 1997" 能匹配到 EN 1997-1 的 record

---

### P2-T6: 实现 scroll-to-highlight（FM-27）

| 字段 | 内容 |
|------|------|
| 优先级 | P0 |
| 工作量 | L |
| 并行通道 | 2-D |
| 依赖 | P1-T1 |

**修改文件**: `frontend/src/components/PdfEvidenceViewer.tsx`

**变更**: 
1. 添加 scrollContainerRef 和 overlayRef
2. 文本高亮完成后 `mark.scrollIntoView({ behavior: "smooth", block: "center" })`
3. bbox 叠加完成后 `overlayRef.scrollIntoView({ behavior: "smooth", block: "center" })`

**验收标准**: 点击引用后高亮自动出现在视口中部

---

**Phase 2 并行通道**

| 通道 | 任务 | 估算 | 合并风险 |
|------|------|------|---------|
| 2-A | P2-T1 | ~2h | 低 |
| 2-B | P2-T2 → P2-T3 | ~4h | 低 |
| 2-C | P2-T4 → P2-T5 | ~3h | 低 |
| 2-D | P2-T6 | ~6h ★关键路径 | 低 |

---

## Phase 3: Visual Redesign（视觉重设计）

**阶段目标**: Notion 风格面板，所有文本 >= 12px，品牌青色高亮，翻译区无抖动。

### P3-T1: 移除标题栏 + 元数据 chips（V1+V2）

| 字段 | 内容 |
|------|------|
| 优先级 | P0 |
| 工作量 | M |
| 并行通道 | 3-A |
| 依赖 | P2-T6 |

**修改文件**: `EvidencePanel.tsx`

**变更**: 删除 h-14 标题栏(56px)；元数据栏所有字体提升到 text-xs(12px)；property chips 样式

---

### P3-T2: PDF 背景 + 骨架屏（V3+V4）

| 字段 | 内容 |
|------|------|
| 优先级 | P1 |
| 工作量 | S |
| 并行通道 | 3-A |
| 依赖 | P3-T1 |

**修改文件**: `EvidencePanel.tsx`，`PdfEvidenceViewer.tsx`

**变更**: bg-neutral-600 → bg-[#eae9e4]；"Loading PDF..." → 骨架屏 + 中文提示

---

### P3-T3: 翻译区高度稳定（V5）

| 字段 | 内容 |
|------|------|
| 优先级 | P0 |
| 工作量 | S |
| 并行通道 | 3-A |
| 依赖 | P3-T2 |

**修改文件**: `EvidencePanel.tsx`

**变更**: 翻译区 min-h-[40px] + AnimatePresence opacity 过渡

---

### P3-T4: mark 青色样式（V9）

| 字段 | 内容 |
|------|------|
| 优先级 | P1 |
| 工作量 | S |
| 并行通道 | 3-C（独立） |
| 依赖 | P2-T2 |

**修改文件**: `frontend/src/index.css`

**变更**: 追加 `.react-pdf__Page__textContent mark { background-color: rgba(8, 145, 178, 0.25); }`

---

### P3-T5: bbox 淡入动画（V7）

| 字段 | 内容 |
|------|------|
| 优先级 | P2 |
| 工作量 | S |
| 并行通道 | 3-D（独立） |
| 依赖 | P2-T6 |

**修改文件**: `PdfEvidenceViewer.tsx`

**变更**: 叠加层 div → motion.div + opacity 淡入 200ms

---

### P3-T6: 空状态重设计（V6）

| 字段 | 内容 |
|------|------|
| 优先级 | P2 |
| 工作量 | S |
| 并行通道 | 3-A |
| 依赖 | P3-T3 |

**修改文件**: `EvidencePanel.tsx`

**变更**: BookOpen → FileSearch 图标；两行 text-pretty 文案；删除 `<br />`

---

### P3-T7: toggle hover/focus 状态（V10）

| 字段 | 内容 |
|------|------|
| 优先级 | P2 |
| 工作量 | S |
| 并行通道 | 3-A |
| 依赖 | P3-T6 |

**修改文件**: `EvidencePanel.tsx`

**变更**: focus-visible:outline + hover:opacity-90 + disabled:cursor-not-allowed

---

**Phase 3 并行通道**

| 通道 | 任务 | 估算 | 合并风险 |
|------|------|------|---------|
| 3-A | P3-T1→T2→T3→T6→T7（串行） | ~5h ★关键路径 | 中（同文件） |
| 3-C | P3-T4 | ~0.5h | 低 |
| 3-D | P3-T5 | ~1h | 低 |

---

## Phase 4: Polish & Integration

**阶段目标**: 响应式改进，端到端验证，文档更新。

### P4-T1: 响应式抽屉回退（V8）

| 字段 | 内容 |
|------|------|
| 优先级 | P2（可选） |
| 工作量 | L |
| 并行通道 | 4-A |
| 依赖 | Phase 3 全部 |

**修改文件**: `evidencePanelLayout.ts`，`evidencePanelLayout.test.ts`，`EvidencePanel.tsx`，`App.tsx`

**变更**: < xl 时面板以抽屉形式出现；App.tsx 添加 isEvidenceDrawerOpen 本地状态

---

### P4-T2: E2E 集成验证

| 字段 | 内容 |
|------|------|
| 优先级 | P0 |
| 工作量 | M |
| 并行通道 | 4-B |
| 依赖 | Phase 3 全部 |

**验证清单**: 文本引用高亮 + bbox 叠加 + 跨页引用 + 翻译 toggle + mark 颜色 + 无 console.error

---

### P4-T3: 更新分析文档

| 字段 | 内容 |
|------|------|
| 优先级 | P2 |
| 工作量 | S |
| 并行通道 | 4-C |
| 依赖 | P4-T2 |

**修改文件**: `docs/analysis/risk-assessment-evidence-panel.md`，`docs/analysis/module-inventory-evidence-panel.md`

---

## 全局任务汇总

| 任务 ID | 标题 | 优先级 | 工作量 | 通道 | 依赖 | 关键路径 |
|---------|------|-------|--------|------|------|---------|
| P1-T1 | 删除 sync-conflict 文件 | P0 | S | 1-A | — | |
| P1-T2 | layout test 语义断言 | P0 | S | 1-A | — | |
| P1-T3 | pdfLocator 锚点测试 | P1 | M | 1-B | — | ★ |
| P1-T4 | citations 锚点测试 | P1 | M | 1-B | — | |
| P2-T1 | 清理 highlight_text 标记 | P0 | M | 2-A | P1-T1 | |
| P2-T2 | 降低 isStrong 阈值 | P0 | M | 2-B | P1-T3 | ★ |
| P2-T3 | 反向包含检查 | P1 | M | 2-B | P2-T2 | ★ |
| P2-T4 | page 软 boost | P1 | M | 2-C | P1-T4 | |
| P2-T5 | part 号前缀匹配 | P1 | S | 2-C | P2-T4 | |
| P2-T6 | scroll-to-highlight | P0 | L | 2-D | P1-T1 | ★ |
| P3-T1 | 移除标题栏 + 元数据 chips | P0 | M | 3-A | P2-T6 | ★ |
| P3-T2 | PDF 背景 + 骨架屏 | P1 | S | 3-A | P3-T1 | ★ |
| P3-T3 | 翻译区高度稳定 | P0 | S | 3-A | P3-T2 | ★ |
| P3-T4 | mark 青色样式 | P1 | S | 3-C | P2-T2 | |
| P3-T5 | bbox 淡入动画 | P2 | S | 3-D | P2-T6 | |
| P3-T6 | 空状态重设计 | P2 | S | 3-A | P3-T3 | ★ |
| P3-T7 | toggle hover/focus | P2 | S | 3-A | P3-T6 | ★ |
| P4-T1 | 响应式抽屉回退 | P2 | L | 4-A | Phase 3 | ★ |
| P4-T2 | E2E 集成验证 | P0 | M | 4-B | Phase 3 | |
| P4-T3 | 更新分析文档 | P2 | S | 4-C | P4-T2 | |
