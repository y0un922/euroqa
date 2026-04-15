# 检索优化 — 任务拆解

## 概述

目标：移除无效意图分类，提升检索召回率和回答质量。

分为 4 个阶段，每阶段内的任务可并行执行（标注了并行通道）。

---

## Phase 1: 清理意图分类（低风险，立即可做）

> 目标：移除 IntentType 及其所有引用，简化检索管线

### P1-T1: 简化 query_understanding.py
- **并行通道**: A
- **文件**: `server/core/query_understanding.py`
- **操作**:
  - 删除 `classify_intent()` 函数及相关正则 `_EXACT_PATTERNS`
  - 从 `QueryAnalysis` dataclass 移除 `intent` 字段
  - `analyze_query()` 不再调用 `classify_intent()`
- **合并风险**: 低

### P1-T2: 简化 retrieval.py
- **并行通道**: B
- **文件**: `server/core/retrieval.py`
- **操作**:
  - `_merge_results()` 移除 `intent` 参数，统一为向量优先合并
  - `retrieve()` 移除 `intent` 参数
- **合并风险**: 低

### P1-T3: 清理 schemas 和 API 层
- **并行通道**: C
- **文件**: `server/models/schemas.py`, `server/api/v1/query.py`
- **操作**:
  - 从 schemas.py 删除 `IntentType` 枚举（如无其他引用）
  - query.py 中不再传递 `intent` 给 retriever
- **合并风险**: 低

### P1-T4: 更新测试
- **并行通道**: D
- **文件**: `tests/server/test_query_understanding.py`, `tests/server/test_retrieval.py`
- **操作**:
  - 删除 `TestClassifyIntent` 类
  - 删除 `test_exact_intent_prioritizes_bm25`
  - 更新 `TestAnalyzeQuery` 移除 intent 断言
  - 更新 `TestRetrieveFallback` 移除 intent 相关代码
- **依赖**: P1-T1, P1-T2, P1-T3 完成后执行
- **合并风险**: 低

### P1-T5: 验证
- **操作**: 运行全量测试确认无回归
- **依赖**: P1-T4

---

## Phase 2: 建立评测基线（诊断优先）

> 目标：量化当前检索系统的召回表现，为后续优化提供数据支撑

### P2-T1: 创建评测数据集
- **并行通道**: A
- **文件**: 新建 `tests/eval/test_questions.json`
- **操作**:
  - 设计 10-15 个典型 Eurocode 查询问题
  - 每个问题标注期望命中的条款/表格/公式
  - 覆盖：精确引用、概念查询、推理查询、跨文档查询
- **合并风险**: 无（新增文件）

### P2-T2: 创建评测脚本
- **并行通道**: B
- **文件**: 新建 `tests/eval/eval_retrieval.py`
- **操作**:
  - 读取测试问题 → 走完整检索管线 → 计算 recall@k
  - 输出每个问题的命中/未命中分析
  - 支持对比不同参数配置
- **合并风险**: 无（新增文件）

### P2-T3: 运行基线评测
- **依赖**: P2-T1, P2-T2
- **操作**: 执行评测，记录当前 recall@8 基线数据

---

## Phase 3: 检索召回优化

> 目标：基于诊断结果提升 recall@k

### P3-T1: 优化检索参数
- **并行通道**: A
- **文件**: `server/config.py`
- **操作**:
  - `vector_top_k`: 20 → 30
  - `bm25_top_k`: 20 → 30
  - `rerank_top_n`: 8 → 10
  - 放宽 `cross_doc_aggregate` max_per_source（3 → 5，或根据是否有 source filter 动态调整）
- **合并风险**: 低

### P3-T2: BM25 双语检索
- **并行通道**: B
- **文件**: `server/core/retrieval.py`
- **操作**:
  - `_bm25_search()` 增加接受原始中文查询的能力
  - `retrieve()` 中对 BM25 同时使用改写后英文和原始中文执行两次搜索
  - 合并两路 BM25 结果
- **合并风险**: 中（修改检索核心逻辑）

### P3-T3: Rerank 使用原始问题
- **并行通道**: C
- **文件**: `server/core/retrieval.py`
- **操作**:
  - `_rerank()` 使用用户原始中文问题（而非改写后的英文关键词）
  - 因为 reranker（bge-reranker-v2-m3）支持跨语言
- **合并风险**: 低

### P3-T4: 验证召回提升
- **依赖**: P3-T1, P3-T2, P3-T3
- **操作**: 重新跑评测脚本，对比 recall@k 变化

---

## Phase 4: 回答质量优化

> 目标：在更好的检索基础上提升 LLM 回答质量

### P4-T1: 增大上下文 token 预算
- **并行通道**: A
- **文件**: `server/config.py`, `server/core/generation.py`
- **操作**:
  - `max_context_tokens` 3000 → 4000
  - `build_prompt()` 中 parent_chunks token 预算同步调整
- **合并风险**: 低

### P4-T2: 优化 query rewrite prompt
- **并行通道**: B
- **文件**: `server/core/query_understanding.py`
- **操作**:
  - 改进 rewrite prompt：不仅生成关键词，还生成一个自然语言英文查询
  - 输出格式：`keywords: ... | sentence: ...`
  - 向量检索用 sentence，BM25 用 keywords
- **合并风险**: 中

### P4-T3: 端到端验证
- **依赖**: P4-T1, P4-T2
- **操作**: 运行评测 + 人工抽查回答质量

---

## 并行执行矩阵

```
Phase 1: [A: query_understanding] [B: retrieval] [C: schemas+api] → [D: tests] → [verify]
Phase 2: [A: eval dataset] [B: eval script] → [run baseline]
Phase 3: [A: params] [B: bm25 bilingual] [C: rerank original] → [verify recall]
Phase 4: [A: token budget] [B: query rewrite] → [e2e verify]
```
