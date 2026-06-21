# 模块: frontend.components.KnowledgeBasesPage

## 职责

- 提供知识库管理独立页面。
- 展示知识库列表和当前知识库文档详情。
- 支持创建知识库、绑定已有文档、批量上传 PDF、移出文档和删除知识库。

## 行为规范

- 删除知识库默认只删除逻辑分组；危险选项勾选后才请求后端同时删除独占底层文档索引。
- 批量上传只接受 PDF 文件，上传后由后端代理写入 MinIO 并加入解析队列。
- 绑定已有文档时排除已经属于当前知识库的文档，避免重复绑定。
- 文档状态使用 `DocumentStatusBadge`，与左侧文档导入状态保持一致。
- 管理操作完成后必须刷新知识库列表；涉及上传或删除底层文档时同步刷新文档列表。

## 依赖关系

- 依赖 `frontend/src/lib/api.ts` 的知识库管理 API 封装。
- 依赖 `frontend/src/components/DocumentStatusBadge.tsx` 展示文档状态。
