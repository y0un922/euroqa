# Phase 3: 生成层证据闸门

## 目标

让回答严格服从闭环证据，而不是自由选择相关片段。

## 任务清单

- [x] **P3-T1**: 重构 exact evidence pack
- [x] **P3-T2**: unresolved refs 显式暴露
- [x] **P3-T3**: sources 顺序与证据顺序对齐
- [ ] **P3-T4**: 受限 LLM fallback 预留点

## Notes

- LLM fallback 只能做增强，不能代替 deterministic 主链
- 先保证排序和闸门，再考虑额外智能性

## 已完成内容

- `server/models/schemas.py`
  - `RetrievalContext` 新增 `ref_chunks / resolved_refs / unresolved_refs`
- `server/core/generation.py`
  - exact / exact_not_grounded prompt 显式注入已补齐与未补齐引用
  - `sources` 顺序改为跟随 exact evidence pack
  - `retrieval_context` 持久化 `ref_chunks / resolved_refs / unresolved_refs`
- `server/api/v1/query.py`
  - 将 retrieval 的 `resolved_refs / unresolved_refs` 透传给 generation

## 验证

- `uv run pytest -q tests/server/test_generation.py tests/server/test_retrieval.py tests/server/test_query_understanding.py tests/server/test_api.py`

结果：

- `124 passed`
