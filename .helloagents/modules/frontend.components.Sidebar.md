# 模块: frontend.components.Sidebar

## 职责

- 展示左侧文档导航、上传入口、热门问题和术语预览
- 提供“新建检索会话”按钮，用于清空当前页内消息与引用状态

## 行为规范

- 侧边栏不再展示“最近提问”或任何本地 history 恢复入口。
- “新建检索会话”只清空当前页内状态，不依赖浏览器持久化。
- 文档列表继续负责高亮当前选中文档，并在处理中的文档上展示状态与进度。

## 依赖关系

- 依赖 `frontend/src/components/DocumentUpload.tsx` 提供文档上传入口
- 依赖 `frontend/src/components/DocumentStatusBadge.tsx` 展示文档处理状态
- 依赖 `frontend/src/hooks/useEuroQaDemo.ts` 提供当前页内的新建会话和文档选择回调
