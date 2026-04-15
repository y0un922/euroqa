# 交叉引用解析专项 — 任务拆解

## 概述

目标：建立一条可生产落地的“规范内部交叉引用解析”链路，使 exact 问题在涉及 `Table / Figure / Expression / Clause` 时能够：

- 稳定找到被引对象
- 把被引对象提升为主证据
- 在证据不闭环时明确降级

分为 5 个阶段。

---

## Phase 1: 引用对象模型与离线引用图

> 目标：把 chunk 升级为可寻址的规范对象，并在离线阶段建立引用边

### P1-T1: 扩展内部引用抽取规则
- **优先级**: P0
- **工作量**: M
- **并行通道**: A
- **文件**: `pipeline/structure.py`, `tests/pipeline/test_structure.py`
- **内容**:
  - 让 `extract_cross_refs()` 支持 `Table/Figure/Expression/Clause/Section`
  - 保留原始字符串与标准化写法
- **验收**:
  - 能正确抽取 `Table 3.1`, `Figure 3.3`, `Expression (3.14)`, `3.1.7`

### P1-T2: 建立规范对象标识
- **优先级**: P0
- **工作量**: L
- **并行通道**: B
- **文件**: `pipeline/chunk.py`, `server/models/schemas.py`, `tests/pipeline/test_chunk.py`
- **内容**:
  - 为 clause/table/formula/image chunk 补 `object_type/object_label/object_id/object_aliases`
- **验收**:
  - `Table 3.1` 唯一映射到一个稳定 `object_id`

### P1-T3: 生成引用边
- **优先级**: P0
- **工作量**: L
- **并行通道**: C
- **文件**: `pipeline/chunk.py`, 新增 `shared/reference_graph.py` 或同类模块
- **内容**:
  - 把 chunk 中引用解析为 `ref_object_ids`
  - 保留 unresolved labels
- **依赖**: P1-T1, P1-T2
- **验收**:
  - `3.1.7` 的 chunk 可指向 `Table 3.1`, `Figure 3.3`, `Figure 3.4`, `Figure 3.5`

### P1-T4: 扩展索引字段
- **优先级**: P0
- **工作量**: M
- **并行通道**: D
- **文件**: `pipeline/index.py`
- **内容**:
  - ES mapping 增加 `object_*`、`ref_*` 字段
- **验收**:
  - ES 可直接按 `object_id` / `object_label` 精确检索

### P1-T5: 重建与校验索引脚本
- **优先级**: P0
- **工作量**: M
- **并行通道**: E
- **文件**: `scripts/rebuild-indexes.sh` 及相关脚本
- **内容**:
  - 支持新字段重建
  - 输出对象统计和 unresolved ref 报告
- **依赖**: P1-T4
- **验收**:
  - 可输出每份文档的对象数、引用边数、未解析引用数

---

## Phase 2: 在线 deterministic resolver

> 目标：在线检索阶段先找主命中，再按引用图补齐证据

### P2-T1: query understanding 补 `requested_objects`
- **优先级**: P1
- **工作量**: M
- **并行通道**: A
- **文件**: `server/core/query_understanding.py`, `server/models/schemas.py`
- **内容**:
  - 从问题中显式抽取 `Table 3.1`、`3.1.7` 这类目标
- **验收**:
  - 对 exact 引用型问题输出结构化对象 hint

### P2-T2: 新增 resolver 主逻辑
- **优先级**: P0
- **工作量**: XL
- **并行通道**: B
- **文件**: `server/core/retrieval.py`, 新增 `server/core/reference_resolution.py`
- **内容**:
  - 主命中后，按 `requested_objects + ref_object_ids` 解析被引对象
  - 返回 `resolved_refs/unresolved_refs/evidence_graph`
- **依赖**: P1 全部完成
- **验收**:
  - 对 `3.1.7 + Table 3.1` 能输出闭环证据图

### P2-T3: 引用对象提权排序
- **优先级**: P0
- **工作量**: L
- **并行通道**: C
- **文件**: `server/core/retrieval.py`
- **内容**:
  - 被主条款直接引用的对象高于一般相关 chunk
- **依赖**: P2-T2
- **验收**:
  - `Table 3.1` 进入 primary exact evidence，而非仅做旁证

### P2-T4: 引用闭环 groundedness
- **优先级**: P0
- **工作量**: L
- **并行通道**: D
- **文件**: `server/core/retrieval.py`
- **内容**:
  - exact 模式新增 `reference_closure` 判断
- **依赖**: P2-T2
- **验收**:
  - 主条款要求查表但表未覆盖时，必须降级

---

## Phase 3: 生成层证据闸门

> 目标：回答必须服从闭环证据，而不是自由挑片段

### P3-T1: 重构 exact evidence pack
- **优先级**: P0
- **工作量**: L
- **并行通道**: A
- **文件**: `server/core/generation.py`
- **内容**:
  - 固定顺序：primary clause -> direct referenced objects -> support context
- **验收**:
  - prompt 中主位顺序稳定

### P3-T2: unresolved refs 显式暴露
- **优先级**: P1
- **工作量**: M
- **并行通道**: B
- **文件**: `server/core/generation.py`, `server/api/v1/query.py`, `server/models/schemas.py`
- **内容**:
  - 在 `retrieval_context` 或调试字段中暴露未解析引用
- **依赖**: P2-T2
- **验收**:
  - 前后端能看到 exact 降级原因

### P3-T3: sources 顺序与证据顺序对齐
- **优先级**: P1
- **工作量**: S
- **并行通道**: C
- **文件**: `server/core/generation.py`
- **内容**:
  - `sources` 先出主条款和直接被引对象
- **验收**:
  - 前端证据列表第一屏就是工程师真正该看的证据

### P3-T4: 受限 LLM fallback 预留点
- **优先级**: P2
- **工作量**: M
- **并行通道**: D
- **文件**: 设计接口，不一定同阶段实现
- **内容**:
  - 仅对 unresolved refs 允许补查
  - 限制深度 1、调用次数 3、文档域受限
- **验收**:
  - 仅作为增强，不影响 deterministic 主链

---

## Phase 4: 专项评测与回归门禁

> 目标：把交叉引用质量变成可量化门禁

### P4-T1: 建专项题库
- **优先级**: P0
- **工作量**: M
- **并行通道**: A
- **文件**: `tests/eval/*`
- **内容**:
  - 新增 exact cross-ref 题型：
    - 条款 -> 表
    - 条款 -> 图
    - 条款 -> 公式
    - 条款 -> 条款
    - 多跳链
    - 同号噪音干扰
- **验收**:
  - 至少 20 道覆盖生产高风险问法

### P4-T2: 指标与报告扩展
- **优先级**: P0
- **工作量**: M
- **并行通道**: B
- **文件**: `tests/eval/eval_retrieval.py`
- **内容**:
  - 新增：
    - `direct_ref_resolution_rate`
    - `reference_closure_rate`
    - `noise_intrusion_rate`
- **验收**:
  - 评测输出可直接作为上线门禁

### P4-T3: 单测补齐
- **优先级**: P0
- **工作量**: L
- **并行通道**: C
- **文件**: `tests/server/test_retrieval.py`, `tests/server/test_generation.py`
- **内容**:
  - 引用闭环、对象提权、降级逻辑、source 顺序
- **依赖**: P2, P3
- **验收**:
  - 关键链路均有可复现单测

### P4-T4: 基线对比与验收
- **优先级**: P0
- **工作量**: S
- **并行通道**: D
- **文件**: 评测输出报告
- **依赖**: P4-T1, P4-T2, P4-T3
- **验收**:
  - 达到里程碑门槛后才允许进入灰度

---

## Phase 5: 上线与灰度

> 目标：安全上线，不把实验逻辑直接推到工地生产

### P5-T1: 新旧索引并行
- **优先级**: P0
- **工作量**: M
- **并行通道**: A
- **内容**:
  - 支持影子索引或版本化索引

### P5-T2: 影子评测与日志
- **优先级**: P0
- **工作量**: M
- **并行通道**: B
- **内容**:
  - 线上记录 unresolved refs、closure 失败、噪音候选

### P5-T3: 灰度放量
- **优先级**: P1
- **工作量**: S
- **并行通道**: C
- **内容**:
  - 先 exact 问题，后复杂引用问法

### P5-T4: 回滚预案
- **优先级**: P0
- **工作量**: S
- **并行通道**: D
- **内容**:
  - 索引回切、开关回退、日志保留

---

## 并行执行矩阵

```text
Phase 1: [A 抽取规则] [B 对象标识] [D 索引字段] [E 重建脚本预备]
         -> [C 引用边] -> [E 重建校验]

Phase 2: [A requested_objects] [B resolver 主逻辑]
         -> [C 对象提权] [D 闭环 groundedness]

Phase 3: [A exact evidence pack] [B unresolved refs 暴露] [C source 顺序]
         -> [D 受限 fallback 预留]

Phase 4: [A 专项题库] [B 评测指标] [C 单测补齐]
         -> [D 基线验收]

Phase 5: [A 新旧索引并行] [B 影子评测日志] [D 回滚预案]
         -> [C 灰度放量]
```
