# 模块: server.core.retrieval

## 职责

- 执行混合检索：向量召回、BM25、去重融合、跨文档聚合、重排序和父块补全
- 在主检索 query 之外，使用原问题做补充向量召回

## 行为规范

- 主检索 query 默认使用 `rewritten_query`，走 `vector + BM25`。
- 当 `original_query` 非空且与主 query 不同，额外执行一次 `vector-only` 补召回。
- 原问题补召回只追加新候选，不打乱主检索结果原有顺序；主路仍然由 `rewritten_query` 决定。
- 中文原问题不直接参与 BM25，以避免对英文规范文档产生低质量词面召回。
- 当请求已显式限定 `source`，或当前候选实际上只来自单一 `source` 时，跳过跨文档聚合，不再把候选集合压缩到 `max_per_source=3`。
- 候选集合在融合后仍需经过跨文档聚合、chunk 拉取、rerank 和父块补全，避免两套流程分叉。

## 依赖关系

- 依赖 Milvus 向量检索与 Elasticsearch BM25 检索
- 依赖 `server.core.query_understanding` 提供 `rewritten_query` 与 `original_question`
- 依赖 rerank client 对融合后的候选集合做最终排序
