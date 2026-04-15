# 精确型规范问答双通道与证据闸门 — 设计文档

> Version: 1.0
> Date: 2026-04-10
> Status: Draft

## 1. 问题陈述

当前 Eurocode QA 系统的主链路是：

1. `query_understanding` 将中文问题扩展为英文检索查询
2. `retrieval` 执行向量检索 + BM25 + rerank
3. `generation` 使用固定结构化模板生成中文回答

这条链路对“开放式解释问题”表现尚可，但对一类更强调直接条文依据的问题会系统性失真。典型表现不是“找不到任何相关内容”，而是：

1. 检索结果中混入大量相关但不直接回答问题的条文
2. 生成阶段将这些泛相关片段扩写成一篇结构完整、但不够精确的答案
3. 最终输出把“相关内容”包装成“直接依据”

该问题不是单个问法或单个条文的偶发错误，而是一类系统性故障。一个典型例子是：

- 用户问“欧标的截面计算的基本假设前提是什么”
- 系统实际检索到的证据里既包含 EN 1992-1-1 6.1 的直接假设条文，也包含 5.8 一般方法、B 区 / D 区、双向弯曲等相关内容
- 由于当前排序与生成逻辑没有把“直接条文”作为唯一主证据，最终答案会把周边相关条款拼成一段看似完整、但并不精确的回答

因此，本次改造不针对单个错例做微调，而是针对“精确型规范问答失败”这一类问题建立新的问答路径。

## 2. 目标

### 2.1 本次目标

1. 将用户问题区分为两类问答模式：
   - `exact`：用户期待直接条文、定义、假设、公式、限值、条款定位
   - `open`：用户期待解释、机理分析、综合说明或计算路径说明
2. 对 `exact` 问题建立单独的高精度检索路径 `exact probe`
3. 在生成前增加 groundedness gate，用于判断当前证据是否足以支撑“直接回答”
4. 为 `exact`、`open`、`exact_not_grounded` 三种状态分别设计回答模板
5. 建立一组“精确型规范问答”验证样例和评测指标，作为后续回归基线

### 2.2 非目标

- 不重构整套向量检索、Milvus、ES 或 rerank 基础设施
- 不替换现有 LLM provider 或模型配置
- 不在本次改造中解决所有开放式工程问答质量问题
- 不在本次改造中引入多阶段 agent 协作式回答生成
- 不在本次改造中改变前端引用展示与 evidence panel 的交互

---

## 3. 问题分类与总体方案

### 3.1 问题类型划分

本次改造把现有问答分成两个顶层模式：

- `exact`
  - 定义类：`什么是 ...`
  - 假设类：`基本假设 / 前提 / 采用什么假定`
  - 适用性类：`适用于什么情况 / 哪些区域 / 哪类构件`
  - 公式类：`公式是什么 / 表达式是什么`
  - 限值类：`限值是多少 / 推荐值是什么 / 可取值范围`
  - 定位类：`第几条 / 哪一章 / 哪张表 / 哪个公式`
- `open`
  - 机理解释
  - 影响因素
  - 综合说明
  - 多条文联立解释
  - 开放式工程建议

### 3.2 总体方案

采用“LLM-first routing + rule guardrails + retrieval-grounded validation”的双通道设计。

整体流程如下：

```text
用户问题
  -> query_understanding
      -> LLM 初判 answer_mode / intent_label / target_hint
      -> 规则兜底与修正
  -> if answer_mode = exact
      -> exact probe 检索
      -> groundedness gate
      -> final_mode = exact | exact_not_grounded
  -> else
      -> final_mode = open
  -> generation
      -> 按 final_mode 选择回答模板
```

这意味着：

1. “你在问什么”主要由 LLM 负责识别
2. “规范里有没有直接证据”由检索与 groundedness gate 负责确认
3. 生成模板必须服从最终证据状态，而不是仅服从意图分类

---

## 4. Query Understanding：LLM 优先分流

### 4.1 设计原则

分流不采用纯正则分类，也不采用“纯 LLM 决定一切”。

原因如下：

- 纯正则的问题在于覆盖性差，容易被问法变体打穿
- 纯 LLM 的问题在于即使意图识别正确，也不能单独保证文档里确实存在直接证据

因此分流采用：

1. `LLM 主判`
2. `规则校正`
3. `检索反证`

### 4.2 新增输出字段

在 [server/core/query_understanding.py](/Volumes/software/webdav/Euro_QA/server/core/query_understanding.py) 的现有 `QueryAnalysis` 基础上新增：

```python
answer_mode: Literal["exact", "open"] | None
intent_label: str | None
intent_confidence: float | None
target_hint: dict[str, str | None] | None
reason_short: str | None
```

建议 `intent_label` 的枚举至少包含：

- `definition`
- `assumption`
- `applicability`
- `formula`
- `limit`
- `clause_lookup`
- `explanation`
- `mechanism`
- `calculation`

### 4.3 LLM 分流器输入

分流器输入应保持轻量，仅包含：

1. 用户原始问题
2. glossary 命中的术语提示
3. 显式过滤线索（如文档编号、章节号、表号、公式号）
4. 可选的最近一轮对话上下文

### 4.4 LLM 分流器输出 Schema

分流器建议输出如下 JSON：

```json
{
  "answer_mode": "exact|open",
  "intent_label": "definition|assumption|applicability|formula|limit|clause_lookup|explanation|mechanism|calculation",
  "target_hint": {
    "document": "EN 1992-1-1",
    "clause": "6.1",
    "object": "basic assumptions"
  },
  "confidence": 0.0,
  "reason_short": "asks for direct normative assumptions of a section"
}
```

约束：

- `target_hint` 只作为检索 hint，不是事实承诺
- 低置信度或格式错误时，必须允许系统回退到规则兜底
- `reason_short` 仅用于日志和调试，不直接暴露给前端回答

### 4.5 规则兜底

规则层不负责主判，只做两件事：

1. 明显的强信号修正
   - 条款号、表号、公式号、章节号
   - “基本假设”“适用条件”“公式是什么”“第几条”等强显式问法
2. LLM 异常与低置信度回退

这里允许继续使用正则，但其角色从“分类器”降级为“guardrail”。

---

## 5. Retrieval：Exact Probe 与 Groundedness Gate

### 5.1 Exact Probe 的职责

`exact probe` 不是完整检索替代品，它的目标只有三个：

1. 快速验证是否存在直接回答该问题的条文
2. 为 `exact` 问题提供高精度候选
3. 为 groundedness gate 提供可判断的锚点证据

它不负责扩大召回面，也不负责综合解释。

### 5.2 Exact Probe 的检索顺序

对于 `answer_mode=exact` 的问题，probe 优先级应为：

1. `section_path` / 标题命中
2. `clause_ids` 命中
3. `match_phrase` 精确短语命中
4. `content` 中的规范句式命中
5. BM25 全文命中
6. 向量检索补充

当前 [server/core/retrieval.py](/Volumes/software/webdav/Euro_QA/server/core/retrieval.py) 的 BM25 只搜索 `content` 和 `embedding_text`。本次改造需要把以下字段纳入检索与加权：

- `source_title`
- `section_path`
- `clause_ids`

### 5.3 直接锚点定义

不同 `intent_label` 需要不同的锚点类型：

- `definition`
  - `X is ...`
  - `X means ...`
  - `For the purpose of this standard...`
- `assumption`
  - `the following assumptions are made`
  - `plane sections remain plane`
  - `... is ignored`
- `applicability`
  - `This section applies to...`
  - `applies to...`
  - `for members...`
- `formula` / `limit`
  - 明确公式块
  - `Expression (6.x)`
  - `may be taken as`
  - `shall be limited to`

仅有“相关章节”而没有直接锚点，不足以判定为 `grounded`。

### 5.4 Groundedness Gate

在 exact probe 之后引入 groundedness gate。判定结果分三档：

- `grounded`
  - 命中与 `intent_label` 对应的直接锚点
  - 且来源文档与 `target_hint` 不冲突
  - 最终模式：`exact`
- `partially_grounded`
  - 找到了相关章节或相关条款
  - 但没有直接定义句 / 假设句 / 公式句 / 限值句
  - 最终模式：`exact_not_grounded`
- `ungrounded`
  - 只有泛相关内容
  - 或证据跨文档漂移明显
  - 最终模式：`exact_not_grounded`

### 5.5 Why not direct fallback to open

用户问的是精确型问题时，不能因为 probe 没命中直接条文，就自动切换成开放式解释答案。

否则系统会再次走回“相关内容冒充直接依据”的旧路径。

因此当 `answer_mode=exact` 但 groundedness 不足时，必须进入 `exact_not_grounded`，而不是直接转为 `open`。

---

## 6. Generation：三种回答模式

### 6.1 总原则

生成器不能再把所有问题都当成“结构完整的工程说明文”来写。

本次改造后，回答模板必须服从最终证据状态，而不是仅服从问题类型。

最终模式分三种：

- `exact`
- `open`
- `exact_not_grounded`

### 6.2 `exact` 模式

`exact` 模式用于“用户问法精确，且已找到直接条文”。

建议模板固定为 4 段：

1. `直接结论`
2. `直接依据`
3. `适用边界`
4. `补充说明`

约束：

- 先给 1 到 3 句直接答案
- 必须标出最关键的 `[Ref-N]`
- 只列直接支撑结论的条文，不掺入泛相关章节
- 回答长度明显低于现有八段式模板

### 6.3 `open` 模式

`open` 模式继续支持解释型和综合型问答。

但不建议继续对所有开放型问题强制八段式。更合理的方式是：

- `mechanism` / `explanation`：可使用较完整结构
- `calculation`：保留步骤化说明
- `parameter`：可使用缩短结构

也就是说，“八段式”从默认模板变为可选模板。

### 6.4 `exact_not_grounded` 模式

`exact_not_grounded` 是本次新增的关键模式，用于：

- 用户期待精确答案
- 系统只找到了相关内容
- 但没有找到足够直接的证据

建议模板固定为 3 段：

1. `当前可确认`
2. `未直接定位到的部分`
3. `下一步检索建议`

约束：

- 不允许输出完整结论式摘要
- 不允许输出“工程含义 / 动作建议 / 国家附录待确认项”等扩写
- 不允许把相关条文包装成直接依据
- 回答长度必须短，且以“证据缺口说明”为中心

### 6.5 长度与结构约束

建议在 [server/core/generation.py](/Volumes/software/webdav/Euro_QA/server/core/generation.py) 中对不同模式显式施加长度控制：

- `exact`：短答
- `exact_not_grounded`：更短，只能确认与缺口说明
- `open`：允许长答

如果不做长度控制，即使模板拆分完成，模型仍可能在段内持续扩答。

---

## 7. 代码影响范围

### 7.1 `server/core/query_understanding.py`

新增：

- `answer_mode`
- `intent_label`
- `intent_confidence`
- `target_hint`
- `reason_short`

调整：

- 扩展 LLM prompt，使其同时输出现有 `question_type` 与新的路由字段
- 保留旧字段，避免破坏现有 API 兼容性

### 7.2 `server/core/retrieval.py`

新增：

- `exact probe` 检索逻辑
- groundedness 判断输入结构
- 标题 / 条款 / 短语命中加权

调整：

- 将 `section_path`、`clause_ids`、`source_title` 纳入 BM25 / phrase 策略
- 对 `exact` 问题减少泛相关聚合和无关补充

### 7.3 `server/core/generation.py`

新增：

- `exact` 模板
- `exact_not_grounded` 模板
- groundedness-aware prompt selection

调整：

- 让现有八段式模板只服务 `open` 或指定类型的问题

### 7.4 测试与评测

涉及：

- [tests/server/test_query_understanding.py](/Volumes/software/webdav/Euro_QA/tests/server/test_query_understanding.py)
- [tests/server/test_retrieval.py](/Volumes/software/webdav/Euro_QA/tests/server/test_retrieval.py)
- [tests/server/test_generation.py](/Volumes/software/webdav/Euro_QA/tests/server/test_generation.py)
- [tests/eval/eval_retrieval.py](/Volumes/software/webdav/Euro_QA/tests/eval/eval_retrieval.py)

---

## 8. 验证样例集

### 8.1 样例结构

建议新增一组“精确型规范问答样例”，每条样例至少包含：

- `question`
- `expected_mode`
- `expected_document`
- `expected_sections`
- `expected_anchor_phrases`
- `must_not_include`
- `notes`

示例：

```json
{
  "question": "欧标的截面计算的基本假设前提是什么",
  "expected_mode": "exact",
  "expected_document": "EN 1992-1-1:2004",
  "expected_sections": ["6.1"],
  "expected_anchor_phrases": [
    "plane sections remain plane",
    "the tensile strength of the concrete is ignored",
    "the following assumptions are made"
  ],
  "must_not_include": [
    "5.8.9",
    "双向弯曲简化公式"
  ]
}
```

### 8.2 样例类型

建议第一批覆盖：

1. 定义 / 假设类
2. 适用性类
3. 公式 / 限值类
4. 条文定位类
5. 少量 `open` 类问题作为保护样例

### 8.3 评测指标

建议新增 4 个核心指标：

- `anchor_hit_rate`
  - top-k 检索结果中是否出现预期锚点
- `section_hit_rate`
  - 是否命中目标 section / clause
- `grounded_mode_accuracy`
  - 最终模式是否符合预期
- `over_answer_rate`
  - 在 `exact_not_grounded` 样例中，是否出现不应有的扩写内容

其中 `over_answer_rate` 是本次最关键的新指标，因为当前主要问题是“错误扩答”，而不是纯召回不足。

---

## 9. 实施顺序

建议按以下顺序落地：

### Phase 1：样例集与评测指标

先补齐：

- 精确型问题样例
- groundedness 模式断言
- over-answer 检查项

目的：先定义“什么叫修好”，避免后续只能凭主观感受评估效果。

### Phase 2：LLM-first routing

在 query understanding 中增加：

- `answer_mode`
- `intent_label`
- `target_hint`

此阶段先不改生成模板，只完成分流与日志观测。

### Phase 3：Exact Probe + Groundedness Gate

在 retrieval 中实现：

- 精确字段优先检索
- 锚点识别
- groundedness 判定

此阶段的收益是：即使回答模板尚未修改，系统也能知道哪些问题“不该自信扩答”。

### Phase 4：生成模板拆分

在 generation 中新增：

- `exact`
- `exact_not_grounded`
- `open`

并把模板选择改为 groundedness-aware。

### Phase 5：排序细节与阈值调优

最后再调：

- 标题 / 条款 / 短语 boost
- groundedness 阈值
- exact / open 的边界样例

这一步应建立在前面结构已经稳定的前提下进行。

---

## 10. 验收标准

本次改造完成后，应满足以下标准：

1. 精确型问题的 top-k 检索结果中，更稳定地出现直接条文或直接锚点
2. 当 direct evidence 缺失时，系统能够保守降级，而不是输出看似完整但不精确的长答案
3. `exact_not_grounded` 样例中的错误扩答率显著下降
4. `open` 类型问题的解释能力不明显退化
5. 类似“基本假设 / 适用条件 / 公式 / 限值 / 条文定位”这类问题，不再频繁出现“相关内容冒充直接依据”的错误模式

---

## 11. 风险与权衡

### 11.1 主要收益

- 让系统从“相关性问答”更接近“证据约束问答”
- 对一整类高频工程问题形成稳定约束
- 将“没有直证时保守缩答”变成默认安全策略

### 11.2 主要风险

- 分流过保守，可能使部分本可回答的问题被降级
- 分流过激进，可能把开放式问题错误压成短答
- 精确型检索策略会增加后端逻辑分支与测试负担

### 11.3 风险控制

- 使用 LLM 主判 + 规则兜底 + 检索反证，避免单点误判
- 通过样例集单独监控 `open` 问题质量，防止解释能力退化
- 将 groundedness 与 over-answer 指标纳入回归评测，而不是仅看 section recall

---

## 12. 结论

本次改造的核心不是“修复某一个错误答案”，而是给系统补上一条缺失的能力边界：

- 先识别用户是否在问精确条文
- 再验证是否真的找到了直接证据
- 最后再决定回答到什么程度

只有把这一边界建立起来，系统才能稳定处理“定义 / 基本假设 / 适用条件 / 公式 / 限值 / 条文定位”这类工程高频问题，而不再持续陷入“相关内容很多，但直接答案不准”的模式。
