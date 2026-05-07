# 模块: frontend.components.EvidencePanel

## 职责

- 展示当前引用来源的文件、章节、页码和置信度
- 展示来源原文与 `source.translation`
- 展示关联引用和文档页预览

## 行为规范

- 组件本身不生成翻译，只消费 `activeReference.source.translation`
- 当 `translation` 为空时显示“暂无翻译”
- `translation` 改为按 `ReactMarkdown + remark-gfm` 渲染，因此表格、列表和段落会按 Markdown 结构展示
- 不直接插入 HTML，避免把后端译文展示能力与原始 HTML 绑定
- `original_text`、`highlight_text`、`locator_text` 在右侧“定位文本对照”区域必须保留为各自独立视图，但默认通过单卡片内的标签切换查看，避免在窄侧栏里同时堆叠导致主 PDF 区被挤压
- 调试视图的标题、说明文案、标签顺序和内容高度策略由 `frontend/src/lib/evidenceDebug.ts` 提供，`EvidencePanel` 只负责按当前激活标签渲染单个视图
- 右侧 PDF 阅读器的页码显示由 `PdfEvidenceViewer` 内部状态控制；上一页/下一页、页码输入提交和引用定位页同步必须同时更新当前渲染页与页码输入框显示，避免用户翻页后顶部页码滞后。

## 依赖关系

- 依赖 `frontend/src/lib/types.ts` 中的 `ReferenceRecord`
- 依赖 `frontend/src/lib/pdfViewerPage.ts` 统一解析 PDF 当前页和页码输入状态
- 依赖后端 `/api/v1/query` 与 `/api/v1/query/stream` 返回的 `Source.translation`
- 依赖 `react-markdown` 和 `remark-gfm` 渲染中文解释
- 依赖 `frontend/src/lib/evidenceDebug.ts` 生成定位文本对照卡片元数据
