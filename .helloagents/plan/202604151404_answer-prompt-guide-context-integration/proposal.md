# 变更提案: answer-prompt-guide-context-integration

## 元信息
```yaml
类型: 优化
方案类型: implementation
优先级: P0
状态: 已确认
创建: 2026-04-15
```

---

## 1. 需求

### 背景
甲方已经明确给出新的回答整理提示词，要求系统不再偏向“自由生成式问答模板”，而是转为“基于已检索证据进行工程化整理”的输出模式。现有后端虽然已经有 `open / exact / exact_not_grounded` 三套模板，但仍以回答模式为中心组织提示词，没有完整映射到“用户问题 + 规范证据 + 证据元数据 + 指南证据”的输入结构，也缺少单独的 `guide_context` 透传链路。

### 目标
1. 将新的“回答整理助手”提示词完整接入现有问答主链路，并全量替换当前三种回答模板。
2. 为“如何计算 / 如何取值 / 公式推导 / 参数确定 / 设计步骤”等问题增加单独的 `guide_context` 检索与透传能力。
3. 保持 `/query` 与 `/query/stream` 在模板选择、上下文透传和返回字段上的一致性。
4. 在正式修改前创建 checkpoint commit，方便用户在结果不符合预期时直接回退。

### 约束条件
```yaml
时间约束: 本次会话内完成方案、实现、验证
性能约束: 不引入明显的流式响应额外分叉；新增指南检索只在相关问题触发
兼容性约束: 现有 API 返回结构保持兼容，新增字段应为可选
业务约束: 指南只能作为帮助理解和参考计算过程的补充，不能替代规范条文本身
```

### 验收标准
- [ ] `open / exact / exact_not_grounded` 三种模式统一切换到新的“证据整理助手”输出规则，且不再保留旧模板段落约束。
- [ ] 计算/取值/步骤类问题可单独携带 `guide_context`，非相关问题不强制检索指南。
- [ ] `/query` 与 `/query/stream` 都能返回与新链路一致的上下文快照，并保持行为一致。
- [ ] 后端回归测试覆盖提示词构建、指南上下文透传、流式 done payload、非流式响应。

---

## 2. 方案

### 技术方案
采用“最小侵入接入”方案，在现有后端主链路上做集中改造：

- 保留 `query_understanding.py` 现有问题分型和 `answer_mode` 路由，不新增第二套路由器。
- 在 `retrieval.py` 的 `RetrievalResult` 中新增指南证据结果，仅对计算/取值/步骤类问题且问题与 `DG_EN1990` 明显相关时触发专用检索。
- 在 `generation.py` 中重构系统提示词与用户提示词构建方式，统一改为“回答整理助手”输入模型：
  - 用户问题
  - 已检索规范证据 `retrieved_context`
  - 证据元数据 `metadata`
  - 可选指南证据 `guide_context`
- 在 `schemas.py` 和 `query.py` 中将新增的指南上下文快照透传到流式与非流式输出。
- 使用测试先约束新提示词结构和指南链路，再完成实现。

### 影响范围
```yaml
涉及模块:
  - server.models.schemas: 扩展 retrieval_context / guide_context 响应结构
  - server.core.retrieval: 增加 guide_context 检索结果与触发条件
  - server.core.generation: 全量替换回答模板与 prompt 组装
  - server.api.v1.query: 透传新增上下文到 /query 与 /query/stream
  - tests.server.test_generation: 覆盖提示词与上下文组装
  - tests.server.test_api: 覆盖 API 返回与流式 done payload
预计变更文件: 6-8
```

### 风险评估
| 风险 | 等级 | 应对 |
|------|------|------|
| 全量替换模板后破坏现有 exact 问答守边界行为 | 高 | 用测试锁定“仅基于证据、不编造、不扩答”的规则 |
| 指南检索触发条件过宽，导致无关问题带入 DG 证据 | 中 | 只在 `QuestionType.CALCULATION / PARAMETER` 且问题命中步骤/计算/取值语义时触发 |
| 流式和非流式链路透传字段不一致 | 高 | 同步改 `generate_answer` / `generate_answer_stream` 与 API 测试 |
| 当前工作区已有大量未提交变更，checkpoint commit 范围超出本任务 | 中 | 在执行前明确使用 checkpoint commit 记录“当前工作区整体状态”，作为用户指定的回退点 |

---

## 3. 技术设计

### 架构设计
```mermaid
flowchart TD
    A[query_understanding] --> B[retrieval main chunks]
    A --> C[guide retrieval trigger]
    B --> D[generation prompt assembler]
    C --> D
    D --> E[/query JSON response]
    D --> F[/query/stream done payload]
```

### API设计
#### POST `/api/v1/query`
- **请求**: 保持现有结构不变
- **响应**: `QueryResponse.retrieval_context` 增加可选 `guide_chunks`，并保留现有 `chunks / parent_chunks / ref_chunks / resolved_refs / unresolved_refs`

#### POST `/api/v1/query/stream`
- **请求**: 保持现有结构不变
- **响应**: `done` 事件中的 `retrieval_context` 同步增加可选 `guide_chunks`

### 数据模型
| 字段 | 类型 | 说明 |
|------|------|------|
| `guide_chunks` | `list[dict[str, object]]` | 指南文档检索结果快照，仅在相关问题时返回 |
| `guide_context` | `str | None` | 生成阶段传给 LLM 的指南证据文本块 |
| `metadata_context` | `str` | 从检索 chunk 元数据整理出的文档名、章节号、页码等信息块 |

---

## 4. 核心场景

### 场景: 规范条文问答统一走证据整理模板
**模块**: `server.core.generation`
**条件**: 任意问答请求进入生成阶段
**行为**: 使用新的整理式 system prompt 与 user prompt 替换旧模板
**结果**: 回答围绕“直接结论、依据与说明、计算步骤、指南参考案例、依据位置”组织，且只基于证据作答

### 场景: 计算类问题补充指南证据
**模块**: `server.core.retrieval`
**条件**: 问题属于计算/取值/步骤类，且适合使用 `DG_EN1990`
**行为**: 单独检索 `DG_EN1990` 相关片段，并透传为 `guide_context`
**结果**: 指南只作为补充说明或案例来源，不覆盖规范原文结论

### 场景: 流式与非流式输出保持一致
**模块**: `server.api.v1.query`
**条件**: `/query` 或 `/query/stream`
**行为**: 使用同一套 retrieval context 结构返回
**结果**: 前端或调用方可一致读取主规范证据和指南证据快照

---

## 5. 技术决策

### answer-prompt-guide-context-integration#D001: 采用最小侵入接入，而不是新增独立装配层
**日期**: 2026-04-15
**状态**: ✅采纳
**背景**: 本次任务强调“先接进去、可快速回退”，不适合引入大范围结构重构。
**选项分析**:
| 选项 | 优点 | 缺点 |
|------|------|------|
| A: 在现有 retrieval/generation 链路上最小侵入接入 | 改动集中、回退简单、流式/非流式容易保持一致 | `generation.py` 继续偏重 |
| B: 新增独立 prompt assembler / evidence bundle 层 | 长期结构更清晰 | 本次重构范围过大、回退成本高 |
**决策**: 选择方案A
**理由**: 更符合当前任务的交付目标和回退诉求，能在单次会话内完成实现和验证。
**影响**: 主要影响 `server.core.retrieval`、`server.core.generation`、`server.api.v1.query` 和测试层。

### answer-prompt-guide-context-integration#D002: 指南证据采用“条件触发 + 独立透传”，不混入主规范 evidence pack
**日期**: 2026-04-15
**状态**: ✅采纳
**背景**: 甲方提示词明确要求指南只能作为补充，不能替代规范条文本身。
**选项分析**:
| 选项 | 优点 | 缺点 |
|------|------|------|
| A: 指南证据与规范证据分开透传 | 边界清晰，提示词约束更稳 | 需要扩展返回结构 |
| B: 直接把指南 chunk 混到主检索结果里 | 实现快 | 容易让模型把指南当规范依据 |
**决策**: 选择方案A
**理由**: 能在 prompt 中明确区分“规范依据”和“指南参考案例”，更符合甲方要求。
**影响**: 需要扩展 `RetrievalResult`、`RetrievalContext` 和 API done payload。
