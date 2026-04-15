# Phase 1: 后端导出契约与检索快照标准化

## 任务清单

- [x] P1-T1 定义 retrieval context DTO，并把它纳入非流式响应与流式完成态元数据。（验收：新结构能区分主检索上下文与父级扩展上下文；主检索项支持 rerank score；字段只保留导出与前端持久化所需内容；`/query` 与 `/query/stream` 完成态使用同一数据形状）
- [x] P1-T2 在 `server/core/generation.py` 中新增共享 snapshot builder，统一从 `chunks / parent_chunks / scores` 生成导出快照。（验收：流式与非流式复用同一构造逻辑；主检索与父级扩展分组清晰；输出字段覆盖文件名、标题、章节、页码、条款、正文文本及必要补充元数据；空检索结果返回稳定空结构）
- [x] P1-T3 更新 `server/api/v1/query.py` 的 `/query` 与 `/query/stream` 完成态返回，并同步补齐后端契约测试。（验收：非流式 `QueryResponse` 含 retrieval context；流式 `done` payload 含相同字段；fallback 非流式路径与 stream 完成态保持一致；`tests/server/test_api.py` 和 `tests/server/test_generation.py` 覆盖新增字段）

## Notes

- 当前阶段不建议并行执行，原因是 schema、generation 与 query 编排高度耦合。
- 若需要压缩 localStorage 体积，应在本阶段就裁剪导出快照字段，而不是把完整内部 `Chunk` 结构透传到前端。
