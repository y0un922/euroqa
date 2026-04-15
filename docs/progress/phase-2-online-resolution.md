# Phase 2: 在线 deterministic resolver

## 目标

在线检索时基于对象图补齐交叉引用，输出闭环证据结果。

## 任务清单

- [x] **P2-T1**: query understanding 补 `requested_objects`
- [x] **P2-T2**: 新增 resolver 主逻辑
- [x] **P2-T3**: 引用对象提权排序
- [x] **P2-T4**: 引用闭环 groundedness

## Notes

- exact 问题的关键不只是“主条款命中”，而是“被引对象也命中”
- 该阶段结束后，应能输出 `resolved_refs/unresolved_refs`

## 已完成内容

- `server/core/query_understanding.py`
  - 新增 `extract_requested_objects()`
  - `analyze_query()` 产出 `requested_objects`
- `server/api/v1/query.py`
  - 将 `requested_objects` 透传给 retrieval
- `server/core/retrieval.py`
  - 新增 `object_id` 定向检索
  - 主检索后先按 `requested_objects + ref_object_ids` 做 deterministic object lookup
  - `ref_chunks` 优先注入直接被引对象，再回退字符串补抓
  - `groundedness` 增加 reference closure 约束
  - 输出 `resolved_refs / unresolved_refs`
  - direct ref 命中的 `Table / Expression / Annex` 会提升进 primary exact evidence，而不是只留在 `ref_chunks`
  - reference closure 改为按 `object_type:key` 比较，规避 source slug 差异导致的假未闭环
  - 未显式请求的 `Figure` 不再阻断 exact groundedness
  - 当同 key 的 `Table/Figure/Expression` 已显式请求时，阴影产生的 clause 请求会被忽略

## 验证

- `uv run pytest -q tests/server/test_query_understanding.py tests/server/test_retrieval.py tests/server/test_api.py`
- `uv run pytest -q tests/server/test_generation.py tests/server/test_retrieval.py tests/server/test_query_understanding.py tests/server/test_api.py`
- `uv run pytest -q tests/server/test_retrieval.py -k 'ReferenceClosure and (resolves_direct_referenced_table or ignores_requested_clause or does_not_require_unrequested_figures or ignores_shadowed_clause_request)'`

结果：

- `73 passed`
- `121 passed`
- `4 passed`

## 线上冒烟

- `3.1.7 里面混凝土受压应变限值怎么取？`
  - `groundedness = grounded`
  - `resolved_refs = ["3.1.7", "Table 3.1"]`
  - primary evidence 顺序为 `3.1.7 -> Table 3.1`
- `Table 3.1 混凝土强度等级有哪些？`
  - `groundedness = grounded`
  - `unresolved_refs = []`
