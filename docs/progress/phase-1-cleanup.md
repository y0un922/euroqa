# Phase 1: 清理意图分类

## 目标
移除 IntentType 枚举及所有引用，简化检索管线。

## 任务清单

- [ ] **P1-T1**: 简化 query_understanding.py
  - 删除 `classify_intent()` + `_EXACT_PATTERNS`
  - `QueryAnalysis` 移除 `intent` 字段
  - `analyze_query()` 不再调用 `classify_intent()`

- [ ] **P1-T2**: 简化 retrieval.py
  - `_merge_results()` 移除 `intent` 参数
  - `retrieve()` 移除 `intent` 参数

- [ ] **P1-T3**: 清理 schemas + API
  - 删除 `IntentType` 枚举
  - `query.py` 不再传递 intent

- [ ] **P1-T4**: 更新测试
  - 删除 `TestClassifyIntent` 类
  - 删除 `test_exact_intent_prioritizes_bm25`
  - 更新 intent 相关断言

- [ ] **P1-T5**: 全量测试验证

## 并行矩阵
```
[T1: query_understanding] [T2: retrieval] [T3: schemas+api] → [T4: tests] → [T5: verify]
```
