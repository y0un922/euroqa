# 检索优化项目 — 架构总览

## 项目概要

Euro_QA 是一个面向中国工程师的欧洲建筑规范（Eurocode）问答系统。核心功能是用户输入中文问题，系统从 Eurocode PDF 中检索相关条款片段，并借助 LLM 生成中文回答。

## 技术栈

| 层 | 技术 |
|---|------|
| Web 框架 | FastAPI + SSE（sse-starlette） |
| 向量数据库 | Milvus（COSINE, HNSW ef=128） |
| 全文检索 | Elasticsearch（BM25, multi_match） |
| Embedding | BAAI/bge-m3（本地或远程 API） |
| Rerank | BAAI/bge-reranker-v2-m3（本地或远程 API） |
| LLM | OpenAI-compatible API（默认 DeepSeek） |
| PDF 解析 | MinerU（本地/官方 API） |
| 前端 | React + TypeScript + Vite |

## 当前检索流水线

```
用户中文问题
   │
   ├── classify_intent → EXACT/CONCEPT/REASONING  ← 【无实际价值，拟删除】
   ├── extract_filters → {source: "EN xxxx", element_type: "table"}
   └── rewrite_query → LLM 改写为英文检索关键词
           │
           ▼
   ┌─── HybridRetriever.retrieve() ───┐
   │                                   │
   │  rewritten_query → vector_search (Milvus, top_k=20)
   │  rewritten_query → bm25_search   (ES, top_k=20)
   │  original_query  → vector_search (Milvus, top_k=20, 补充)
   │                                   │
   │  merge_results  ← intent 决定优先级（几乎无效果）
   │  cross_doc_aggregate ← 每个来源最多 3 chunks
   │  fetch_chunks   ← 从 ES 获取完整文档
   │  rerank         ← bge-reranker (top_n=8)
   │  fetch_parent_chunks
   │                                   │
   └─── RetrievalResult ──────────────┘
           │
           ▼
   build_prompt → LLM → 流式/非流式回答
```

## 关键参数（server/config.py）

| 参数 | 默认值 | 含义 |
|------|--------|------|
| vector_top_k | 20 | 向量检索取前 N 个 |
| bm25_top_k | 20 | BM25 检索取前 N 个 |
| rerank_top_n | 8 | 重排序后保留前 N 个 |
| max_context_tokens | 3000 | prompt 中上下文 token 预算 |

## 已识别问题

1. **intent 分类无实际价值**：只影响 merge 时的优先级排序，rerank 后被抹平
2. **BM25 仅搜英文**：rewrite_query 生成英文关键词给 BM25，但 Eurocode 原文本身是英文，这没问题；但如果用户问的中文在 embedding_text 中，BM25 搜不到
3. **cross_doc_aggregate 限制过严**：每个来源最多 3 chunks，可能在单文档深度查询时丢失关键片段
4. **rerank 用 rewritten query**：rerank 应该同时考虑原始中文问题
5. **候选池可能不够大**：20+20 去重后可能只有 25-30 候选，rerank 从中选 8 个
