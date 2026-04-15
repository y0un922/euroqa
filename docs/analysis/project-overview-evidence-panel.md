# PDF 证据面板优化 — 架构总览

## 任务概述

优化右侧 PDF 证据溯源面板的视觉体验和内容匹配率。

- **视觉目标**: 现代简洁 Notion 风格
- **匹配目标**: 提升引用 → PDF 高亮的成功率

## 技术栈

| 层 | 技术 | 版本 |
|---|---|---|
| UI 框架 | React | 19.0.0 |
| 构建工具 | Vite | 6.2.0 |
| CSS | Tailwind CSS v4 | 4.1.14 (CSS-first, 无 config 文件) |
| PDF 渲染 | react-pdf + pdfjs-dist | 9.2.1 / 4.8.69 |
| 动画 | motion/react (Framer Motion) | 12.23.24 |
| Markdown | react-markdown + remark-gfm + remark-math + rehype-katex | 10.1.0 |
| 图标 | lucide-react | 0.546.0 |
| 测试 | Node.js node:test + node:assert/strict | Node 22 |

## 数据流

```
用户点击引用按钮 → onReferenceClick(referenceId)
  → useEuroQaDemo.setActiveReferenceId
  → 派生 activeReference / activeReferencePdfUrl
  → App.tsx 传递 props 到 EvidencePanel
  → EvidencePanel 传递到 PdfEvidenceViewer
  → react-pdf 渲染页面 + 文本高亮 / bbox 叠加
  → onLocationResolved(status) 回传状态
```

## 端到端匹配管线 (5 阶段)

```
LLM 内联引用文本 → citations.ts 匹配 → ReferenceRecord 查找
  → PdfEvidenceViewer 渲染页面
  → pdfLocator.ts 文本匹配 OR bbox 叠加
  → PDF 文本层高亮
```

## 核心模块

| 文件 | 职责 | 行数 | 复杂度 |
|---|---|---|---|
| EvidencePanel.tsx | 右侧面板主容器(三层布局) | 229 | 中 |
| PdfEvidenceViewer.tsx | PDF 渲染 + 高亮 + bbox | 203 | 高 |
| pdfLocator.ts | PDF 文本匹配算法 | 264 | 高 |
| citations.ts | 引用 → 参考源匹配 | 385 | 高 |
| inlineReferences.ts | 引用徽章生成 | 70 | 低 |
| evidencePanelLayout.ts | 面板响应式布局 | 14 | 低 |
| evidenceDebug.ts | 调试字段提取 | 155 | 低 |
| useEuroQaDemo.ts | 全局状态管理(god-hook) | 630 | 极高 |
| types.ts | 共享类型定义 | 150 | 低 |

## 后端数据源

| 端点 | 用途 |
|---|---|
| POST /api/v1/query/stream | 问答 + sources 返回 |
| GET /api/v1/documents/{id}/file | PDF 文件下载 |
| POST /api/v1/sources/translate | 源翻译 |

Source 对象关键字段: `file`, `document_id`, `element_type`, `bbox` [x0,y0,x1,y1] (0-1000), `page`, `clause`, `original_text`, `highlight_text`, `locator_text`
