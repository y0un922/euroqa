# Eurocode 规范问答系统 — 设计文档

> Version: 1.0
> Date: 2026-03-26
> Status: Draft

## 1. 项目概述

### 1.1 背景

中国工程师参与欧盟建设项目时，需要熟悉 Eurocode（欧洲结构设计规范）体系。该体系包含约 40 个 PDF 文档（EN 1990 ~ EN 1999 及其子部分），全英文，含大量表格、数学公式和交叉引用，与中国国标体系存在显著差异。

### 1.2 目标

构建一个基于大语言模型的规范标准查询解释系统：

- 中国工程师用**中文**提问
- 系统精确定位到规范文件的**原文位置**（文件名 + 页码 + 条款号）
- 输出原文并给出**中文翻译解释**
- 支持跨文档关联查询
- 支持推理类问题（如"巴黎地铁使用期限" → Table 2.1 Category 5: 100 years）

### 1.3 交付边界

- **核心交付物**：后端 API 服务（FastAPI），含完整 OpenAPI 文档
- **Demo 前端**：简单 Web UI，由本团队开发，不纳入最终交付
- **最终前端**：由甲方前端团队基于 API 文档对接

### 1.4 当前阶段

Demo/MVP，不考虑高并发，后续可扩展。

---

## 2. 系统架构

```
┌─────────────────────┐
│  前端（Demo/甲方）    │
└─────────┬───────────┘
          │ REST API (v1)
┌─────────▼────────────────────────────────────┐
│            后端 API 服务 (FastAPI)              │
│                                               │
│  ┌─────────────┐  ┌────────────┐  ┌────────┐ │
│  │ 查询理解层    │→│ 混合检索层  │→│ 生成层  │ │
│  └─────────────┘  └────────────┘  └────────┘ │
└────────┬─────────────────┬───────────────────┘
         │                 │
┌────────▼────────┐ ┌──────▼───────────────────┐
│  Milvus/Qdrant  │ │  离线文档处理管线          │
│  + Elasticsearch │ │  MinerU (hybrid) → 分块   │
└─────────────────┘ │  → Embedding → 入库       │
                    └──────────────────────────┘
```

### 2.1 三层核心

1. **查询理解层**：中文问题 → 意图分类 + 术语对齐 + 英文查询改写
2. **混合检索层**：向量语义检索 + BM25 关键词检索 → 跨文档聚合 → Reranker 精排
3. **生成层**：检索结果 + 用户问题 → LLM → 结构化中文回答（含原文定位 + 翻译）

---

## 3. 文档处理管线

### 3.1 PDF 解析：MinerU hybrid 后端

选择 MinerU（上海 AI Lab）的 hybrid 后端：

- 简单内容走 pipeline 后端（快速、无幻觉）
- 复杂公式走 VLM 后端（高精度视觉识别）
- 输出格式：Markdown + 元数据
- 公式 → LaTeX，表格 → HTML，图片 → 图片文件

部署架构：

```
┌─────────────┐     HTTP      ┌──────────────────┐
│  mineru-api  │ ──────────→  │ mineru-vllm-server│
│  (轻量 CPU)  │  http-client  │  (GPU 机器)       │
│  port 8000   │              │  port 30000       │
└─────────────┘              └──────────────────┘
```

API 调用指定 `backend=hybrid-http-client`，本地 API 不需要 GPU。

### 3.2 结构化解析

MinerU 输出的 Markdown 进行结构化解析：

- 识别章节/小节/条款层级（Section → Subsection → Clause）
- 标记元素类型（text / table / formula / image）
- 提取交叉引用关系（"see EN 1992" → cross_refs）

### 3.3 分块策略：混合分块

**纯文本：父子分块**

- Child chunk：小节（Subsection）级别，200-800 tokens
- Parent chunk：章节（Section）级别，用于生成时补充上下文
- 过长小节（>1500 tokens）：按条款编号 `(1)` `(2)` 切分
- 过短小节（<100 tokens）：合并相邻小节

**特殊元素：独立分块**

| 元素类型 | chunk 内容 | embedding 文本 |
|---------|-----------|---------------|
| 表格 | 标题 + HTML 内容 + 所在节标题 | LLM 生成的自然语言摘要 |
| 公式 | 编号 + LaTeX + where 定义块 + 所在节标题 | LLM 生成的语义描述 |
| 图片 | VLM 生成的图片描述 + 所在节标题 | 图片描述文本 |

**上下文关联**：

- 纯文本 chunk 中保留引用占位符：`[→ Table 2.1 - Indicative design working life]`
- 特殊元素 chunk 携带 `parent_text_chunk_id` 和 `section_path`
- 生成阶段通过关联 ID 将同一 section 的 chunks 拼合

### 3.4 Chunk 元数据

```json
{
  "source": "EN 1990:2002",
  "source_title": "Eurocode - Basis of structural design",
  "section_path": ["Section 2 Requirements", "2.3 Design working life"],
  "page_numbers": [28],
  "clause_ids": ["2.3(1)"],
  "element_type": "text|table|formula|image",
  "has_table": false,
  "has_formula": false,
  "cross_refs": ["Annex A"],
  "parent_chunk_id": "chunk_section_2",
  "parent_text_chunk_id": "chunk_023"
}
```

### 3.5 Embedding + 入库

- **Embedding 模型**：bge-m3（BAAI），支持中英双语，输出 dense + sparse 向量
- **向量库**：Milvus/Qdrant，存储 dense 向量
- **关键词检索**：Elasticsearch，存储 sparse/BM25 索引 + 元数据
- 图片不做视觉 embedding（VLM 文本描述足够），后续有图搜图需求再扩展 CLIP

### 3.6 完整管线流程

```
Stage 1: MinerU 解析
  PDF → Markdown + 元数据（页码、标题层级、公式LaTeX、表格HTML、图片文件）

Stage 2: 结构化解析
  Markdown → 识别层级 → 标记元素类型 → 提取交叉引用

Stage 3: 分块
  纯文本 → 父子分块（小节child + 章节parent）
  表格/公式/图片 → 独立分块 + LLM/VLM 生成描述

Stage 4: Embedding + 入库
  bge-m3 生成向量 → Milvus/Qdrant + Elasticsearch
  构建术语表（从 chunk 中提取中英术语对）
```

---

## 4. 查询理解层

### 4.1 意图分类

| 意图类型 | 示例 | 检索策略 |
|---------|------|---------|
| 精确查询 | "公式6.10" "Table A1.2" | BM25 优先，按编号精确匹配 |
| 概念查询 | "什么是极限状态" | 向量语义检索优先 |
| 推理查询 | "巴黎地铁寿命多久" | 查询改写 + 向量检索 + LLM 推理 |

### 4.2 查询改写（中 → 英 + 术语对齐）

流程：用户中文 → LLM 提取关键概念 → 术语表匹配 → 生成英文检索 query

领域术语映射表（离线构建 + 持续补充）：

```json
{
  "设计使用年限": "design working life",
  "极限状态": "limit state",
  "承载能力极限状态": "ultimate limit state (ULS)",
  "正常使用极限状态": "serviceability limit state (SLS)",
  "分项系数": "partial factor",
  "荷载组合": "combination of actions",
  "可变荷载": "variable action",
  "永久荷载": "permanent action",
  "偶然荷载": "accidental action"
}
```

术语表命中的用精确翻译，未命中的由 LLM 自行翻译。

### 4.3 结构化检索条件提取

从用户输入中提取元数据过滤条件：

- "EN 1992 第6章" → `source="EN 1992"`, `section_path` 过滤
- "表格A1.2" → `element_type="table"`, BM25 匹配 "A1.2"

---

## 5. 混合检索 + 重排序

### 5.1 检索流程

```
英文语义 query → 向量检索（Milvus/Qdrant） → Top-K 候选
关键词/编号    → BM25 检索（Elasticsearch）  → Top-K 候选
                                                  ↓
                                            合并去重
                                            Reranker 精排
                                            (bge-reranker-v2-m3)
                                                  ↓
                                            Top-N 最终结果
                                            + 关联 chunk 补全
元数据过滤 → source/type 过滤
结构化条件 → 同 section 的文本/表格/公式 chunk 拼合
```

### 5.2 Reranker

使用 bge-reranker-v2-m3：跨语言精排，与 bge-m3 配套。

### 5.3 跨文档聚合

检索结果按来源文件分组，每个文件取 Top-2~3，确保覆盖多文档。

### 5.4 Parent Document Retrieval

检索命中 child chunk 后，取其 parent chunk（章节级）喂给 LLM，提供更完整的上下文。

---

## 6. 生成层

### 6.1 Prompt 组装

```
系统提示：你是欧洲建筑规范专家...
术语表：{相关术语中英对照}
检索上下文：
  [1] EN 1990:2002, P28, §2.3 ...
  [2] EN 1991-1-1, P35, §6.3 ...
用户问题：{question}
要求：中文回答 + 原文定位 + 翻译
```

### 6.2 结构化输出

LLM 输出结构化 JSON：

```json
{
  "answer": "根据 EN 1990:2002 Table 2.1...",
  "sources": [
    {
      "file": "EN 1990:2002",
      "title": "Eurocode - Basis of structural design",
      "section": "2.3 Design working life",
      "page": 28,
      "clause": "Table 2.1, Category 5",
      "original_text": "Monumental building structures, bridges...",
      "translation": "重大建筑结构、桥梁及其他土木工程结构"
    }
  ],
  "related_refs": ["EN 1990:2002 Annex A"],
  "confidence": "high",
  "conversation_id": "uuid"
}
```

### 6.3 置信度

| confidence | 含义 | 前端展示建议 |
|-----------|------|------------|
| high | 直接命中规范原文 | 正常展示 |
| medium | 需要推理 | 标注"基于推理" |
| low | 未找到强相关内容 | 提示"未找到直接相关条款" |

---

## 7. 引导式交互

### 7.1 三级引导

| 级别 | 内容 | 作用 |
|------|------|------|
| 第一级 | 选择规范领域（EN 1990~1999 / 不确定） | source 过滤 |
| 第二级 | 选择问题类型（查条款/问概念/算参数/比差异） | 检索策略 + prompt 模板 |
| 第三级 | 自由输入 + 热门问题快捷入口 | 用户提问 |

引导为**可选辅助**，用户可跳过直接提问。

### 7.2 对话追问

保留最近 2-3 轮对话的检索结果作为上下文，支持连续追问。通过 `conversation_id` 关联。

---

## 8. API 设计

### 8.1 接口列表

| Method | Path | 说明 |
|--------|------|------|
| POST | /api/v1/query | 问答主接口 |
| POST | /api/v1/query/stream | SSE 流式回答 |
| GET | /api/v1/documents | 规范文件列表 |
| GET | /api/v1/documents/{id}/page/{page} | PDF 页面预览 |
| GET | /api/v1/glossary | 术语表查询 |
| GET | /api/v1/suggest | 热门问题/引导项 |

### 8.2 问答主接口

```
POST /api/v1/query

Request:
{
  "question": "string (必填)",
  "domain": "string (可选, 规范领域)",
  "query_type": "string (可选, concept|clause|parameter|comparison)",
  "conversation_id": "string (可选, 追问时传入)",
  "stream": "boolean (默认 false)"
}

Response:
{
  "answer": "string",
  "sources": [Source],
  "related_refs": ["string"],
  "confidence": "high|medium|low",
  "conversation_id": "string"
}
```

API 提供完整 OpenAPI/Swagger 文档，前端团队可自行对接。

---

## 9. 技术栈

| 层 | 技术选型 | 说明 |
|----|---------|------|
| 后端框架 | FastAPI (Python 3.12) | 异步 API，自动生成 OpenAPI 文档 |
| 文档解析 | MinerU (hybrid 后端) | PDF → Markdown，公式/表格/图片 |
| Embedding | bge-m3 (BAAI) | 中英双语 dense + sparse |
| Reranker | bge-reranker-v2-m3 | 跨语言精排 |
| 向量库 | Milvus / Qdrant | 向量检索 |
| 关键词检索 | Elasticsearch | BM25 + 元数据 |
| LLM | 国产大模型云端 API | 查询改写 + 回答生成 |
| 部署 | Docker Compose | 后端 + 依赖服务一键部署 |

---

## 10. 项目结构

```
euro-qa/
├── docs/                        # 设计文档 + API 文档
├── data/
│   ├── pdfs/                    # 原始 PDF 文件
│   ├── parsed/                  # MinerU 解析输出
│   └── glossary.json            # 中英术语表
├── pipeline/                    # 离线处理管线
│   ├── parse.py                 # Stage 1: MinerU 解析
│   ├── structure.py             # Stage 2: 结构化解析
│   ├── chunk.py                 # Stage 3: 分块
│   └── index.py                 # Stage 4: Embedding + 入库
├── server/                      # 后端 API（核心交付物）
│   ├── main.py                  # FastAPI 入口
│   ├── api/
│   │   └── v1/                  # 版本化 API 路由
│   ├── core/                    # 业务逻辑
│   │   ├── query.py             # 查询理解
│   │   ├── retrieval.py         # 检索
│   │   └── generation.py        # 生成
│   ├── models/                  # 数据模型
│   └── config.py                # 配置
├── demo-web/                    # Demo 前端（不纳入最终交付）
├── pyproject.toml
└── docker-compose.yml           # 一键部署
```

---

## 11. 风险与待定项

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| MinerU 复杂公式识别错误 | 回答不准确 | hybrid 后端 VLM 兜底 + 人工校验机制 |
| 跨语言检索精度不足 | 检索召回低 | 术语表 + bge-m3 跨语言能力 + Reranker |
| LLM 幻觉 | 给出规范中不存在的内容 | 强制引用原文 + 置信度标注 |
| 40个PDF处理时间 | 离线管线耗时 | 一次性处理，增量更新 |

### 待定项

- 国产 LLM 具体选型（通义千问 / DeepSeek / 其他）
- Milvus vs Qdrant 最终选择
- 中欧规范差异对比功能的深度
- 术语表的初始规模和维护机制
