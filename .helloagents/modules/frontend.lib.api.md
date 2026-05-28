# 模块: frontend.lib.api

## 职责

- 封装前端调用后端 API 的 URL、JSON 请求和 SSE 读取逻辑
- 管理文档导入、问答、引用翻译、LLM 设置和文档预览相关请求

## 行为规范

- `buildChatQueryPayload()` 使用 `sessionId` 字段发送外部会话 ID，保持跨文档检索时不附带 `domain`
- `queryStream()` 会在请求体中补充 `stream: true`，不附带项目内置 bearer token，并把 `reasoning`、`chunk`、`progress`、`done` 事件分发给调用方
- `uploadDocumentToMinio()` 以 `multipart/form-data` 调用 `/api/v1/documents/upload-to-minio`，由后端代理写入 MinIO 并触发解析
- 旧 `uploadDocument()` 与 `processDocument()` 保留为兼容接口，不作为华科方联调默认路径

## 依赖关系

- 被 `frontend/src/hooks/useEuroQaDemo.ts` 和 `frontend/src/hooks/useDocumentImport.ts` 调用
