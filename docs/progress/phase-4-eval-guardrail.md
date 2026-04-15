# Phase 4: 专项评测与回归门禁

## 目标

把交叉引用质量变成可量化门禁。

## 任务清单

- [x] **P4-T1**: 建专项题库
- [x] **P4-T2**: 指标与报告扩展
- [x] **P4-T3**: 单测补齐
- [ ] **P4-T4**: 基线对比与验收

## Notes

- 没有专项题库，就无法证明生产可用
- 重点看 `direct_ref_resolution_rate` 和 `noise_intrusion_rate`

## 已完成内容

- `tests/eval/test_questions.json`
  - 新增 clause -> table 的交叉引用题型
- `tests/eval/eval_retrieval.py`
  - 评测时透传 `requested_objects`
  - 新增 `direct_ref_resolution_rate`
  - 新增 `reference_closure_rate`
  - 新增 `noise_intrusion_rate`
  - `per_question` 输出 `resolved_refs / unresolved_refs / direct_ref_hits`
- `tests/eval/test_eval_retrieval.py`
  - 为 helper 指标逻辑和 `evaluate()` 主链补离线单测

## 验证

- `uv run pytest -q tests/eval/test_eval_retrieval.py tests/server/test_generation.py tests/server/test_retrieval.py tests/server/test_query_understanding.py tests/server/test_api.py`

结果：

- `128 passed`

## 待完成

- 还没有在真实 ES/Milvus + 重建索引环境下刷新 `eval_results.json`
- `P4-T4` 需要在线跑一次 retrieval eval，生成新的基线报告后才能算完成
