# Workflow Refactor Plan: Pipeline 默认 + Agent 兜底

> 生成日期：2026-06-29
> 状态：待实施
> 目标：用显式 pipeline 替代 QA agent tool loop 作为默认路径，Agent 降为 escalation handler

---

## 一、核心设计原则

1. **Pipeline 默认，Agent 兜底**：90%+ 请求走显式 pipeline（expand → plan → retrieve → generate），Agent 只在 groundedness 不足或复杂多步调查时激活。
2. **一次 LLM 调用完成 Condense + Route**：合并上下文解析和意图路由为一次 structured output 调用，减少串行延迟。
3. **会话上下文分层管理**：Tier 1 Episodic Buffer（最近 N 轮 TurnState）+ Tier 2 Conversation Summary（长会话压缩）。
4. **防幻觉三道防线**：prompt 约束 → post-hoc 实体溯源校验 → fallback 降级。
5. **Generation 输入收紧**：resolved_question + retrieval evidence + 结构化 summary，不读取原始 history 文本。

---

## 二、会话上下文管理

### Tier 1: Episodic Buffer（工作记忆）

```python
class TurnState:
    user_question: str           # 用户原始问题
    resolved_question: str       # 上下文解析后的独立问题
    topic: str                   # 本轮主题（"混凝土梁受弯承载力"）
    referenced_objects: list[str]  # 本轮命中的表/公式/条款号
                                   # 来源：检索结果的 chunk.metadata.object_label
    source_docs: list[str]       # 本轮命中的 EN 标准号
                                   # 来源：检索结果的 chunk.metadata.source
    groundedness: str            # 本轮检索的 groundedness
    confidence: str              # 本轮回答的 confidence
```

- 存储最近 N=5-8 轮（可配置）
- 生命周期：会话结束销毁
- **关键**：referenced_objects 和 source_docs 必须来自检索结果 metadata，不是 LLM answer text

### Tier 2: Conversation Summary（长会话压缩）

```python
class ConversationSummary:
    topics_covered: list[str]      # 已讨论过的主题列表
    key_objects: list[str]         # 历史中出现过的关键表/公式（不压缩）
    key_sources: list[str]         # 历史中涉及的 EN 标准（不压缩）
    turn_count: int                # 总轮数
    summary_text: str              # 200-400 tokens 的叙事摘要
```

- 触发条件：轮数 > N，或 token 总量接近 budget 的 80%
- 压缩策略：observation masking（旧检索结果丢弃，只保留结论）
- key_objects 和 key_sources 永不压缩（支持远距离指代解析）

### 对话状态更新规则

每次请求结束时，从 **检索结果**（不是 answer text）构建 TurnState：
- `referenced_objects` ← 检索命中的 `chunk.metadata.object_label`（如 "Table 6.1"）
- `source_docs` ← 检索命中的 `chunk.metadata.source`（如 "EN 1992-1-1"）
- `topic` ← 可从 resolved_question 或 question_type 推导

---

## 三、Condense + Route（合并 LLM 调用）

### 输入

```
- current_question: str          # 用户当前问题
- conversation_buffer: list[TurnState]  # 最近 5-8 轮结构化状态
- conversation_summary: ConversationSummary | None  # 长会话时有
```

### 输出（structured output）

```python
class CondenserOutput:
    intent: Literal[
        "greeting",           # 寒暄/非规范问题
        "new_query",          # 全新规范查询
        "follow_up",          # 依赖上一轮的追问（需要检索）
        "reuse_context",      # 可基于上一轮证据直接回答
        "summarize",          # 总结历史
        "clarify",            # 指代不清，需要反问
    ]
    resolved_question: str | None    # 只在需要检索时输出
    clarification_prompt: str | None # 只在 intent=clarify 时输出
    resolution_trace: ResolutionTrace | None
```

```python
class ResolutionTrace:
    added_from_history: list[HistoryReference]
    original_kept_ratio: float

class HistoryReference:
    term: str           # "EN 1992-1-1"
    source_turn: int    # 来自第几轮
    source_field: str   # referenced_objects / source_docs / topic
```

### Prompt 防幻觉约束

写入 system prompt 的硬约束：
1. resolved_question 只允许使用：用户当前问题原文 + buffer 中 referenced_objects/source_docs/user_question/topic 字段的值
2. 绝对不允许补充用户和历史中都没有出现的 EN 标准号、章节号、表号、公式号
3. 如果无法确定指代对象，必须输出 intent="clarify"
4. resolution_trace 必须为每个添加的术语标注来源

### Post-hoc 校验（确定性代码）

```python
def validate_resolution(output, buffer, current_q) -> bool:
    """检查 resolved_question 中的 EN/表号/条款号是否可溯源"""
    entities_in_resolved = extract_en_references(output.resolved_question)  # regex
    entities_in_current = extract_en_references(current_q)
    entities_in_history = set()
    for turn in buffer:
        entities_in_history.update(turn.referenced_objects)
        entities_in_history.update(turn.source_docs)

    for entity in entities_in_resolved:
        if entity not in entities_in_current and entity not in entities_in_history:
            return False  # 幻觉
    return True
```

### 校验失败的 Fallback 策略

按失败模式分流，不一刀切：
- **指代真的解析不了**（buffer 为空 + 有指代词，或指代对象有歧义）→ clarify
- **Condenser 过度解析被 validation 拦截**（用户意图清楚但 condenser 补了幻觉实体）→ strip 幻觉部分，用清洁原文检索
- **reuse_context 边界不确定** → 放弃复用，做新检索（不 clarify）

---

## 四、完整 Workflow 流程

```
用户问题 + conversation_state
        │
        ▼
┌─────────────────────────────────────┐
│ Condense + Route (LLM, ~300ms)      │
│ 输入: question + buffer + summary   │
│ 输出: intent + resolved_question    │
└───────┬─────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────┐
│ Post-hoc Validation (代码, <5ms)    │
│ 检查实体溯源、编辑距离              │
│ 失败 → fallback（见上文策略）       │
└───────┬─────────────────────────────┘
        │
        ├── intent=greeting ──────────────→ 模板/轻量 LLM 回复（不检索）
        ├── intent=clarify ───────────────→ 返回 clarification_prompt
        ├── intent=summarize ─────────────→ 从 buffer 生成总结（不检索）
        ├── intent=reuse_context ─────────→ 用上一轮 evidence 重新 generate
        │                                    前提: 上一轮 groundedness=grounded
        │
        ├── intent=new_query ─────┐
        ├── intent=follow_up ─────┤
        │                         ▼
        │              ┌──────────────────────────────┐
        │              │ Query Expansion (LLM, ~300ms) │
        │              │ 纯英文三路扩展，不做 rewrite  │
        │              └──────────┬───────────────────┘
        │                         │
        │                         ▼
        │              ┌──────────────────────────────┐
        │              │ Evidence Planning             │
        │              │ 简单问题: heuristic plan      │
        │              │ 复合问题: LLM slot planning   │
        │              └──────────┬───────────────────┘
        │                         │
        │                         ▼
        │              ┌──────────────────────────────┐
        │              │ Hybrid Retrieval              │
        │              │ parallel slot search          │
        │              └──────────┬───────────────────┘
        │                         │
        │                         ▼
        │              ┌──────────────────────────────┐
        │              │ Groundedness Check            │
        │              │ grounded → 继续               │
        │              │ not_grounded → Agent Escalation│
        │              └──────────┬───────────────────┘
        │                         │
        │            ┌────────────┴────────────┐
        │            │                         │
        │      grounded/partial          not_grounded
        │            │                         │
        │            ▼                         ▼
        │     ┌──────────────┐        ┌──────────────┐
        │     │ Generate      │        │ Agent Loop   │
        │     │ answer_stream │        │ (escalation) │
        │     └──────────────┘        └──────────────┘
        │
        ▼
┌─────────────────────────────────────┐
│ Update TurnState                     │
│ 从检索结果（不是 answer）提取:       │
│ - referenced_objects                 │
│ - source_docs                        │
│ - topic                              │
│ 压缩 buffer 如果超限                 │
└─────────────────────────────────────┘
```

---

## 五、Agent 的新位置

Agent 从"默认路径"降为"Escalation Handler"：

### 激活条件（二选一）
1. **Groundedness 不足**：检索后 groundedness = "not_grounded"
2. **未来扩展**：Condense+Route 判定 complex_investigation（多步调查）

### Escalation 模式下 Agent 可以
- 调用 lookup_object、open_chunk 做精确查找
- 改变 search strategy（换 source_hints、调整 query）
- 多轮工具调用直到 groundedness 达标或 max_turns=3-5

### 不再负责
- Context resolution（由 Condense+Route 处理）
- Intent routing（由 Condense+Route 处理）
- 生成最终回答（由 generate_answer_stream 处理）

### 预期指标
- Agent activation rate < 15%
- 90%+ 请求走显式 pipeline

---

## 六、Generation 输入规范

Generation prompt 只接收：
1. `resolved_question` — 来自 Condense+Route
2. `retrieval evidence` — 当前轮检索到的 chunks（含 parent/ref/guide）
3. `conversation_summary.summary_text` — 200-400 tokens 叙事摘要

**不再传入**：原始 conversation history 文本、历史轮的 expanded_queries、历史轮的 retrieval metadata

---

## 七、可观测性（每次请求必须记录）

| Metric | 说明 |
|--------|------|
| `condense_route_ms` | Condense+Route 耗时 |
| `intent` | 分类结果 |
| `resolution_trace` | 上下文解析做了什么改动 |
| `validation_passed` | Post-hoc 校验是否通过 |
| `agent_bypassed` | 是否跳过了 agent |
| `query_expansion_ms` | 扩展耗时 |
| `evidence_planning_ms` | 规划耗时 |
| `retrieval_ms` | 检索耗时（per slot） |
| `generation_first_token_ms` | 从请求开始到第一个 answer token |
| `groundedness` | 最终 groundedness |
| `total_llm_calls` | 本次请求总共 LLM 调用次数 |

---

## 八、分阶段实施

### Phase 0: 可观测性先行（3 天）

不改业务逻辑，只加 structured logging：
- 每次请求记录：original_question, conversation_turn_count, 上一轮 referenced_objects, 最终 groundedness
- 人工标注 50 条真实请求的 intent（用于后续验证 LLM routing 准确率）

### Phase 1: TurnState + Condense+Route（1 周）

- 实现 `TurnState` 和 `ConversationSummary` 数据结构
- 每次请求结束时从检索结果构建 TurnState
- 实现 Condense+Route LLM 调用（structured output）
- 实现 post-hoc validation
- **Shadow mode**：Condense+Route 只 log 不控制分流，用标注数据验证准确率

### Phase 2: Pipeline 接管主路径（1-2 周）

- Condense+Route 正式控制分流
- greeting / summarize / clarify 走快速路径
- new_query / follow_up 走 expand → plan → retrieve → generate
- Agent 降为 escalation（groundedness 不足时激活）
- 保留老路径作为 feature flag fallback

### Phase 3: 优化和压缩（2 周）

- 实现 ConversationSummary 压缩（buffer 超限时触发）
- 评估合并 Query Expansion + Evidence Planning 为一次 LLM
- 评估 Condense+Route 是否需要换小模型
- 建立端到端 eval harness（覆盖 context resolution + routing）

---

## 九、Condense+Route 模型选择

| 方案 | 延迟 | 准确度 | 成本 |
|------|------|--------|------|
| 和 generation 用同一个大模型 | 300-500ms | 最高 | 高 |
| 小模型（Qwen2.5-7B / GLM-4-9B） | 100-200ms | 够用 | 低 |
| Fine-tuned LoRA（参考 IBM Granite） | 50-150ms | 最高 | 低 |

建议：先用现有 LLM 验证流程，延迟不可接受时再考虑小模型/LoRA。

---

## 十、注意事项

1. **reuse_context 初期保守实现**：只在用户明确问上一轮答案中提到的内容时才走复用，否则宁可重新检索
2. **Condense+Route prompt 需要迭代**：准备 few-shot examples 覆盖中文省略、混合中英文指代、跨轮指代
3. **Generation 和 Condense+Route 看到的 history 必须一致**：都只看 TurnState + summary，不看原始文本
4. **模型升级时注意 intent 分布漂移**：Phase 0 的标注数据固化为 regression test
5. **summary_text 质量是承重墙**：200-400 tokens 叙事线索，不只是结构化字段
