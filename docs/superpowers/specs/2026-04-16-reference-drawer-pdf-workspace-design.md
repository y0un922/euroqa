# PDF Workspace With Reference Drawer Design

## Goal

将前端右侧证据区改造成以整页 PDF 阅读为主的工作区，并把原有固定底部译文栏改为右上角按钮触发的底部抽屉。抽屉仅在选中引用后展示，覆盖在 PDF 上方，支持显示原文与翻译，并允许用户上下拖动调整高度。

## Context

- 当前 [EvidencePanel](/Volumes/software/webdav/Euro_QA/frontend/src/components/EvidencePanel.tsx) 采用三段式固定布局：元数据头、PDF 预览区、底部译文栏。
- 当前 [PdfEvidenceViewer](/Volumes/software/webdav/Euro_QA/frontend/src/components/PdfEvidenceViewer.tsx) 以“定位片段”为中心，保留了 bbox/text 高亮逻辑。
- 参考实现位于 `Euro_QA_pageindex/frontend`，其中 PDF 区已经切换到整页阅读器模式，抽屉思路需结合现有项目的翻译状态流补齐。

## User Experience

### Visual Thesis

右侧是安静、连续的 PDF 阅读平面，引用详情只在需要时像证据卡一样浮现在底部。

### Interaction Thesis

- 右上角引用按钮是唯一入口，避免右侧区域同时出现多套控制条。
- 底部抽屉覆盖在 PDF 上方，不推动 PDF 重排。
- 抽屉顶部提供拖拽把手，用户可在最小和最大高度之间连续调整。

## Layout Contract

### Closed State

- 右侧面板始终显示整页 PDF 阅读器。
- 右上角显示引用按钮。
- 未选中引用时不显示抽屉内容，按钮保持可见但不展开内容。

### Open State

- 当用户点击回答中的引用并形成 `activeReference` 时，抽屉默认展开。
- 抽屉锚定在面板底部，覆盖在 PDF 上方。
- 抽屉内容区分为：
  - 引用头部：文档名、条款、页码
  - 操作区：复制原文、翻译开关/关闭
  - 内容区：原文卡片、翻译卡片

## Component Design

### EvidencePanel

- 保留为右侧主入口组件，但从“三层固定布局”改为“PDF 主体 + 右上角按钮 + 底部抽屉覆盖层”。
- 负责管理：
  - 抽屉开合
  - 抽屉高度
  - 拖拽状态
  - 复制原文行为
- 继续消费现有的 `activeReference`、`sourceTranslationEnabled`、`sourceTranslation`、`sourceTranslationLoading`、`sourceTranslationError`。

### PdfEvidenceViewer

- 切换为整页 PDF 阅读器模式，直接参考 `Euro_QA_pageindex` 的页码导航实现。
- 保留 `page` 作为初始定位页，但不再承担引用级高亮呈现。
- 提供：
  - 上一页/下一页
  - 页码输入
  - 总页数展示

### New Drawer Layout Utility

- 新增一个前端工具模块，负责：
  - 计算默认抽屉高度
  - 根据容器高度夹紧最小/最大高度
  - 将拖拽位移转换为抽屉最终高度
- 这部分单独测试，避免把交互边界判断塞进 JSX。

## Behavior Rules

- 当 `activeReference` 从空变为非空时，抽屉自动展开并恢复默认高度。
- 当 `activeReference` 变化但仍存在时，抽屉保持打开，只刷新标题和内容。
- 当用户关闭抽屉时，不清空 `activeReference`，仅隐藏详情层。
- 翻译关闭时仍显示原文卡片；翻译区显示“翻译已关闭”而不是完全消失。
- 拖拽高度必须有边界，避免抽屉覆盖掉几乎全部 PDF。

## File Impact

- Modify: [frontend/src/components/EvidencePanel.tsx](/Volumes/software/webdav/Euro_QA/frontend/src/components/EvidencePanel.tsx)
- Modify: [frontend/src/components/PdfEvidenceViewer.tsx](/Volumes/software/webdav/Euro_QA/frontend/src/components/PdfEvidenceViewer.tsx)
- Create: [frontend/src/lib/evidencePanelPdf.ts](/Volumes/software/webdav/Euro_QA/frontend/src/lib/evidencePanelPdf.ts)
- Create: [frontend/src/lib/pdfViewerPage.ts](/Volumes/software/webdav/Euro_QA/frontend/src/lib/pdfViewerPage.ts)
- Create: [frontend/src/lib/evidenceDrawerLayout.ts](/Volumes/software/webdav/Euro_QA/frontend/src/lib/evidenceDrawerLayout.ts)
- Create: [frontend/src/lib/evidenceDrawerLayout.test.ts](/Volumes/software/webdav/Euro_QA/frontend/src/lib/evidenceDrawerLayout.test.ts)
- Create: [frontend/src/components/EvidencePanel.test.tsx](/Volumes/software/webdav/Euro_QA/frontend/src/components/EvidencePanel.test.tsx)

## Validation

- 单元测试覆盖抽屉高度计算和 PDF payload/page 导航工具。
- 静态渲染测试覆盖：
  - 有引用时渲染右上角按钮和抽屉主要文案
  - 无引用时不渲染抽屉内容
- 运行 `frontend` 的 `test` 与 `lint`。
