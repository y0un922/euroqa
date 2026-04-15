# 基线评测结果（部分：q01-q08）

## 配置
- vector_top_k=20, bm25_top_k=20, rerank_top_n=8
- embedding: BAAI/bge-m3, reranker: BAAI/bge-reranker-v2-m3

## 汇总指标

| 指标 | 值 |
|------|------|
| section_recall@8 | 0.7188 (平均) |
| keyword_recall@8 | 0.7088 (平均) |
| 通过率 (recall≥0.5) | 87.5% (7/8) |

## 逐题结果

| ID | 问题 | section_recall | keyword_recall | 状态 | 最高rerank分 |
|----|------|---------------|----------------|------|-------------|
| q01 | C30/37抗压强度设计值 | 1.00 | 0.67 | PASS | 0.901 |
| q02 | 保护层厚度 | 1.00 | 1.00 | PASS | 0.978 |
| q03 | 梁的抗剪设计 | 0.50 | 1.00 | PASS | 0.204 |
| q04 | Table 3.1 强度等级 | 0.50 | 0.33 | PASS | 0.841 |
| q05 | 裂缝宽度控制 | 0.75 | 0.67 | PASS | 0.960 |
| q06 | 6.2.2条 无抗剪钢筋 | 1.00 | 0.00 | PASS | 0.972 |
| q07 | 徐变和收缩 | 1.00 | 1.00 | PASS | 0.911 |
| q08 | 环境等级 XC1/XC2 | 0.00 | 1.00 | FAIL | - |

## 已识别的召回问题

### 1. q03 — rerank 分数极低（最高仅 0.204）
- **原因**: rewrite 生成了 "beam shear design procedure EN 1992 EN 1993 verification calculation"，包含无关的 "EN 1993"
- **根因**: reranker 用改写后的英文查询而非原始中文问题来排序
- **改进**: rerank 应使用原始中文问题（bge-reranker 支持跨语言）

### 2. q04 — Table 3.1 未被检索到
- **原因**: element_type=table 过滤限制了候选池，且 Table 3.1 的 chunk 可能没有在 section_path 中包含 "3.1.2"
- **改进**: 增大 top_k 或放宽过滤条件

### 3. q07 — 目标 section 3.1.4 排在第 7 位
- **原因**: 向量检索将 "Greek lower case letters" 排在首位，与徐变收缩公式中的希腊字母相关但不直接
- **改进**: 更大的候选池 + 更好的 rerank 策略

### 4. q08 — FAIL：section 4.2 完全未命中
- **原因**: 虽然关键词全部命中（XC1, XC2, exposure class, Table 4.1），但 section_path 中不包含 "4.2" 字样
- **改进**: 可能是 section_path 存储格式问题（如 "4.2 Environmental conditions" vs "Table 4.1: Exposure classes..."）

### 5. q06 — keyword_recall=0 但 section_recall=1.0
- **原因**: 期望关键词 "VRd,c" 含特殊字符逗号，在 chunk 中可能格式不同
- **结论**: keyword_recall 指标对特殊字符敏感，section_recall 更可靠

## 优化方向优先级

1. **Rerank 使用原始中文问题** — 直接解决 q03 低分问题（影响最大）
2. **增大 top_k 和 rerank_top_n** — 扩大候选池（30+30 → rerank 10-12）
3. **放宽 cross_doc_aggregate** — 单文档场景下不限制
4. **改进 query rewrite** — 避免引入无关内容（如 EN 1993）
