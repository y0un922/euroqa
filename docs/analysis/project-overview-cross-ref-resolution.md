# 交叉引用解析专项 — 架构总览

## 任务目标

为 Eurocode QA 建立一条可生产落地的“规范内部交叉引用解析”主链路，解决以下问题：

- 用户问题命中主条款后，系统无法稳定找到该条款引用的 `Table / Figure / Expression / Clause`
- 已补回的引用对象没有被当作主证据强约束使用，导致噪音片段挤占答案主位
- exact 问题在“部分相关”与“直接依据”之间缺少明确闸门

本次规划目标不是“提高一点召回率”，而是建立一条可审计、可回归、可灰度上线的工程链路。

## 当前系统链路

现有主链路：

1. `server/core/query_understanding.py`
   - 负责 query rewrite、路由、target hint
2. `server/core/retrieval.py`
   - exact probe + 向量检索 + BM25 + rerank + `ref_chunks` 补充
3. `server/core/generation.py`
   - 根据 `chunks + ref_chunks + parent_chunks` 生成 exact/open/exact_not_grounded 回答
4. `pipeline/*`
   - 负责结构化解析、chunk 构建、Milvus/ES 索引

## 已验证事实

### 1. 不是向量库缺块

已核查：

- `data/debug_runs/20260409T160508Z_bf7c07a5/artifacts/EN1992-1-1_2004/stage3_chunks.json`
- Milvus `eurocode_chunks`
- Elasticsearch `eurocode_chunks`

结论：

- `Table 3.1` 已存在于离线 chunk、ES、Milvus 三处
- `Table 3.1` 对应表格块可通过 `clause_ids = "Table 3.1"` 精确命中
- 当前 `HybridRetriever` 实测时也能把 `Table 3.1` 找回到 `ref_chunks`

### 2. 真正问题在引用解析与证据使用协议

当前缺陷：

- `pipeline/structure.py` 的 `extract_cross_refs()` 只提取 `EN xxxx` 和 `Annex X`
- 内部对象引用 `Table 3.1 / Figure 3.3 / Expression (3.14) / 3.1.7` 没有被离线结构化
- `retrieval.py` 只能在检索后从正文用 regex 临时抓内部引用
- `generation.py` 虽然接收 `ref_chunks`，但没有“引用对象必须进入主证据”的强协议

## 根因归纳

### 根因 A：对象模型缺失

系统有 chunk，但没有统一的“规范对象”层：

- 条款对象：`3.1.7`
- 表对象：`Table 3.1`
- 图对象：`Figure 3.3`
- 公式对象：`Expression (3.14)`

没有对象层，就没有稳定的对象 ID、别名、引用边、覆盖率统计。

### 根因 B：引用边在离线阶段未建图

当前 `cross_refs` 只是一组非常弱的字符串字段，而且不覆盖最关键的内部表图公式引用。

结果：

- 在线阶段无法确定“一条证据需要补哪些被引对象”
- 只能靠 prompt 或临时检索补救

### 根因 C：exact groundedness 未把“引用闭环”作为约束

对于这类问题：

- 主条款说“见 Table 3.1”
- 如果没有 `Table 3.1`，则证据实际上不闭环

当前 groundedness 判断仍可能把只有主条款、没有表格对象的结果视为可回答，风险过高。

## 目标架构

推荐采用：

`离线确定性引用图 + 在线确定性解析器 + 回答前证据闸门`

流程：

1. 离线解析阶段抽取规范对象和引用边
2. 索引阶段把对象标识、别名、引用关系写入 ES 元数据
3. 在线检索先找主命中，再根据引用图补齐被引对象
4. exact 模式下做“证据闭环检查”
5. 只有闭环成立时，才允许 LLM 以“直接依据”口吻回答

## 不推荐的主方案

不建议把“LLM 阅读已检索内容后自主调用 tool 去找引用”作为生产主链路。

原因：

- 稳定性差：相同问题可能走出不同工具路径
- 可审计性差：难以解释某次为何补了 A 没补 B
- 线上成本和时延不可控
- 回归验证困难

该能力可以保留为受限 fallback，但不能作为主方案。

## 推荐原则

- 主路径必须 deterministic
- LLM 只能在“证据齐备后”负责组织答案，不负责定义证据边界
- 引用对象缺失时必须显式降级，而不是默默用相关片段代替
- 任何上线都必须以专项评测集和线上日志指标为闸门
