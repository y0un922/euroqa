# 模块: server.api.v1.documents

## 职责

- 处理文档解析触发、批量状态查询、批量删除和单文档兼容端点
- 维护文档索引、解析状态和 PDF 文件的外部对接契约

## 行为规范

- `POST /documents/parse` 接受 `docId`、`fileName`、`minioPath`，返回 `code`、`docId`、`status`、`message`
- `minioPath` 使用 `bucket/key` 格式时，后端会通过 MinIO 客户端下载到 `pdf_dir/{docId}.pdf` 后入队；本地可见文件路径仍作为开发兼容路径
- `POST /documents/upload-to-minio` 接受浏览器上传的 PDF，后端写入 `eurocode/uploads/{docId}.pdf`，再复用解析队列返回 `code`、`docId`、`fileName`、`minioPath`、`status`、`message`
- `POST /documents/status` 接受 `docIds` 数组，批量返回每个文档的 `status`、`progress`、`stage`、`message` 和可选错误信息
- `POST /documents/delete` 接受 `docIds` 数组，逐条返回删除结果，不因单条失败中断整体响应
- 旧的 `/documents/{doc_id}/process` 与 `DELETE /documents/{doc_id}` 作为兼容 wrapper，内部复用新契约逻辑
- 批量删除与单文档删除都必须在测试中 mock 索引删除操作，避免真实外部数据删除

## 依赖关系

- 依赖 `server.services.task_manager` 判断文档解析是否处于活跃状态
- 依赖 `server.services.minio_storage` 向 MinIO 写入浏览器上传 PDF，并从 MinIO 获取外部上传 PDF
- 依赖 `pipeline.index.delete_document_chunks` 删除文档索引数据
- 依赖 `server.deps.invalidate_retriever_cache()` 使删除后的文档立即失效
