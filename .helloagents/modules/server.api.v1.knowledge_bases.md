# 模块: server.api.v1.knowledge_bases

## 职责

- 提供 `/api/v1/knowledge-bases` 受保护管理接口。
- 支持创建、列表、详情、更新、删除知识库。
- 支持绑定已有文档、从知识库移出文档、批量上传 PDF 并加入解析队列。

## 行为规范

- 删除知识库默认只删除知识库元数据和绑定关系，不删除底层文档索引。
- `delete_documents=true` 是危险模式，只删除该知识库独占的底层文档索引，共享文档必须保留。
- 删除前若知识库内任一文档仍在解析、结构化、分块、摘要或索引阶段，接口返回 409 业务错误。
- 批量上传复用文档解析链路：上传 PDF 到 MinIO 后调用 `_enqueue_document_parse()` 写入 parse options 并入队。
- 详情响应中的文档状态来自文档 API 的 `_get_document_status()`，保持与文档列表状态一致。

## 依赖关系

- 依赖 `server.services.kb_database.KBDatabase` 存储元数据。
- 复用 `server.api.v1.documents` 的 doc_id 规范化、解析入队、状态查询与索引删除 helper。
- 依赖 `server.services.minio_storage.upload_pdf_to_minio` 上传 PDF。
