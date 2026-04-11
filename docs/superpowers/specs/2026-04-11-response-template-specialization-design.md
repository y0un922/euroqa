# Eurocode QA 回答模板分型重构 — 设计文档

> Version: 1.1
> Date: 2026-04-11
> Status: Draft
> Supersedes: 2026-04-10-answer-depth-reconstruction-design.md（本设计覆盖并替代前一版的 open 模式回答结构）

## 1. 问题陈述

当前系统的 open 模式使用统一的 7 段回答结构应对所有类型的工程问题（rule / parameter / calculation / mechanism），导致：

1. **回答太泛**：工程师读完不知道具体该怎么做，缺乏可操作的工程指导
2. **结构冗余**：7 段结构对大多数问题来说太多，关键结论被淹没在"教学式"长文中
3. **不够具体**：LLM 倾向输出"请查阅表 X"、"建议参考相关标准"等空话，而不是直接给出数值和步骤

**核心矛盾**：用一个模板应对所有问题类型，而不同类型的工程问题需要截然不同的回答策略。查表取值的问题需要直接给数、给查表路径；计算问题需要逐步推导；规则解读需要中文解释 + 工程动作；机理问题需要原理 + 影响。

**本系统服务于落地工程项目，回答错误对施工来说是毁灭级灾难。因此本次重构的底线是：极度保守，检索到什么说什么，每个数值/结论必须有 [Ref-N] 背书，宁可回答不完整也不能回答错误。**

## 2. 目标与非目标

### 2.1 本次目标

1. 将 open 模式的单一 7 段模板替换为 4 种按 `question_type` 分型的精简模板（各 3-4 段）
2. 强化 exact 模式的"反空话"约束和数值引用要求
3. 为所有模板新增通用"反空话"规则，从根本上消除泛泛而谈的回答
4. 保留现有三路生成模式（open / exact / exact_not_grounded）
5. 复用现有 question_type 路由（query_understanding.py 已分类为 rule/parameter/calculation/mechanism）
6. 更新生成层测试

### 2.2 非目标

- 不修改检索排序、rerank、Milvus 或 ES 基础设施（第二阶段）
- 不改变前端回答渲染结构或 Evidence Panel UI（第二阶段）
- 不新增新的回答模式
- 不修改 query_understanding.py 的 question_type 分类逻辑
- 不修改 API 契约（QueryResponse schema 不变）
- 不修改 build_prompt() 的证据包组装逻辑
- **非流式 JSON 路径**（`_SYSTEM_PROMPT` + `_build_json_system_prompt()`）暂不修改。当前非流式路径仅作为流式失败时的降级回退，实际使用频率极低。本次聚焦流式路径的模板重构；非流式路径将在后续版本同步更新以保持一致。两者行为暂时允许分歧。

## 3. 用户画像与设计原则

### 3.1 目标用户

- 在欧洲工作的中国工程师
- 熟悉中国规范体系，但不熟悉 Eurocode 体系
- 需要把回答直接用于设计、校核、审查或施工
- 使用场景包括工地现场快速查询和办公室详细核对

### 3.2 设计原则

1. **极度保守**：检索到什么说什么；每个数值/结论必须有 [Ref-N] 背书；未检索到的内容绝不写成规范结论
2. **一问一型**：不同类型的问题使用不同的回答模板，每种模板只包含该类型最需要的 3-4 段内容
3. **反空话**：禁止一切不含实际信息的"安全废话"；每段必须有实质内容（具体数值/条款号/操作步骤/判断条件）
4. **工程可操作**：回答的终极标准是"工程师读完知道具体该怎么做"
5. **混合深度**：简单查表直接给值，复杂问题给操作步骤

## 4. 模板分型架构

### 4.1 架构总览

```
用户提问
    │
    ▼
query_understanding.py
    │ 分类 question_type: rule / parameter / calculation / mechanism
    │ 路由 answer_mode: exact / open
    ▼
decide_generation_mode()
    │
    ├── exact + grounded ──────────► build_exact_system_prompt()        [4 段，强化版]
    ├── exact + not_grounded ──────► build_exact_not_grounded_prompt()  [4 段，不变]
    └── open ──────────────────────► build_open_system_prompt()
                                        │
                                        │ question_type 路由
                                        ├── parameter ──► 数值提取模板 [3 段]
                                        ├── rule ───────► 规定解读模板 [3 段]
                                        ├── calculation ► 计算步骤模板 [4 段]
                                        ├── mechanism ──► 机理说明模板 [3 段]
                                        └── None/unknown► 规定解读模板 [3 段] (fallback)
```

### 4.2 与现有系统的关系

| 组件 | 变化 |
|------|------|
| `question_type` 路由 | **不变** — query_understanding.py 已经输出 rule/parameter/calculation/mechanism |
| `decide_generation_mode()` | **不变** — 三路分流 open/exact/exact_not_grounded |
| `build_open_system_prompt()` | **重构** — 从单一 7 段模板改为按 question_type 分发到 4 种专属模板 |
| `build_exact_system_prompt()` | **强化** — 新增反空话规则和数值必引规则 |
| `build_exact_not_grounded_system_prompt()` | **不变** |
| `build_prompt()` | **不变** — 证据包组装逻辑不变 |
| `_build_sources_from_chunks()` | **不变** — 引用构建逻辑不变 |
| 前端渲染 | **不变** — Markdown 渲染不受影响（段落从 7 变 3-4，前端自适应） |

## 5. 四种 Open 模式模板

### 5.1 数值提取模板（parameter）

**适用场景**：查表取值、参数查询、限值确认、系数查询

**回答结构**（3 段）：

#### `### 直接结果`

**Guidance**：
- 第一行必须给出具体数值，格式为 "X = 值 单位 [Ref-N]"
- 如果有多个相关数值，用列表或表格呈现
- 禁止用"请查阅表 X"替代具体数值
- 如果查到的值受条件影响（如环境类别、材料等级），必须明确说明当前取值对应的条件

**示例 Guidance 文本**：
```
必须在第一行直接给出用户查询的数值，格式为"参数名 = 数值 单位 [Ref-N]"。
如果检索到了表格数据，直接提取具体数值，绝不能只说"请查阅表格"或"需参见表 X"。
如果该数值取决于特定条件（如环境类别、材料等级、结构类型），必须说明当前给出的值对应什么条件。
```

#### `### 怎么查到的`

**Guidance**：
- 给出完整的查表路径：哪个表 → 哪行哪列 → 什么条件决定取值
- 如果涉及多个参数之间的依赖关系，用表格说明
- 举出具体示例，如"查 Table 4.4N → 行：XC1 环境类别 → 列：结构类别 S4 → 得 cmin,dur = 15mm"

**示例 Guidance 文本**：
```
给出完整的查表路径：告诉用户从哪个表格出发，沿着哪个行和列条件定位到数值。
格式示例："查 Table X → 行条件：Y → 列条件：Z → 得到 结果"。
如有多个参数互相依赖，用 Markdown 表格列出参数之间的关系。
```

#### `### 使用限制`

**Guidance**：
- 只列出真正影响该数值是否成立的前提条件
- 必须指出是否需要查 National Annex 以获取本国最终值
- 必须指出该值适用于什么构件类型 / 工况 / 材料
- 禁止泛泛写"应结合项目实际情况"

**示例 Guidance 文本**：
```
列出影响这个数值成立的关键前提条件，包括：
- 适用的构件类型或材料
- 是否需要查 National Annex 确认最终值
- 哪些工况下此值可能不适用
不要写"建议结合实际情况"之类的空话，必须说明具体是什么情况。
```

---

### 5.2 规定解读模板（rule）

**适用场景**：某条规则是什么意思、某条规定怎么理解、一般性工程问答

**回答结构**（3 段）：

#### `### 规定内容`

**Guidance**：
- 先用 1-3 句中文概括这条规则的核心意思
- 引用原文关键表述并标注 [Ref-N]
- 必须解释中国工程师不熟悉的 Eurocode 术语
- 不要逐字翻译，要用中国工程师的思维方式解释

**示例 Guidance 文本**：
```
先用 1-3 句中文概括这条规则在说什么，它要控制什么工程问题。
然后引用原文中最关键的表述，标注 [Ref-N]。
对中国工程师不直观的术语（如 accidental design situation、serviceability limit state）必须给出中文工程含义。
```

#### `### 适用范围与限制`

**Guidance**：
- 明确列出适用于什么构件类型、工况、材料
- 明确指出什么情况下此规则不适用或结论可能变化
- 如果受 National Annex 影响，必须指出

**示例 Guidance 文本**：
```
明确列出：
- 适用对象：什么类型的构件、什么工况、什么材料
- 不适用情况：什么条件下此规则不成立
- 边界因素：是否受 National Annex、项目参数或构件分类影响
```

#### `### 工程上怎么做`

**Guidance**：
- 必须转化为具体工程动作，而不是复述条文
- 说明在设计、校核、审查或出图时具体怎么执行
- 可以使用 "Step 1 → Step 2 → ..." 格式

**示例 Guidance 文本**：
```
把这条规则转化成具体工程动作。例如：
- 设计阶段需要校核什么
- 施工审查时重点关注什么
- 出图标注时需要体现什么
不要只说"应按规范执行"，必须说明具体执行什么。
```

---

### 5.3 计算步骤模板（calculation）

**适用场景**：怎么算、验算流程、公式应用、数值代入

**回答结构**（4 段）：

#### `### 逐步计算`

**Guidance**：
- 按 Step 1 → Step 2 → ... 结构组织，逐步推导到最终结果
- 每步包含：步骤说明 → 公式（LaTeX + 编号）→ 参数取值来源 → 代入计算
- 必须给出数值算例（使用典型参数如 C30/37、B500 等）
- 严格区分四层取值：规范表达式 / 推荐值 / NA 最终值（标注「NA 待确认」）/ 项目计算值
- 最后一步给出最终计算结果，标注公式编号和 [Ref-N]

**示例 Guidance 文本**：
```
按 Step 1 → Step 2 → ... → 最终结果 的结构组织。每步必须包含：
1. 公式编号和 LaTeX 表达式
2. 参数含义、单位、取值来源
3. 代入具体数值的计算过程
选取典型参数（如 C30/37、B500、300×500mm 截面）完成数值算例。
严格区分：规范表达式、推荐值（recommended）、本国最终值（标注 NA 待确认）、项目计算值。
最后一步给出最终结果，格式为"参数名 = 数值 单位（公式 X.X [Ref-N]）"。
如果输入条件不完整，推导到数据支持的步骤为止，说明缺什么参数才能继续。
```

#### `### 输入条件`

**Guidance**：
- 用 Markdown 表格列出所有计算参数
- 表格列：符号 | 含义 | 单位 | 取值来源 | 当前取值/是否缺失

**示例 Guidance 文本**：
```
用 Markdown 表格列出所有参与计算的参数：
| 符号 | 含义 | 单位 | 取值来源 | 当前取值 |
对于缺失的参数，在"当前取值"列标注"缺失 — 需查 XX"。
```

#### `### 计算结果摘要`

**Guidance**：
- 用 1-3 行总结最终计算结果和关键中间值
- 如果计算不完整，说明当前推导到了哪一步、最终结论还差什么

**示例 Guidance 文本**：
```
用 1-3 行总结最终计算结果，格式为"参数名 = 数值 单位 [Ref-N]"。
如果计算未能完成，说明"当前推导到 Step X，结果为 Y；最终结论还需 Z 参数"。
```

#### `### 使用限制`

**Guidance**：
- 列出公式适用范围（构件类型、材料、荷载类型等）
- 列出 NA 待确认项
- 列出需要用户补充的输入参数

**示例 Guidance 文本**：
```
列出这个计算方法适用的范围和限制条件，包括：
- 公式适用于什么类型的构件和工况
- 哪些参数需要查 National Annex 确认
- 哪些输入需要用户根据项目条件补充
```

---

### 5.4 机理说明模板（mechanism）

**适用场景**：为什么这么规定、原理是什么、设计哲学

**回答结构**（3 段）：

#### `### 结论`

**Guidance**：
- 1-3 句话直接回答"为什么"
- 必须有 [Ref-N] 支撑
- 如果检索内容不直接说明原理，诚实说明"当前片段未直接解释原因，以下是基于条文内容的分析"

**示例 Guidance 文本**：
```
用 1-3 句话直接回答用户的"为什么"问题，标注 [Ref-N]。
如果检索到的条文没有直接解释原因，必须说明"当前片段未直接给出原因"，然后基于条文内容做有限分析。
```

#### `### 原理解释`

**Guidance**：
- 解释这条规则背后的工程原理或设计哲学
- 只能基于检索内容解释，不能凭 LLM 自身知识编造规范意图
- 可以引用 Designers' Guide 或规范注释中的解释

**示例 Guidance 文本**：
```
基于检索到的条文或注释解释这条规则的设计原理。
只能使用检索片段中的内容，不能凭自身知识编造规范意图。
如果检索到了 Designers' Guide 的解释性内容，可以引用。
```

#### `### 工程影响`

**Guidance**：
- 说明这个原理对设计、施工、审查的实际影响
- 指出违反时可能导致的后果（如果条文有提及）
- 转化为工程师可理解的影响描述

**示例 Guidance 文本**：
```
说明这条规则的原理对实际工程意味着什么：
- 对设计有什么影响
- 对施工有什么影响
- 违反时会有什么后果（仅当检索内容提及时）
```

## 6. Exact 模式强化

### 6.1 保留结构

4 段结构不变：
- `### 直接答案`
- `### 关键依据`
- `### 这条规定应如何理解和使用`
- `### 使用时要再核对的条件`

### 6.2 新增硬规则

在现有 6 条规则基础上新增：

**规则 7（反空话）**：
```
禁止输出不含实际信息的句子，包括但不限于：
- "请查阅表 X" — 如果检索到了表 X 的数据，必须直接提取数值
- "需参见规范" — 必须指出具体哪条规范的哪个条款
- "根据规范要求应..." — 必须说明是哪条规范的哪条具体要求
- "建议结合项目实际情况" — 必须说明哪些具体的项目参数会影响结论
```

**规则 8（数值必引）**：
```
回答中出现的每个具体数值（系数、限值、参数值、判断阈值）都必须标注 [Ref-N]。
没有 [Ref-N] 支撑的数值不允许出现在回答中。
```

### 6.3 Exact-Not-Grounded 模式

**不修改**。当前 4 段结构和约束规则已经成熟。

## 7. 跨模板通用规则

### 7.1 反空话规则（所有模板共享）

在 `_STREAM_BASE_RULES` 中新增一条规则：

```
禁止输出以下模式的空话：
- "根据规范要求，应..." → 必须指出哪条规范的哪条具体要求
- "建议参考相关标准" → 必须指出具体哪个标准的哪个条款
- "具体数值需查阅表 X" → 如果检索到了表 X，必须直接给出数值
- "在实际工程中应注意..." → 必须说明具体注意什么、为什么
- "需结合项目实际情况" → 必须说明哪些具体的项目参数会影响结论
- "应符合相关规定" → 必须说明是哪条规定

每个段落必须包含以下至少一种实质内容：
- 具体数值（带单位和 [Ref-N]）
- 具体条款号
- 具体操作步骤
- 具体判断条件
如果某段无法提供任何实质内容，则该段不输出。
```

### 7.2 极度保守规则（所有模板共享）

现有 base rule 1 已覆盖"不得编造"，但需强化：

```
在当前加强版中新增：
- 检索片段中没有直接提及的数值，不能在回答中出现
- 检索片段中没有直接支持的结论，不能写成"规范要求"
- 如果证据只能支持部分回答，必须明确说明"当前证据可确认 X，但 Y 仍需查阅 Z 条款"
- 宁可回答不完整，也不能回答不正确
```

### 7.3 工程上下文注入（所有 open 模板共享）

沿用现有逻辑：如果 query_understanding 提取了工程上下文（country, structure_type, limit_state 等），在 prompt 末尾注入已知/缺失上下文提示。4 种模板均支持此注入。

**重要变更**：现有代码中工程上下文注入引用了旧模板的段落名称"还需要补充确认的内容"（`generation.py:592-600`），此引用在新模板中不再存在。需按以下方式修改：

- 将缺失上下文提示改为不引用特定段落名称的通用表述：
  - 有缺失上下文时："以下工程背景未提供：{missing}。请先给出一般原则下的回答，并在最后一个段落末尾说明「若需确定性答案，还需提供：……」。"
  - 无工程上下文时："工程上下文未识别。请给出通用原则回答，并在最后一个段落末尾提示工程师需要补充哪些项目信息。"
- 使用"最后一个段落"代替具体段落名称，确保对所有 4 种模板通用

## 8. 实现方案

### 8.1 代码结构

**函数关系变更**：当前 `build_open_system_prompt()` 是 `build_stream_system_prompt()` 的薄包装。重构后：
- **删除** `build_stream_system_prompt()` — 它是旧 7 段模板的实现，不再需要
- **`build_open_system_prompt()`** 成为 open 模式的唯一入口，内含模板路由逻辑
- `_build_stream_mode_system_prompt()` 中调用 `build_open_system_prompt()` 不变
- 清理 `_STREAM_SYSTEM_PROMPT_LEGACY` — 旧备用 prompt 一并删除

```python
# generation.py 中的新结构

# 替换现有 ANSWER_SECTIONS, _SECTION_GUIDANCE, _TYPE_EMPHASIS
# 新增 4 个模板定义

PARAMETER_TEMPLATE = {
    "sections": [
        ("result", "直接结果"),
        ("lookup_path", "怎么查到的"),
        ("limitations", "使用限制"),
    ],
    "guidance": {
        "result": "...",      # 如 Section 5.1 所述
        "lookup_path": "...",
        "limitations": "...",
    },
}

RULE_TEMPLATE = {
    "sections": [
        ("rule_content", "规定内容"),
        ("scope", "适用范围与限制"),
        ("engineering_action", "工程上怎么做"),
    ],
    "guidance": { ... },
}

CALCULATION_TEMPLATE = {
    "sections": [
        ("steps", "逐步计算"),
        ("inputs", "输入条件"),
        ("result_summary", "计算结果摘要"),
        ("limitations", "使用限制"),
    ],
    "guidance": { ... },
}

MECHANISM_TEMPLATE = {
    "sections": [
        ("conclusion", "结论"),
        ("explanation", "原理解释"),
        ("impact", "工程影响"),
    ],
    "guidance": { ... },
}

# 模板路由
_OPEN_TEMPLATES = {
    "parameter": PARAMETER_TEMPLATE,
    "rule": RULE_TEMPLATE,
    "calculation": CALCULATION_TEMPLATE,
    "mechanism": MECHANISM_TEMPLATE,
}

def build_open_system_prompt(question_type, engineering_context):
    qt = _normalize_question_type(question_type) or "rule"  # fallback
    template = _OPEN_TEMPLATES[qt]
    # 组装：角色 + base rules + 反空话规则 + 模板段落 + 工程上下文
    ...
```

### 8.2 模板组装流程

每个 open 模板的 system prompt 结构：

```
1. 角色声明（不变）
2. 通用 base rules（强化版，含反空话规则和极度保守规则）
3. 问题类型声明
4. 该类型专属的段落结构 + guidance
5. 工程上下文注入（如有）
```

### 8.3 Exact 模式修改

仅在现有 `build_exact_system_prompt()` 的规则列表中追加规则 7（反空话）和规则 8（数值必引），不改变结构。

## 9. 修改范围

### 9.1 需要修改的文件

| 文件 | 修改内容 |
|------|---------|
| `server/core/generation.py` | 删除 `ANSWER_SECTIONS`、`_SECTION_GUIDANCE`、`_TYPE_EMPHASIS`、`_CALC_FORMULAS_GUIDANCE`、`_CALC_VARIABLES_GUIDANCE`、`_STREAM_SYSTEM_PROMPT_LEGACY`（旧备用 prompt）、`build_stream_system_prompt()`；新增 4 个模板定义和 `_OPEN_TEMPLATES` 路由；重写 `build_open_system_prompt()` 为模板路由入口；修改工程上下文注入中的段落名称引用为通用表述；在 `_STREAM_BASE_RULES` 中新增反空话规则和极度保守规则；在 `build_exact_system_prompt()` 中新增规则 7、8；清理 `八段式` 相关注释 |
| `tests/server/test_generation.py` | 为每种 question_type 增加模板选择和段落结构断言；验证反空话规则存在；验证 fallback 行为；验证工程上下文注入兼容 |

### 9.2 保持不变的文件

| 文件 | 原因 |
|------|------|
| `server/core/query_understanding.py` | question_type 分类逻辑不变 |
| `server/core/retrieval.py` | 检索逻辑不变（第二阶段优化） |
| `server/models/schemas.py` | API 契约不变 |
| `server/api/v1/query.py` | 请求处理不变 |
| `frontend/*` | 前端渲染不变（第二阶段调整） |

## 10. 测试策略

### 10.1 模板路由测试

```python
# 验证每种 question_type 选择正确的模板
def test_parameter_template_selected():
    prompt = build_open_system_prompt(question_type="parameter")
    assert "### 直接结果" in prompt
    assert "### 怎么查到的" in prompt
    assert "### 使用限制" in prompt

def test_rule_template_selected():
    prompt = build_open_system_prompt(question_type="rule")
    assert "### 规定内容" in prompt
    assert "### 适用范围与限制" in prompt
    assert "### 工程上怎么做" in prompt

# ... calculation, mechanism 类似
```

### 10.1b 旧模板移除验证

```python
# 验证旧 7 段标题不出现在新模板中
OLD_SECTION_HEADERS = [
    "### 先说结论",
    "### 这条规则在说什么",
    "### 适用条件与边界",
    "### 工程上怎么用",
    "### 容易出错的点",
    "### 当前依据",
    "### 还需要补充确认的内容",
]

def test_old_sections_removed_from_all_templates():
    for qt in ["parameter", "rule", "calculation", "mechanism"]:
        prompt = build_open_system_prompt(question_type=qt)
        for old_header in OLD_SECTION_HEADERS:
            assert old_header not in prompt, f"Old header '{old_header}' still present in {qt} template"
```

### 10.2 反空话规则测试

```python
def test_anti_vagueness_rules_present():
    for qt in ["parameter", "rule", "calculation", "mechanism"]:
        prompt = build_open_system_prompt(question_type=qt)
        assert "禁止输出" in prompt or "不能只说" in prompt
        assert "请查阅表" in prompt  # 黑名单中的示例

def test_exact_mode_anti_vagueness():
    prompt = build_exact_system_prompt()
    assert "禁止输出不含实际信息" in prompt
```

### 10.3 Fallback 测试

```python
def test_unknown_question_type_fallback():
    prompt = build_open_system_prompt(question_type=None)
    # 应 fallback 到 rule 模板
    assert "### 规定内容" in prompt

def test_invalid_question_type_fallback():
    prompt = build_open_system_prompt(question_type="unknown_type")
    assert "### 规定内容" in prompt
```

### 10.4 工程上下文兼容测试

```python
def test_engineering_context_injected_all_templates():
    ctx = EngineeringContext(country="Germany", structure_type="bridge")
    for qt in ["parameter", "rule", "calculation", "mechanism"]:
        prompt = build_open_system_prompt(question_type=qt, engineering_context=ctx)
        assert "Germany" in prompt
```

### 10.5 Exact 模式测试

```python
def test_exact_value_citation_rule():
    prompt = build_exact_system_prompt()
    assert "每个具体数值" in prompt and "[Ref-N]" in prompt

def test_exact_structure_unchanged():
    prompt = build_exact_system_prompt()
    assert "### 直接答案" in prompt
    assert "### 关键依据" in prompt
```

### 10.6 验收标准

#### 阻断项

- [ ] 4 种 open 模板已实现，每种 3-4 段
- [ ] 模板路由正确：question_type → 对应模板
- [ ] 反空话规则写入所有模板
- [ ] exact 模式新增规则 7、8
- [ ] fallback 到 rule 模板正常工作
- [ ] 所有 generation 测试通过
- [ ] 流式路径中 4 种模板路由与 open/exact/exact_not_grounded 模式选择一致

#### 警告项

- [ ] 回答篇幅没有不合理增长
- [ ] exact 模式没被扩写成长文
- [ ] 工程上下文注入在所有模板中正常工作

## 11. 风险与回退策略

### 11.1 主要风险

1. **LLM 不遵循模板**：某些 LLM 可能不严格遵循 3 段结构或输出多余段落
2. **question_type 分类不准**：如果 query_understanding 的分类错误，会导致使用错误模板
3. **反空话规则过严**：可能导致 LLM 在证据不足时干脆不输出内容
4. **计算模板过于复杂**：4 段结构对 LLM 的推理能力要求更高

### 11.2 控制策略

1. 用 `###` 标题锁定骨架；如果 LLM 输出多余段落，前端仍能正常渲染
2. fallback 到 rule 模板（覆盖面最广），降低分类错误的影响
3. 反空话规则中保留"如果某段无法提供实质内容则不输出"的弹性
4. 计算模板可以在第一阶段先用简化版，后续迭代增强

### 11.3 回退方式

- 每种模板可独立回退到旧版 7 段模板
- 回退粒度为 question_type 级别，不影响其他类型
- 极端情况下可将 `_OPEN_TEMPLATES` 路由全部指向 rule 模板作为统一 fallback

## 12. 未来阶段预留

### 第二阶段：检索优化

- 优化 retrieval.py 中的表格/公式检索精度
- 检索质量直接影响 parameter 和 calculation 模板的回答质量
- 如果关键表格未被检索到，再好的 prompt 也无法让 LLM 给出正确数值

### 第三阶段：前端适配

- 前端可能需要根据新的 3-4 段结构调整三层显示过滤
- 可能需要为不同 question_type 提供不同的 UI 展示优化
- Evidence Panel 可以根据 question_type 调整默认展示方式
