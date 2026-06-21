# 多规范 Agentic Search 方案（v3.1 — 三方共识版）

> **修订记录**：
> - v1：初版方案
> - v2：Codex review 后修正 5 个问题（Agent Loop 重写、索引迁移、filter 契约、交叉引用、eval 入口）
> - v3：三方设计共识（QU 自动路由为主、Agent 覆盖为辅、soft boost vs hard filter）
> - v3.1（本版）：Codex 第二轮 review 修正 5 中 + 1 低中实施契约细节：
>   - doc_version 契约统一：拆分 `version_pref`（语义输入）和 `doc_version: list[str]`（检索过滤值）
>   - 交叉引用函数名修正为实际代码：`_fetch_cross_ref_chunks` / `_fetch_object_chunks_by_object_ids`
>   - soft_boosts 签名链路完整补齐：analyze_query → retrieve tool → HybridRetriever → ES should / rerank
>   - /documents/parse 增加 doc_type 的完整文件链路展开
>   - rerank source 标注对齐 `_rerank_text()` 现有逻辑
>   - Phase 2 scope 澄清：retrieve 覆盖参数归入 Phase 1 最后一步

---

## 1. 背景

### 1.1 业务需求

甲方（华科）需要系统支持**多种类、多篇欧洲结构设计规范**的上传与问答。当前系统仅针对少量 Eurocode 规范（EN 1990、EN 1991-1-1、EN 1992-1-1）做了优化，现在需要扩展到完整的规范体系。

### 1.2 测试文档集

首批测试文件共 **20 个 PDF，约 4,800 页**，分为两大批次：

**新版规范（5 本，BS EN 系列）：**

| 文件 | 页数 | 领域 |
|------|------|------|
| BS-EN-1990-2023 | 178 | 设计基本 |
| BSEN1991-1-1-2025 | 49 | 荷载 |
| BSEN1992-1-1-2023 | 408 | 混凝土 |
| BSEN1993-1-1-2022 | 126 | 钢结构 |
| BSEN1998-1-1-2024 | 130 | 抗震 |

**现行版规范 + 指南 + 示例（15 本）：**

| 规范族 | 规范（页） | 指南（页） | 示例（页） |
|--------|-----------|-----------|-----------|
| EN 1990 设计基本 | 90 | 190 | — |
| EN 1991-1-1 荷载 | 47 | — | — |
| EN 1992-1-1 混凝土 | 225 | 242 | 186 |
| EN 1993-1-1 钢结构 | 98 | 167 | 470 |
| EN 1997-1 地基 | 173 | 213 | 172 |
| EN 1998-1 抗震 | 232 | 288 | 522 |

### 1.3 文档特征分析

这批文档有三个区分维度，对检索质量有直接影响：

**维度一：规范族（Standard Family）**
- EN 1990（设计基本）、EN 1991（荷载）、EN 1992（混凝土）、EN 1993（钢结构）、EN 1997（地基）、EN 1998（抗震）
- 不同规范族之间存在大量**交叉引用**（如 EN 1992 引用 EN 1990 的荷载组合公式，EN 1998 引用 EN 1992 的延性设计条款）

**维度二：文档类型（Document Type）**
- **规范（Standard）**：正式条款文本，精确条文号 + 公式编号，权威性最高
- **指南（Designer's Guide）**：对条款的解释性说明，实践建议，补充背景知识
- **示例（Worked Example）**：完整计算过程，含数值、步骤、中间结果

**维度三：版本（Version）**
- 现行版（EN xxxx:2002-2005 系列）
- 新版（BS EN xxxx:2022-2025 系列）
- 同一规范的新旧版内容高度重叠但条款号可能不同

### 1.4 核心挑战

若将 20 个文件不加区分地全部索引到同一检索空间，会出现以下质量问题：

1. **类型混淆**：用户问"EN 1992-1-1 第 6.1 条规定了什么"，系统可能返回指南里的解释而不是规范原文
2. **版本混淆**：BSEN1992-1-1-2023 和 EN1992-1-1_2004 的 embedding 相似度极高（内容重叠），reranker 无法区分版本
3. **示例噪声**：计算示例文档页数多（470p、522p）、chunk 密度高，会在通用检索中抢占大量排名位
4. **跨规范稀释**：6 个规范族的 chunk 混合后，单一规范的深层问题召回率被其他规范的相似 chunk 稀释
5. **交叉引用覆盖不足**：当前系统已有交叉引用图扩展能力（`retrieval.py:1131` 的 `_fetch_cross_ref_chunks` + `retrieval.py:1229` 的 `_fetch_object_chunks_by_object_ids`），但仅限于同一 collection 内已索引的文档间引用；新增规范族后需评估残余跨规范引用缺口

---

## 2. 当前系统现状

### 2.1 解析流程（pipeline/）

- **串行处理**：`parse_all_pdfs()` 逐个 PDF 顺序解析，无并行
- **MinerU API**：单个 PDF 解析耗时 30-120s（取决于页数），>200 页自动分片上传
- **全量流水线**：Parse → Structure → Chunk → Contextualize → Index，每个阶段串行

**20 个文件串行解析预估耗时：1-2 小时**（一次性操作，非实时瓶颈）

### 2.2 Chunk 元数据（server/models/schemas.py）

当前 `ChunkMetadata` 包含：
- `source`: 文档标识（如 "EN 1990"）
- `source_title`: 显示名称
- `section_path`: 章节层级路径
- `clause_ids`: 条文编号列表
- `element_type`: TEXT / TABLE / FORMULA / IMAGE
- `cross_refs`: 交叉引用列表
- `object_id`, `object_label`, `object_aliases`: 具名对象

**缺失**：无 `doc_type`（规范/指南/示例）、无 `doc_version`（版本标识）、无 `standard_family`（规范化族标识）

### 2.3 索引 Schema 现状

**Milvus**（`shared/milvus_schema.py:7-14`）：当前 collection 仅有 **4 个字段**：
- `chunk_id`（VARCHAR, PK）
- `embedding`（FLOAT_VECTOR, dim=1024）
- `source`（VARCHAR）
- `element_type`（VARCHAR）

`pipeline/index.py:53-58` 的 insert 操作也只写这 4 列。**新增字段需要 drop + recreate collection**，Milvus 不支持 ALTER TABLE 式的在线 schema 变更。

**Elasticsearch**：通过 `chunk.metadata.model_dump()` 动态写入所有 metadata 字段，新增字段可直接写入（dynamic mapping），但需要更新 explicit mapping 以确保新字段被正确索引为 keyword 类型。

### 2.4 Agent 架构现状（关键——v1 方案此处描述有误）

当前系统**已经是 Agent 架构**，不是"单次检索→生成"的单轮模式：

- `/api/v1/query.py:89` → 调用 `dispatch_agent()`（`server/agents/orchestrator.py`）
- `orchestrator.py:40` → `_AGENT_MAX_TURNS = 3`，Agent 最多运行 3 轮
- `qa_agent.py:75-78` → QA Agent 已挂载 `retrieve` 和 `lookup_glossary` 两个 tool
- `agents/tools/retrieve.py:16-22` → `retrieve(query, top_k)` 是 Agent 的 function tool
- Agent 已有 groundedness 判断：`retrieve.py:30` 检查 `bundle.groundedness == "grounded"` 时跳过重复检索
- Agent instructions 已扩展：retrieve 可选覆盖参数、lookup_clause 精确追踪、evidence 充足后停止、代词消解等行为规则

**结论**：不应在 `generation.py` 中另起 Agent Loop；应在 Phase 1 扩展现有 `retrieve` tool 的可选覆盖参数，并在 Phase 2 基于 eval 结果调优 QA Agent instructions / 条件工具。

### 2.5 检索流程（server/core/retrieval.py）

- **全局搜索**：默认不按 source 过滤，vector + BM25 搜索所有已索引文档
- **跨文档限流**：RRF 融合后，硬编码每 source 最多 5 条结果（`retrieval_fusion.py`）
- **Rerank 无 source 感知**：reranker 对所有 chunk 评分时不区分文档来源
- **已有交叉引用能力**：`retrieval.py:1131` `_fetch_cross_ref_chunks`（交叉引用图扩展）、`retrieval.py:1229` `_fetch_object_chunks_by_object_ids`（object_label 精确 lookup）、BM25 fallback 等机制已在运行

### 2.6 Query Understanding（server/core/query_understanding.py）

- 支持查询扩展（多查询生成）和查询分类
- `QueryAnalysis.filters` 类型为 `dict[str, str]`（`query_understanding.py:186`）
- filter helper（`retrieval_helpers.py:233`）当前仅识别 `source` 和 `sources` 两个 key
- **不识别**用户意图中的规范族、文档类型、版本偏好

---

## 3. 方案设计

### 3.1 设计原则

1. **渐进式改造**：在现有架构上增量扩展，不重写核心检索链路
2. **metadata 驱动**：通过丰富 chunk 元数据 + 过滤条件实现路由，不物理拆分 collection
3. **扩展现有 Agent，不新建 Agent**：在现有 QA Agent + retrieve tool 上增加参数和指令
4. **可验证**：每个阶段都可以通过 eval harness（`tests/eval/eval_retrieval.py`）量化质量变化
5. **安全回退**：意图识别不确定时退回全局搜索，保证不比当前差

### 3.2 整体架构与路由职责分工

**核心设计决策**：路由职责归 query understanding，不归 Agent。

```
用户提问
  │
  ▼
┌──────────────────────────────────────────────────────────────────┐
│  QA Agent (现有, server/agents/qa_agent.py, max_turns=3)          │
│                                                                   │
│  常规路径 (90%+ 的调用):                                           │
│  └─ retrieve(query, top_k)          ← 不传 filter 参数            │
│       └─ 内部 QU 自动路由                                         │
│                                                                   │
│  覆盖路径 (二次检索/对比/换规范族):                                  │
│  └─ retrieve(query, top_k,          ← 显式覆盖 QU 路由            │
│       standard_family="EN 1990")                                  │
│                                                                   │
│  精确补充 (Phase 2, eval 驱动):                                    │
│  └─ lookup_clause("EN 1990, 6.4.3.2(2)")  ← 确定性 ES 查找        │
└──────────────────────┬───────────────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────────────┐
│  retrieve tool 内部 (server/agents/tools/retrieve.py)             │
│                                                                   │
│  1. Query Understanding (analyze_query, 增强)                     │
│     ├─ 现有: 查询扩展、分类、target_hint                           │
│     └─ 新增: standard_family / doc_type_intent / version_pref     │
│              + 置信度 (confidence: high / low)                     │
│                                                                   │
│  2. Filter Construction (新增逻辑)                                │
│     ├─ Agent 显式传参 → 直接作为 hard filter (最高优先)             │
│     └─ QU 自动识别 → soft boost (Phase 1 保守策略，不排除候选)      │
│                                                                   │
│  3. Hybrid Retrieval (现有 + filter 注入)                          │
│     ├─ Milvus vector search (带新字段 filter expr)                │
│     ├─ ES BM25 search (带新字段 filter clause)                    │
│     └─ RRF fusion + 动态 per-source cap                          │
│                                                                   │
│  4. Rerank → 返回 evidence                                       │
└──────────────────────────────────────────────────────────────────┘
```

**路由决策优先级**：
1. Agent 显式传参 → 最高优先，直接覆盖 QU 结果（用于二次检索、对比检索）
2. QU 自动识别 → soft boost（即使高置信度也不在 Phase 1 自动 hard filter，避免错误过滤导致 recall 下降）
3. 现有 source/domain filter 保持 hard filter（兼容既有 `domain` / `source` 行为）
4. 无法识别 → 不加 filter/boost，退回全局搜索（保底，不比现在差）

### 3.3 Phase 1：元数据增强 + 查询路由 + 索引重建

#### 3.3.1 Chunk 元数据扩展

在 `ChunkMetadata`（`server/models/schemas.py`）中新增：

```python
class DocType(str, Enum):
    STANDARD = "standard"    # 规范原文
    GUIDE = "guide"          # 设计指南
    EXAMPLE = "example"      # 计算示例

class ChunkMetadata(BaseModel):
    # ... 现有字段 ...
    doc_type: DocType = DocType.STANDARD
    doc_version: str = ""           # "2004", "2023" 等（从文件名提取的年份）
    standard_family: str = ""       # "EN 1990", "EN 1992-1-1" 等（规范化族标识）
```

#### 3.3.2 文档类型自动识别

解析时根据文件名/内容特征自动判定 `doc_type`：

| 识别规则 | 类型 |
|----------|------|
| 文件名含 "DG_" 或 "指南" 或 "Designer's Guide" 或 "designers-guide" | `guide` |
| 文件名含 "示例" 或 "Worked Example" 或 "WS_" 或 "worked_example" | `example` |
| 文件名匹配 `(BS)?EN\s?\d{4}` 且不含上述关键词 | `standard` |
| 以上均不匹配 | 由用户在上传时选择（`/documents/parse` API 增加 `doc_type` 可选参数） |

版本号从文件名提取年份：`BSEN1992-1-1-2023` → `"2023"`，`EN1992-1-1_2004` → `"2004"`。

`standard_family` 通过正则提取并规范化：`BSEN1992-1-1-2023` → `"EN 1992-1-1"`，`DG_EN1992-1-1, -1-2` → `"EN 1992-1-1"`。

#### 3.3.3 索引 Schema 重建（v1 低估了此处成本）

**Milvus collection 必须 drop + recreate**。Milvus 不支持在线 ALTER schema，新增字段的唯一路径是重建：

1. 修改 `shared/milvus_schema.py` 的 `build_collection_schema()`，新增 3 个 VARCHAR 字段：

```python
fields = [
    FieldSchema("chunk_id", DataType.VARCHAR, is_primary=True, max_length=64),
    FieldSchema("embedding", DataType.FLOAT_VECTOR, dim=1024),
    FieldSchema("source", DataType.VARCHAR, max_length=128),
    FieldSchema("element_type", DataType.VARCHAR, max_length=16),
    # ── 新增 ──
    FieldSchema("doc_type", DataType.VARCHAR, max_length=16),
    FieldSchema("standard_family", DataType.VARCHAR, max_length=64),
    FieldSchema("doc_version", DataType.VARCHAR, max_length=16),
]
```

2. 修改 `pipeline/index.py:53-58` 的 insert data 列表，加入新字段：

```python
data = [
    [c.chunk_id for c in to_embed],
    embeddings,
    [c.metadata.source for c in to_embed],
    [c.metadata.element_type.value for c in to_embed],
    # ── 新增 ──
    [c.metadata.doc_type.value for c in to_embed],
    [c.metadata.standard_family for c in to_embed],
    [c.metadata.doc_version for c in to_embed],
]
```

3. `rebuild-indexes.sh` 脚本需要先 `utility.drop_collection()` 再重建。**这意味着执行期间搜索不可用**，需要在维护窗口执行或做蓝绿切换（用新 collection name 建好后再切）。

**ES mapping 更新**：在 index template / explicit mapping 中为新字段加 keyword 子字段：

```json
{
  "doc_type": { "type": "keyword" },
  "standard_family": { "type": "keyword" },
  "doc_version": { "type": "keyword" }
}
```

ES 支持 reindex，可以不停服务。

#### 3.3.4 Filter 数据契约统一

当前 `QueryAnalysis.filters` 是 `dict[str, str]`（`query_understanding.py:186`），filter helper 只认 `source`/`sources`（`retrieval_helpers.py:233`）。需要统一扩展，并明确区分**语义输入**和**检索过滤值**。

**扩展 QueryAnalysis**：

```python
@dataclass
class QueryAnalysis:
    # ... 现有字段 ...
    filters: dict[str, str | list[str]] = field(default_factory=dict)
    soft_boosts: dict[str, str | list[str]] = field(default_factory=dict)  # 新增
    # 约定的 key (filters 和 soft_boosts 共用):
    #   "source": str             — 单个 source 精确匹配（现有）
    #   "sources": list[str]      — 多 source OR 匹配（现有）
    #   "standard_family": str    — 规范族匹配（新增）
    #   "doc_type": str           — 文档类型（新增，值为 "standard"/"guide"/"example"）
    #   "doc_version": list[str]  — 版本年份列表（新增，值为 ["2022","2023"] 等已展开的年份）
    #
    # ⚠️ doc_version 始终是年份字符串列表，不是语义值 "new"/"current"。
    # 语义值在 build_filters_from_intent() 内通过 VERSION_YEAR_MAP 规范化。
```

**doc_version 契约（v3.1 修正：拆分语义输入 vs 检索过滤值）**：

QU 输出的 `version_pref` 是语义值（`"new"` / `"current"` / `"both"` / `"unspecified"`）。
Agent 覆盖参数的 `doc_version` 也接受语义值。
二者在进入 `filters` / `soft_boosts` dict **之前**，必须经过 `_normalize_version_pref()` 转为年份列表：

```python
VERSION_YEAR_MAP = {
    "new": ["2022", "2023", "2024", "2025"],
    "current": ["2002", "2004", "2005"],
}

def _normalize_version_pref(version_pref: str) -> list[str] | None:
    """将语义值转化为 Milvus/ES 可用的年份列表。返回 None 表示无法映射。"""
    return VERSION_YEAR_MAP.get(version_pref)
```

这保证 `doc_version` 在 Milvus expr 和 ES filter clause 中始终是年份字符串，不会泄漏 `"new"` / `"current"` 到检索层。

**扩展 filter helper**（`retrieval_helpers.py`）：

在 `_build_source_filter_clauses()` 中增加对 `standard_family`、`doc_type`、`doc_version` 的处理。新增 `_build_milvus_filter_expr()` 统一构建 Milvus boolean expression。

#### 3.3.5 Query Understanding 增强

在现有 `query_understanding.py` 的 `analyze_query()` prompt 中增加三个分类维度 + 置信度（复用同一次 LLM 调用）：

```
输入: 用户查询
输出 (新增):
  - standard_family: 用户提到或隐含的规范族，如 "EN 1992-1-1"；未明确则为 null
  - standard_family_confidence: "high" / "low"
      - high: 用户明确写了规范编号（"EN 1992-1-1 第 6.1 条"、"EN 1990 Expression (6.10)"）
      - low: 通过领域语义推断（"配筋率" → 可能是 EN 1992，但也可能出现在指南/示例中）
  - doc_type_intent: 用户想要的文档类型
      - "standard": 查条款原文（"规定了什么"、"第X条"、"公式"）
      - "guide": 要解释/理解（"怎么理解"、"为什么"、"背景"）
      - "example": 要计算方法（"怎么算"、"计算步骤"、"算例"）
      - "any": 不明确
  - version_pref: 版本偏好（语义值，非检索值）
      - "new": 明确提到新版/2023/BS EN
      - "current": 明确提到现行版/2004
      - "both": 想对比新旧版
      - "unspecified": 未提及
```

**Phase 1 保守过滤策略（核心设计）**：

```python
def build_filters_from_intent(
    intent,
    agent_overrides: dict | None = None,
) -> tuple[dict[str, str | list[str]], dict[str, str | list[str]]]:
    """返回 (hard_filters, soft_boosts)。
    
    hard_filters: 注入 Milvus expr / ES filter clause，严格排除不匹配文档
    soft_boosts:  注入 ES should clause 或 rerank 加权，偏好匹配但不排除其他
    """
    hard_filters = {}
    soft_boosts = {}

    # ── 优先级 1: Agent 显式覆盖 → 直接 hard filter ──
    if agent_overrides:
        if agent_overrides.get("standard_family"):
            hard_filters["standard_family"] = agent_overrides["standard_family"]
        if agent_overrides.get("doc_type"):
            hard_filters["doc_type"] = agent_overrides["doc_type"]
        if agent_overrides.get("doc_version"):
            years = _normalize_version_pref(agent_overrides["doc_version"])
            if years:
                hard_filters["doc_version"] = years
        return hard_filters, soft_boosts

    # ── 优先级 2: QU 自动识别 → soft boost ──
    # Phase 1 不让 QU 自动 hard filter，保护现有评测集 recall。
    # high-confidence hard filter 留到 20 本文件重建索引 + eval 后再决定。
    if intent.standard_family:
        soft_boosts["standard_family"] = intent.standard_family

    if intent.doc_type_intent in ("standard", "example"):
        soft_boosts["doc_type"] = intent.doc_type_intent
    if intent.doc_type_intent == "guide":
        soft_boosts["doc_type"] = "guide"
    # "any" → 不加任何 filter/boost

    if intent.version_pref in ("new", "current"):
        years = _normalize_version_pref(intent.version_pref)
        if years:
            soft_boosts["doc_version"] = years
    # "both" / "unspecified" → 不加 filter

    return hard_filters, soft_boosts
```

**soft_boosts 完整签名传递链路**：

```
1. analyze_query()
   → QueryAnalysis(filters={...}, soft_boosts={...})
   （QU 内部调用 build_filters_from_intent 填充两个 dict）
                    ↓
2. retrieve tool (_retrieve_impl, server/agents/tools/retrieve.py)
   → 合并 agent_overrides（如有）
   → retriever.retrieve(filters=hard_filters, soft_boosts=soft_boosts, ...)
                    ↓
3. HybridRetriever.retrieve() (server/core/retrieval.py)
   → 签名新增: soft_boosts: dict[str, str | list[str]] | None = None
   → hard_filters → _vector_search() Milvus expr
   → hard_filters → _bm25_search() ES filter clause
   → soft_boosts  → _bm25_search() ES should clause
                    ↓
4. _bm25_search() (server/core/retrieval_search.py:65)
   → 现有机制: preferred_element_type → should clause, boost 2.0 (line 87-93)
   → 新增（同机制）:
     soft_boosts["standard_family"] → {"term": {"standard_family": {"value": "...", "boost": 1.5}}}
     soft_boosts["doc_type"]        → {"term": {"doc_type": {"value": "...", "boost": 1.3}}}
     soft_boosts["doc_version"]     → {"terms": {"doc_version": [...], "boost": 1.3}}
                    ↓
5. _rerank() (server/core/retrieval_rerank.py:33)
   → 可选: 对 soft_boosts 匹配的 chunk score 做加权（×1.2）
   → 需 A/B 测试效果后决定是否启用
```

**关键对齐点**：
- `HybridRetriever.retrieve()` 签名新增 `soft_boosts` 参数
- `_bm25_search()` 的 `should_clauses` 列表已有 `preferred_element_type` boost（`retrieval_search.py:87-93`），新增 soft_boost 采用完全相同的 ES should clause 模式
- Milvus 不支持 should clause，soft_boosts 仅对 BM25 和 rerank 生效

**过滤策略决策表**：

| 场景 | standard_family | doc_type | doc_version | 策略 |
|------|----------------|----------|-------------|------|
| "EN 1992-1-1 第 6.1 条规定了什么" | soft: EN 1992-1-1 | soft: standard | — | 偏好目标规范，Phase 1 不自动排除其他 |
| "混凝土梁配筋率怎么算" | soft: EN 1992-1-1 | soft: example | — | 偏好 1992 和示例，但不排除其他 |
| "新版钢结构规范有什么变化" | soft: EN 1993-1-1 | — | soft: ["2022","2023","2024","2025"] | 偏好新版年份，不自动排除旧版 |
| "荷载组合的基本原则" | — | — | — | 全局搜索 |
| Agent 覆盖 retrieve(standard_family="EN 1990") | hard: EN 1990 | — | — | 显式覆盖 |

**安全回退**：任何维度无法识别 → 不加 filter/boost，退回全局搜索。

#### 3.3.6 检索层调整

**动态 per-source cap**（替换 `retrieval_fusion.py` 硬编码 5）：

```python
def _compute_per_source_cap(filters: dict, num_unique_sources: int) -> int | None:
    has_narrow_filter = "standard_family" in filters or "source" in filters
    if has_narrow_filter:
        return None  # 不限制
    if num_unique_sources <= 3:
        return 10
    elif num_unique_sources <= 10:
        return 5
    else:
        return 3
```

**Rerank source 标注**（可选，需 A/B 测试效果）：

在 `_rerank_text()`（`retrieval_rerank.py:20`）返回值前加 source 标注，保留现有逻辑（table/formula 用 content + object_label，其他用 embedding_text）：

```python
rerank_passage = f"[{chunk.metadata.source} | {chunk.metadata.doc_type}] {_rerank_text(chunk)}"
```

#### 3.3.7 retrieve tool 可选覆盖参数（Phase 1 实施）

当前 `retrieve(query, top_k)` 保持为**默认调用方式**。新增可选参数作为 Agent 的覆盖入口：

```python
@function_tool
async def retrieve(
    ctx: RunContextWrapper[QADeps],
    query: str,
    top_k: int = 8,
    standard_family: str | None = None,   # 覆盖 QU 自动识别
    doc_type: str | None = None,          # 覆盖 QU 自动识别
    doc_version: str | None = None,       # 覆盖 QU 自动识别
) -> str:
    """搜索欧洲规范知识库。通常只需传 query 和 top_k，内部自动路由。
    仅在二次检索、对比检索、或明确换规范族时传入可选参数以覆盖自动路由。"""
```

**内部逻辑**：如果 Agent 传了可选参数，将其作为 `agent_overrides` 传入 `build_filters_from_intent()`，优先级高于 QU 结果（见 3.3.5 的优先级设计）。

### 3.4 Phase 2：Agent Instruction 调优 + 条件 Tool（eval 驱动）

> **定位**：Phase 2 不是新增架构能力，而是在 Phase 1 eval 数据驱动下，补强 Agent 的指令和条件工具。
> 仅当 Phase 1 eval 暴露出可量化的缺口时才实施对应子项。

#### 3.4.1 更新 QA Agent Instructions

在 `_QA_AGENT_INSTRUCTIONS`（`qa_agent.py:20`）中更新多规范场景行为：

```
## 工具
- retrieve(query, top_k=8, standard_family=None, doc_type=None, doc_version=None):
  搜索规范知识库。**通常只传 query 和 top_k 即可**，系统自动识别规范族和文档类型。
  以下情况可传可选参数覆盖自动路由：
  · 二次检索时需要换一个规范族（如第一次查了 EN 1992，现在要查 EN 1990 的交叉引用内容）
  · 用户明确要求对比新旧版 → 分两次 retrieve，分别传 doc_version="new" 和 "current"
  · 用户明确要求看计算示例 → 传 doc_type="example"
  不确定该传什么时，不传。错误的 filter 比没有 filter 更糟糕。

- lookup_glossary(term): 查询术语表。

[如 Phase 1 eval 驱动需要:]
- lookup_clause(clause_ref): 按条款号精确查找规范条文。
  当证据中出现交叉引用（如 "see EN 1990, 6.4.3.2(2)"）且当前证据不含该条款时使用。
```

**关键指令变更**：
- 删除"最多调用 retrieve 2 次"的硬限制 → 改为依赖 groundedness 和 `_AGENT_MAX_TURNS=3` 自然约束
- 新增：当证据中出现跨规范引用时，允许通过 retrieve + standard_family 或 lookup_clause 追踪

#### 3.4.2 新增 lookup_clause tool（eval 驱动，条件实施）

**触发条件**：Phase 1 eval 的 Cross-ref Resolution 指标 < 85%，且失败样例主要是"引用了条款号但没有被召回"。

```python
@function_tool
async def lookup_clause(
    ctx: RunContextWrapper[QADeps],
    clause_ref: str,
) -> str:
    """按条款号精确查找规范条文。如 'EN 1992-1-1, 6.1(2)' 或 'EN 1990, Expression (6.10)'。
    比 retrieve 更精准但覆盖面更窄。仅用于追踪已知条款号的交叉引用。"""
```

内部实现：解析 `clause_ref` 提取 source + clause_id → ES 精确匹配（`clause_ids` keyword + `source` keyword filter）→ 不走向量检索。

#### 3.4.3 此方案与 v1/v2/v3 的关键区别

| 对比点 | v1（已废弃） | v2 | v3/v3.1（本版） |
|--------|-------------|-----|-------------------|
| 路由主体 | 新建 Agent Loop 自行决定 | Agent 通过 tool 参数决定 | **QU 自动路由为主，Agent 覆盖为辅** |
| retrieve 参数 | 全新 tool | 扩展为必填参数风格 | 扩展为**可选参数 escape hatch** |
| 过滤策略 | 一律 hard filter | 一律 hard filter | **QU 自动 soft boost；Agent 覆盖 hard filter** |
| lookup_clause | 预设实现 | 可选 | **eval 驱动，条件实施** |
| Agent instructions | 新写 | 鼓励传参 | **强调通常不传参，自动路由处理** |

### 3.5 解析优化（与上述独立）

#### 3.5.1 并行解析

将 `parse_all_pdfs()` 的串行 for 循环改为带信号量控制的并发：

```python
async def parse_all_pdfs(pdf_dir, config):
    pdf_paths = sorted(pdf_dir.glob("*.pdf"))
    semaphore = asyncio.Semaphore(config.parse_concurrency)  # 建议默认 3

    async def parse_with_semaphore(path):
        async with semaphore:
            return await parse_pdf(path, config)

    results = await asyncio.gather(*[parse_with_semaphore(p) for p in pdf_paths])
    return results
```

#### 3.5.2 Contextualize 并行

将 `contextualize.py` 中按 source 串行的外层循环改为并发（内层已有 semaphore）。

#### 3.5.3 预估提速

| 操作 | 当前（串行） | 优化后（并发 3） |
|------|-------------|-----------------|
| 20 文件解析 | ~90 min | ~30 min |
| Contextualize | ~40 min | ~15 min |
| Index | ~5 min | ~5 min（已较快） |
| **总计** | **~135 min** | **~50 min** |

### 3.6 示例文档的特殊处理

计算示例文档（470p、522p）与规范/指南有不同特征，建议针对性调整：

1. **Chunk size 加大**：示例中的计算步骤需要连续上下文才有意义，建议对 `doc_type=example` 的文档使用更大的 chunk size（如 1200 token vs 当前默认 800 token）
2. **Contextualize prompt 调整**：示例文档的 context summary 应强调"这是哪个条款的计算示例"，而非重复条款内容
3. **检索权重降低**：在非 example 意图的查询中，可对 example chunk 的分数做轻微折扣（如 ×0.8）

---

## 4. 实施计划

### Phase 1：元数据增强 + 查询路由 + 索引重建 + retrieve 覆盖参数（预计 5-7 天）

> **scope 澄清**：retrieve tool 的可选覆盖参数归入 Phase 1 最后一步，因为它只是将 Phase 1 的
> filter 管线暴露给 Agent，不依赖 eval 数据。Phase 2 仅包含 eval 驱动的增强（lookup_clause、
> instruction 调优）。

| 步骤 | 内容 | 涉及文件 | 验证 |
|------|------|----------|------|
| 1 | `ChunkMetadata` 增加 `doc_type`, `doc_version`, `standard_family` | `server/models/schemas.py` | 单元测试 |
| 2 | 文件名识别规则 + `/documents/parse` API 支持 `doc_type` 参数 | `pipeline/` 相关模块、`server/models/schemas.py:303` (`DocumentParseRequest` 加字段)、`server/api/v1/documents.py:403` (`_persist_parse_options` 写入)、`server/api/v1/documents.py:600` (upload 表单传递)、`server/services/pipeline_runner.py:149` (读取 options 传入 chunk metadata) | 20 个测试文件全部正确识别；API 手动指定 doc_type 能 override |
| 3 | Milvus schema 重建：新增 3 个 VARCHAR 字段 | `shared/milvus_schema.py` | `ensure_collection` 成功创建新 schema |
| 4 | Milvus insert 扩展：写入新字段 | `pipeline/index.py:53-58` | re-index 后 Milvus 查询验证新字段有值 |
| 5 | ES mapping 更新：新字段 keyword 索引 | `pipeline/index.py` ES 部分 | ES 查询验证新字段可过滤 |
| 6 | Filter + soft_boosts 契约：`QueryAnalysis` 新增 `soft_boosts` 字段，`retrieval_helpers.py` 支持新维度，`HybridRetriever.retrieve()` 签名新增 `soft_boosts` 参数，`_bm25_search()` should clause 扩展 | `query_understanding.py`, `retrieval_helpers.py`, `retrieval_search.py`, `retrieval.py` | 单元测试：hard filter 排除、soft boost 加权 |
| 7 | Query understanding prompt 增加意图识别 + 置信度 | `query_understanding.py` | prompt 调试 + 边界 case 测试 |
| 8 | 动态 per-source cap | `retrieval_fusion.py` | eval harness 对比 |
| 9 | `rebuild-indexes.sh` 更新：drop + recreate + 新 schema | `scripts/rebuild-indexes.sh` | 全量 re-index 成功 |
| 10 | `retrieve` tool 增加可选覆盖参数（standard_family, doc_type, doc_version） | `server/agents/tools/retrieve.py` | Agent 传参后 filter 生效 |
| 11 | 全量索引 20 个文件 + eval 基线 | — | `tests/eval/eval_retrieval.py` 对比基线 |

### Phase 2：Agent Instruction 调优 + 条件 Tool（eval 驱动，预计 2-3 天）

| 步骤 | 内容 | 文件 | 触发条件 |
|------|------|------|----------|
| 1 | Agent instructions 更新：多规范场景行为规则 | `server/agents/qa_agent.py` | Phase 1 eval 完成后 |
| 2 | （条件）新增 `lookup_clause` tool | `server/agents/tools/lookup_clause.py` | Cross-ref Resolution < 85% |
| 3 | 跨规范引用测试集 | `tests/eval/` | 对比 Phase 1 基线 |

### 解析优化（与上述独立，预计 1 天）

| 步骤 | 内容 | 验证 |
|------|------|------|
| 1 | `parse_all_pdfs` 并行化 | 20 文件解析计时对比 |
| 2 | `contextualize.py` 外层并行 | 计时对比 |

---

## 5. 风险与对策

| 风险 | 严重度 | 对策 |
|------|--------|------|
| Milvus 重建期间搜索不可用 | 高 | 维护窗口执行（数据量小，重建 <10min）；规模增大后再考虑蓝绿切换 |
| 文件名识别规则不够准确 | 中 | `/documents/parse` API 增加 `doc_type` 可选参数，用户可手动指定兜底 |
| QU 意图被错误 hard filter | 中 | **Phase 1 消解**：QU 自动结果只做 soft boost；hard filter 只由 Agent 显式覆盖触发 |
| Agent 过度使用覆盖参数 | 中 | Instructions 明确"通常不传参数，自动路由处理"；错误 filter 比没有 filter 更糟 |
| 新旧版条款号映射困难 | 低 | 不做自动映射，靠 Agent 分别 retrieve 两个版本 |
| 示例文档 chunk 噪声 | 中 | doc_type soft boost + Phase 1 的意图路由自然缓解 |
| 已有交叉引用能力可能已覆盖大部分场景 | — | Phase 1 eval 量化 Cross-ref Resolution，驱动 Phase 2 的 lookup_clause 决策 |

---

## 6. 评估方案

### 6.1 基线测试

在实施改动前，先用现有系统对 20 个文件做全量索引，跑 eval harness 记录基线指标：
- **检索评估**：`tests/eval/eval_retrieval.py`（完整检索 eval harness）
- 新增一批多规范场景的测试问题（覆盖跨规范引用、版本对比、类型区分）

> ⚠️ 注意：`tests/eval/test_eval_retrieval.py` 是 helper 单测，不是完整评估入口。完整 eval 是 `tests/eval/eval_retrieval.py`（见 `tests/eval/README.md:5`）。

### 6.2 对比测试

每个 Phase 实施后，跑同一测试集对比：

| 指标 | 含义 | 预期 |
|------|------|------|
| Recall@10 | 前 10 条结果中包含正确答案 chunk 的比例 | Phase 1 ≥ 基线 |
| Source Precision | 返回结果中 source 匹配用户意图的比例（新指标） | Phase 1 显著提升 |
| Type Precision | 返回结果中 doc_type 匹配用户意图的比例（新指标） | Phase 1 显著提升 |
| Cross-ref Resolution | 跨规范引用问题中，引用目标被成功召回的比例（新指标） | 评估残余缺口 |
| Answer Faithfulness | 生成答案中 claim 有 citation 支撑的比例 | 稳定或提升 |
| Latency P50/P95 | 端到端响应时间 | Phase 2 ≤ +20% |

### 6.3 评估驱动决策

- Phase 1 上线后，如果 Cross-ref Resolution 已达 >85%，Phase 2 的 `lookup_clause` tool 可暂缓
- 如果 Source Precision 在无 filter 时仍然很高，说明 rerank 已能区分，可简化 filter 逻辑
- 如果 Type Precision 在 "guide" 意图下不理想（guide 和 standard chunk 混淆），再考虑 rerank passage 加 source 标注
