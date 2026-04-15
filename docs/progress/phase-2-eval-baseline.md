# Phase 2: 建立评测基线

## 目标
量化当前检索系统的召回表现，为优化提供数据支撑。

## 任务清单

- [ ] **P2-T1**: 创建评测数据集
  - 设计 10-15 个典型问题 + 期望命中片段
  - 文件: `tests/eval/test_questions.json`

- [ ] **P2-T2**: 创建评测脚本
  - 完整检索管线 → recall@k 计算
  - 文件: `tests/eval/eval_retrieval.py`

- [ ] **P2-T3**: 运行基线评测
  - 记录当前 recall@8 基线数据

## 并行矩阵
```
[T1: eval dataset] [T2: eval script] → [T3: run baseline]
```
