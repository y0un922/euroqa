# 模块: server.services.kb_database

## 职责

- 使用 SQLite 持久化逻辑知识库元数据。
- 维护知识库与文档 `doc_id` 的多对多关系。
- 为删除知识库时的独占文档判断提供查询能力。

## 行为规范

- 数据库路径来自 `ServerConfig.kb_db_path`，应用启动时通过 `KBDatabase.initialize()` 建表并开启 foreign keys。
- `knowledge_bases.name` 唯一，创建或重命名冲突由 API 层转为 409 业务错误。
- `kb_documents` 使用 `(kb_id, doc_id)` 作为主键，重复添加同一文档应幂等返回 0 个新增关系。
- `get_exclusive_doc_ids(kb_id)` 只返回不属于其他知识库的文档，用于危险删除模式。
- `add_documents()` 和 `remove_documents()` 返回实际关系变更数量，不包含知识库 `updated_at` 更新时间的 UPDATE。

## 依赖关系

- 被 `server.api.v1.knowledge_bases` 用于管理接口。
- 被 `server.api.v1.query` 用于将 `kbIds` 解析为检索 source 范围。
