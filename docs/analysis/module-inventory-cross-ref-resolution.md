# 交叉引用解析专项 — 模块盘点

## 模块清单

### 1. `pipeline/structure.py`

- 现职责：
  - Markdown/HTML 结构解析
  - 抽取 section、table、formula、image
  - 生成 `DocumentNode`
- 当前问题：
  - `extract_cross_refs()` 仅支持 `EN xxxx` 与 `Annex`
  - 不抽取 `Table / Figure / Expression / Clause`
  - 没有对象规范化与引用目标标准化
- 本次角色：
  - 成为“引用目标抽取”的第一入口

### 2. `pipeline/chunk.py`

- 现职责：
  - 生成 text/table/formula/image chunk
  - 为表格块补 `clause_ids = ["Table 3.1"]` 之类的标识
- 当前问题：
  - 只有表格块具备一定对象编号，条款/公式/图对象缺统一对象 ID
  - `cross_refs` 是弱字符串，不可用于稳定图解析
- 本次角色：
  - 为 chunk 建立统一 `object_id/object_type/object_label/ref_object_ids`

### 3. `pipeline/index.py`

- 现职责：
  - Milvus dense vector 写入
  - Elasticsearch 文本与 metadata 写入
- 当前问题：
  - ES mapping 没有为对象检索预留结构化字段
  - Milvus 仅用于 dense 检索，不承载对象关系
- 本次角色：
  - 扩展 ES mapping，支持 deterministic object lookup

### 4. `server/core/query_understanding.py`

- 现职责：
  - query rewrite
  - answer_mode / target_hint
- 当前问题：
  - 能识别 exact 倾向，但无法稳定表达“这题本质上要主条款 + 被引对象”
- 本次角色：
  - 抽取显式引用目标
  - 为 resolver 提供 `requested_objects`

### 5. `server/core/retrieval.py`

- 现职责：
  - exact probe
  - hybrid retrieval
  - groundedness
  - 临时 `ref_chunks` 补充
- 当前问题：
  - `_extract_internal_refs()` 是检索后 regex 补救，不是离线结构
  - `_fetch_cross_ref_chunks()` 没有引用图，只能按字符串搜索
  - groundedness 不检查“引用闭环是否完成”
- 本次角色：
  - 升级为在线 deterministic resolver 主战场

### 6. `server/core/generation.py`

- 现职责：
  - exact/open/exact_not_grounded 生成
  - 组织 sources / retrieval_context
- 当前问题：
  - `ref_chunks` 进入 prompt，但没有强制主位协议
  - 无 unresolved refs 提示
- 本次角色：
  - 强制 exact evidence pack 顺序
  - 只允许在闭环证据上给“可直接确认”的回答

### 7. `server/api/v1/query.py`

- 现职责：
  - 把分析结果传给 retriever 和 generator
- 本次角色：
  - 透传新的 resolver 结果字段
  - 给前端输出更完整的 retrieval/exact 诊断信息

### 8. `tests/server/test_retrieval.py`

- 现职责：
  - exact probe / groundedness / cross_ref 基础测试
- 当前问题：
  - 还没有“引用闭环”级测试
- 本次角色：
  - 扩充 deterministic resolver 的单测主阵地

### 9. `tests/server/test_generation.py`

- 现职责：
  - evidence pack、sources、retrieval_context 测试
- 本次角色：
  - 验证 exact 回答是否优先使用主条款 + 被引对象

### 10. `tests/eval/eval_retrieval.py` 与 `tests/eval/eval_results.json`

- 现职责：
  - retrieval/routing 评测
- 当前问题：
  - 对交叉引用专项覆盖不足
  - 没有“直接引用解析率”指标
- 本次角色：
  - 成为本次上线闸门的核心评测入口

## 推荐新增模块

### `shared/reference_graph.py` 或 `server/core/reference_resolution.py`

建议新增统一引用解析模块，负责：

- 规范对象 ID 规范化
- 引用字符串标准化
- 从 query 与 chunk 中提取引用目标
- 对 ES 做 object lookup
- 构造 `resolved_refs / unresolved_refs / evidence_graph`

## 数据模型建议

建议新增或扩展字段：

- `object_type`: `clause | table | figure | expression | annex`
- `object_label`: 如 `Table 3.1`
- `object_id`: 如 `en1992-1-1-2004#table:3.1`
- `object_aliases`: 同义写法与规范化写法
- `ref_labels`: 原始引用字符串
- `ref_object_ids`: 已解析的目标对象 ID 列表
- `is_primary_object`: 该 chunk 是否可直接作为对象主内容

## 模块复杂度判断

```text
┌────────────────────────────────────┬────────┬──────────────┬────────┐
│ 模块                               │ 改动级 │ 风险         │ 备注   │
├────────────────────────────────────┼────────┼──────────────┼────────┤
│ pipeline/structure.py              │ 高     │ 高           │ 离线抽取入口 │
│ pipeline/chunk.py                  │ 高     │ 高           │ 元数据模型核心 │
│ pipeline/index.py                  │ 中     │ 中           │ ES mapping 变更 │
│ server/core/query_understanding.py │ 中     │ 中           │ query target 补强 │
│ server/core/retrieval.py           │ 很高   │ 很高         │ 在线主逻辑核心 │
│ server/core/generation.py          │ 中     │ 高           │ 回答口径闸门 │
│ tests/server/*                     │ 高     │ 低           │ 必须同步扩充 │
│ tests/eval/*                       │ 高     │ 中           │ 上线闸门 │
└────────────────────────────────────┴────────┴──────────────┴────────┘
```
