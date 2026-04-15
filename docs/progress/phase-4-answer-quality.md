# Phase 4: 回答质量优化

## 目标
在更好的检索基础上提升 LLM 回答质量。

## 任务清单

- [ ] **P4-T1**: 增大上下文 token 预算
  - max_context_tokens: 3000→4000
  - parent_chunks 预算同步调整

- [ ] **P4-T2**: 优化 query rewrite prompt
  - 生成关键词 + 自然语言英文查询
  - 向量检索用 sentence，BM25 用 keywords

- [ ] **P4-T3**: 端到端验证
  - 评测 + 人工抽查

## 并行矩阵
```
[T1: token budget] [T2: query rewrite] → [T3: e2e verify]
```
