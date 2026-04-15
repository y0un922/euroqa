# Phase 3: 检索召回优化

## 目标
基于评测数据提升 recall@k。

## 任务清单

- [ ] **P3-T1**: 优化检索参数
  - vector_top_k: 20→30, bm25_top_k: 20→30, rerank_top_n: 8→10
  - 放宽 cross_doc_aggregate

- [ ] **P3-T2**: BM25 双语检索
  - BM25 同时搜索英文改写 + 原始中文

- [ ] **P3-T3**: Rerank 使用原始问题
  - reranker 用用户原始中文问题排序

- [ ] **P3-T4**: 验证召回提升
  - 重跑评测脚本对比

## 并行矩阵
```
[T1: params] [T2: bm25 bilingual] [T3: rerank original] → [T4: verify]
```
