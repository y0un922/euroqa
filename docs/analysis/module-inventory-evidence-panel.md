# PDF 证据面板优化 — 模块盘点

## 前端模块

### 组件层

#### EvidencePanel.tsx (229行)
- 三层布局: 元数据头 → PDF 查看器(flex-1) → 翻译栏
- 10 个 props, 全部来自 useEuroQaDemo
- 状态徽章: highlighted(绿) / page_only(黄) / error(红)
- 翻译开关: 手工实现的 toggle 按钮

#### PdfEvidenceViewer.tsx (203行)
- react-pdf Document + Page 渲染
- 双路径高亮: bbox CSS 叠加层(table/formula/image) / 文本层 mark 注入(text)
- 5 值复合 key 强制 remount: `${fileUrl}:${safePage}:${normalizedTarget}:${elementType}:${bbox}`
- 通过 refs 管理状态(避免 react-pdf 回调闭包问题)

### 匹配逻辑层

#### citations.ts (385行)
- `linkifyReferenceCitations`: 将 markdown 引用转为可点击链接
- `matchCitationToReference`: 多层评分匹配
  - Tier 1: 解析引用部分(file/clause/page)
  - Tier 2: 归一化
  - Tier 3: 评分(文件匹配→页码+50→条款精确+1000/前缀+700)
  - Tier 4: 回退(全文匹配→同标准ID)

#### pdfLocator.ts (264行)
- `normalizePdfText`: NFKC + 软连字符 + 破折号统一 + PDF 换行连字符合并
- `findPdfHighlightItemIndexes`: 两步匹配(直接 indexOf + 最佳窗口包含)
- `bboxToOverlayStyle`: 0-1000 坐标 → CSS 百分比
- `isStrongHighlightCandidate`: 过滤弱候选(≥12字符或≥3个4+字符token)

#### inlineReferences.ts (70行)
- 匹配引用: 蓝色圆形编号徽章
- 未匹配引用: 灰色矩形条款文本徽章

### 布局与样式层

#### evidencePanelLayout.ts (14行)
- `clamp(420px, 34vw, 560px)` 宽度
- `xl:flex hidden` — 1280px 以下完全隐藏

#### index.css (45行)
- Tailwind v4 @theme 字体定义
- body 背景 #f7f6f3
- 无自定义 mark 样式(使用浏览器默认黄色)

## 后端模块

#### generation.py — Source 构建
- `_build_sources_from_chunks`: 从检索 chunk 构建 Source 列表
- `_build_locator_text`: 截断到 240 字符(按空格边界)
- `_build_highlight_text`: 去除 [-> Table] 等标记, 保留全文
- `_resolve_table_source_geometry`: 运行时表格 bbox 匹配(评分 ≥ 5)

#### content_list.py — Bbox 提取
- `resolve_section_page_metadata`: 从 MinerU content_list 提取 bbox
- `_find_first_body_entry`: 查找标题后首个正文条目的 bbox
- `_validate_bbox`: 验证 4 浮点数, 范围 0-1000

#### chunk.py — Bbox 传播
- 子 chunk: 使用自身 bbox
- 父 chunk: 使用第一个子 chunk 的 bbox (问题!)
- 特殊元素: 使用自身 bbox, 回退到父节区 bbox

## 测试覆盖

| 测试文件 | 测试数 | 覆盖范围 |
|---|---|---|
| citations.test.ts | 11 | 基本匹配, 但缺少页码过滤/多部件标准等 |
| pdfLocator.test.ts | 22 | 归一化/连字符/窗口匹配, 但缺少短条款/反向包含 |
| inlineReferences.test.ts | ~5 | 基本徽章生成 |
| evidenceDebug.test.ts | ~5 | 调试字段构建 |
| evidencePanelLayout.test.ts | 1 | 宽度断言(硬编码字符串) |
