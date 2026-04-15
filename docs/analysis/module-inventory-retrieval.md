# 检索优化项目 — 模块盘点

## 需要修改的模块

### 1. server/core/query_understanding.py (192 行)

**职责**：查询分析管线 — 意图分类 + 过滤提取 + 查询改写

**公开 API**：
- `classify_intent(question) → IntentType` — 基于正则匹配的意图分类【拟删除】
- `extract_filters(question) → dict` — 提取 EN 标准号和元素类型过滤条件【保留】
- `rewrite_query(question, glossary, config) → str` — LLM 中文→英文改写【保留并增强】
- `analyze_query(question, glossary, config) → QueryAnalysis` — 组合入口【简化】
- `sanitize_input(question) → str` — 输入注入防护【保留】

**下游依赖**：
- `IntentType` 被 `retrieval.py:_merge_results()` 和 `retrieve()` 使用
- `QueryAnalysis.intent` 被 `query.py` 传递给 retriever

### 2. server/core/retrieval.py (365 行)

**职责**：混合检索 — 向量 + BM25 + rerank + 父文档

**公开 API**：
- `HybridRetriever.retrieve(query, original_query, intent, filters) → RetrievalResult`

**需要修改**：
- `_merge_results()` — 移除 intent 参数，统一合并策略
- `retrieve()` — 移除 intent 参数，优化候选池策略
- `_bm25_search()` — 考虑增加原始中文查询搜索

### 3. server/models/schemas.py (152 行)

**职责**：Pydantic 数据模型

**需要修改**：
- `IntentType` 枚举 — 移除或标记弃用
- `QueryAnalysis` dataclass 在 query_understanding.py 中 — 移除 intent 字段

### 4. server/api/v1/query.py (114 行)

**职责**：问答 API 端点

**需要修改**：
- `query()` 和 `query_stream()` — 不再传递 intent 给 retriever

### 5. server/core/generation.py (789 行)

**职责**：Prompt 组装 + LLM 调用 + 结果解析

**可能修改**：
- `build_prompt()` — 优化上下文组装策略，增大 token 预算

### 6. server/config.py (72 行)

**职责**：服务器配置

**需要修改**：
- 增加/调整检索相关参数

## 需要修改的测试

### tests/server/test_query_understanding.py
- `TestClassifyIntent` 类（5 个测试）— 整体删除
- `TestAnalyzeQuery` — 移除 intent 断言

### tests/server/test_retrieval.py
- `TestMergeAndDedup.test_exact_intent_prioritizes_bm25` — 删除
- `TestRetrieveFallback` — 移除 intent 相关断言

## 不需要修改的模块

- `pipeline/` — 数据处理管线，与检索逻辑无关
- `shared/` — 模型客户端工具类，接口不变
- `frontend/` — 前端不感知 intent 类型
