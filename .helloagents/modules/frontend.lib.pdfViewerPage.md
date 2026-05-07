# 模块: frontend.lib.pdfViewerPage

## 职责

- 为右侧 PDF 阅读器提供页码夹紧、上一页/下一页计算和导航可用性判断。
- 统一生成 PDF 页码状态，保证当前渲染页 `currentPage` 与页码输入框 `pageInput` 同步。

## 行为规范

- `syncRequestedPdfPage` 接收外部请求页或用户输入页，并按 PDF 总页数夹紧到合法范围。
- `stepPdfPage` 只负责根据方向计算目标页，不直接管理 React 状态。
- `resolvePdfPageState` 是 PDF 阅读器页码状态的统一入口，所有会改变当前页的交互都应通过它同时得到 `currentPage` 和 `pageInput`。
- 总页数未知时，允许请求页大于 1，等 `totalPages` 可用后再夹紧。

## 依赖关系

- 被 `frontend/src/components/PdfEvidenceViewer.tsx` 使用。
- 与 `frontend/src/lib/pdfLocator.ts` 的 `clampPdfPage` 共同保障 PDF 页码边界。
