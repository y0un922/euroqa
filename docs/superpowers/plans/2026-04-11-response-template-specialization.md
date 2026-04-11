# Response Template Specialization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the single 7-section open mode template with 4 specialized templates (parameter/rule/calculation/mechanism), each with 3-4 sections, to produce actionable engineering answers instead of generic ones.

**Architecture:** The existing `build_stream_system_prompt()` function and its 7-section template infrastructure (`ANSWER_SECTIONS`, `_SECTION_GUIDANCE`, `_TYPE_EMPHASIS`, etc.) are replaced by 4 template dicts keyed by `question_type`, routed through a rewritten `build_open_system_prompt()`. The exact mode gets 2 additional anti-vagueness rules. All modes share new anti-vagueness base rules in `_STREAM_BASE_RULES`.

**Tech Stack:** Python 3.12, pytest, pydantic

**Spec:** `docs/superpowers/specs/2026-04-11-response-template-specialization-design.md`

---

## File Structure

Only two files are modified:

| File | Change |
|------|--------|
| `server/core/generation.py` | Replace template infrastructure, rewrite `build_open_system_prompt()`, strengthen `build_exact_system_prompt()`, add anti-vagueness base rules |
| `tests/server/test_generation.py` | Replace old template assertions, add per-question_type tests, add negative assertions, fix imports |

No new files are created.

---

### Task 1: Write failing tests for new template routing

**Files:**
- Modify: `tests/server/test_generation.py:49-99` (TestAnswerPrompts class)

- [ ] **Step 1: Replace old template assertions with new template routing tests**

Replace the existing tests that assert old 7-section headers with new tests for each question_type template. Also add negative assertions for old headers and a fallback test.

In `tests/server/test_generation.py`, replace the `TestAnswerPrompts` class with:

```python
class TestAnswerPrompts:
    def test_system_prompt_prefers_supported_answer_before_missing_info(self):
        assert "先给出基于当前片段可以直接确认的答案" in _SYSTEM_PROMPT
        assert "只有在当前片段连部分答案都无法支持时" in _SYSTEM_PROMPT

    # -- Open mode: parameter template --
    def test_parameter_template_sections(self):
        prompt = build_open_system_prompt(question_type="parameter")
        assert "### 直接结果" in prompt
        assert "### 怎么查到的" in prompt
        assert "### 使用限制" in prompt

    # -- Open mode: rule template --
    def test_rule_template_sections(self):
        prompt = build_open_system_prompt(question_type="rule")
        assert "### 规定内容" in prompt
        assert "### 适用范围与限制" in prompt
        assert "### 工程上怎么做" in prompt

    # -- Open mode: calculation template --
    def test_calculation_template_sections(self):
        prompt = build_open_system_prompt(question_type="calculation")
        assert "### 逐步计算" in prompt
        assert "### 输入条件" in prompt
        assert "### 计算结果摘要" in prompt
        assert "### 使用限制" in prompt

    # -- Open mode: mechanism template --
    def test_mechanism_template_sections(self):
        prompt = build_open_system_prompt(question_type="mechanism")
        assert "### 结论" in prompt
        assert "### 原理解释" in prompt
        assert "### 工程影响" in prompt

    # -- Fallback to rule template --
    def test_unknown_question_type_falls_back_to_rule(self):
        prompt = build_open_system_prompt(question_type=None)
        assert "### 规定内容" in prompt
        assert "### 适用范围与限制" in prompt
        assert "### 工程上怎么做" in prompt

    def test_invalid_question_type_falls_back_to_rule(self):
        prompt = build_open_system_prompt(question_type="nonsense_type")
        assert "### 规定内容" in prompt

    # -- Old 7-section headers must be gone --
    _OLD_SECTION_HEADERS = [
        "### 先说结论",
        "### 这条规则在说什么",
        "### 适用条件与边界",
        "### 工程上怎么用",
        "### 容易出错的点",
        "### 当前依据",
        "### 还需要补充确认的内容",
    ]

    @pytest.mark.parametrize("qt", ["parameter", "rule", "calculation", "mechanism", None])
    def test_old_section_headers_absent(self, qt):
        prompt = build_open_system_prompt(question_type=qt)
        for header in self._OLD_SECTION_HEADERS:
            assert header not in prompt, f"Old header '{header}' still in {qt} template"

    # -- Anti-vagueness rules --
    @pytest.mark.parametrize("qt", ["parameter", "rule", "calculation", "mechanism"])
    def test_anti_vagueness_rules_in_open_templates(self, qt):
        prompt = build_open_system_prompt(question_type=qt)
        assert "禁止输出" in prompt

    def test_anti_vagueness_rules_in_exact_template(self):
        prompt = build_exact_system_prompt()
        assert "禁止输出不含实际信息" in prompt

    def test_exact_value_citation_rule(self):
        prompt = build_exact_system_prompt()
        assert "每个具体数值" in prompt
        assert "[Ref-N]" in prompt

    # -- Existing exact/exact_not_grounded tests (kept) --
    def test_exact_system_prompt_structure(self):
        prompt = build_exact_system_prompt()
        assert "### 直接答案" in prompt
        assert "### 关键依据" in prompt
        assert "### 这条规定应如何理解和使用" in prompt
        assert "### 使用时要再核对的条件" in prompt
        assert "先直接回答" in prompt

    def test_exact_not_grounded_system_prompt_has_guardrails(self):
        prompt = build_exact_not_grounded_system_prompt()
        assert "### 当前能确认的内容" in prompt
        assert "### 为什么还不能直接下结论" in prompt
        assert "### 对工程决策的影响" in prompt
        assert "### 下一步应优先补查什么" in prompt
        assert "不能把相关材料包装成直接依据" in prompt

    # -- Engineering context injection --
    def test_engineering_context_injected_in_all_templates(self):
        from server.models.schemas import EngineeringContext
        ctx = EngineeringContext(country="Germany", structure_type="bridge")
        for qt in ["parameter", "rule", "calculation", "mechanism"]:
            prompt = build_open_system_prompt(question_type=qt, engineering_context=ctx)
            assert "Germany" in prompt, f"Context missing in {qt} template"

    def test_engineering_context_missing_fields_use_generic_wording(self):
        from server.models.schemas import EngineeringContext
        ctx = EngineeringContext(country="Germany")
        prompt = build_open_system_prompt(question_type="rule", engineering_context=ctx)
        # Must NOT reference old section name
        assert "还需要补充确认的内容" not in prompt

    def test_no_context_uses_generic_wording(self):
        prompt = build_open_system_prompt(question_type="rule")
        assert "还需要补充确认的内容" not in prompt

    # -- Mode routing (kept) --
    def test_decide_generation_mode_prefers_groundedness(self):
        assert decide_generation_mode("exact", "grounded") == "exact"
        assert decide_generation_mode("exact", "exact_not_grounded") == "exact_not_grounded"
        assert decide_generation_mode("open", "grounded") == "open"
        assert decide_generation_mode(None, "grounded") == "open"

    # -- Each template targets Chinese engineers --
    @pytest.mark.parametrize("qt", ["parameter", "rule", "calculation", "mechanism"])
    def test_all_templates_target_chinese_engineers(self, qt):
        prompt = build_open_system_prompt(question_type=qt)
        assert "中国工程师" in prompt
```

- [ ] **Step 2: Update imports at top of test file**

Replace the imports block (lines 9-29) so it no longer imports `build_stream_system_prompt` or `_STREAM_SYSTEM_PROMPT_LEGACY`:

```python
from server.core.generation import (
    _STREAM_BASE_RULES,
    _SYSTEM_PROMPT,
    _collect_exact_evidence_candidates,
    _build_exact_evidence_pack,
    build_exact_not_grounded_system_prompt,
    build_exact_system_prompt,
    build_open_system_prompt,
    _build_sources_from_chunks,
    _build_source_translation_prompt,
    _call_source_translation_llm,
    _fill_missing_source_translations,
    build_prompt,
    decide_generation_mode,
    generate_answer,
    generate_answer_stream,
    parse_llm_response,
)
```

- [ ] **Step 3: Remove the legacy prompt assertion test**

Delete the test `test_stream_prompt_prefers_partial_answer_over_blanket_rejection` (line 54-56 area) since it asserts on `_STREAM_SYSTEM_PROMPT_LEGACY` which will be deleted.

- [ ] **Step 4: Run tests to verify they fail**

Run: `uv run python -m pytest tests/server/test_generation.py::TestAnswerPrompts -v --tb=short`

Expected: Most new tests FAIL because `build_open_system_prompt()` still delegates to the old 7-section template. Old header tests should fail (they check absence but old headers are still present). Anti-vagueness tests should fail. The import of deleted symbols should fail at collection time.

- [ ] **Step 5: Commit failing tests**

```bash
git add tests/server/test_generation.py
git commit -m "test: add failing tests for template specialization routing"
```

---

### Task 2: Add anti-vagueness rules to `_STREAM_BASE_RULES`

**Files:**
- Modify: `server/core/generation.py:479-496`

- [ ] **Step 1: Append two new rules to `_STREAM_BASE_RULES` list**

After the existing 8 rules in `_STREAM_BASE_RULES` (line 496), add two new rules:

```python
    # 反空话规则
    "禁止输出以下模式的空话："
    "「根据规范要求，应…」→ 必须指出哪条规范的哪条具体要求；"
    "「建议参考相关标准」→ 必须指出具体哪个标准的哪个条款；"
    "「具体数值需查阅表 X」→ 如果检索到了表 X，必须直接给出数值；"
    "「在实际工程中应注意…」→ 必须说明具体注意什么、为什么；"
    "「需结合项目实际情况」→ 必须说明哪些具体的项目参数会影响结论；"
    "「应符合相关规定」→ 必须说明是哪条规定。"
    "每个段落必须包含至少一种实质内容：具体数值（带单位和 [Ref-N]）、具体条款号、具体操作步骤、或具体判断条件。"
    "如果某段无法提供任何实质内容，则该段不输出。",
    # 极度保守规则
    "检索片段中没有直接提及的数值，不能在回答中出现。"
    "检索片段中没有直接支持的结论，不能写成「规范要求」。"
    "如果证据只能支持部分回答，必须明确说明「当前证据可确认 X，但 Y 仍需查阅 Z 条款」。"
    "宁可回答不完整，也不能回答不正确。",
```

- [ ] **Step 2: Run a quick sanity check**

Run: `uv run python -c "from server.core.generation import _STREAM_BASE_RULES; print(len(_STREAM_BASE_RULES))"`

Expected: `10` (8 original + 2 new)

- [ ] **Step 3: Commit**

```bash
git add server/core/generation.py
git commit -m "feat: add anti-vagueness and extreme-conservative base rules"
```

---

### Task 3: Define 4 specialized open mode templates

**Files:**
- Modify: `server/core/generation.py:398-477` (replace old template infrastructure)

- [ ] **Step 1: Delete old template infrastructure**

Delete the following blocks (lines 398-477):
- Comment `# 八段式工程答案模板系统` and separator
- `ANSWER_SECTIONS` list
- `_TYPE_EMPHASIS` dict
- `_SECTION_GUIDANCE` dict
- `_CALC_FORMULAS_GUIDANCE` string
- `_CALC_VARIABLES_GUIDANCE` string

- [ ] **Step 2: Insert 4 template dicts and routing table**

In place of the deleted code, insert:

```python
# ---------------------------------------------------------------------------
# 问题类型专属模板系统（替代旧 7 段统一模板）
# ---------------------------------------------------------------------------

_PARAMETER_TEMPLATE: dict[str, Any] = {
    "sections": [
        ("result", "直接结果"),
        ("lookup_path", "怎么查到的"),
        ("limitations", "使用限制"),
    ],
    "guidance": {
        "result": (
            "必须在第一行直接给出用户查询的数值，格式为「参数名 = 数值 单位 [Ref-N]」。"
            "如果检索到了表格数据，直接提取具体数值，绝不能只说「请查阅表格」或「需参见表 X」。"
            "如果该数值取决于特定条件（如环境类别、材料等级、结构类型），必须说明当前给出的值对应什么条件。"
            "如有多个相关数值，用列表或 Markdown 表格呈现。"
        ),
        "lookup_path": (
            "给出完整的查表路径：告诉用户从哪个表格出发，沿着哪个行和列条件定位到数值。"
            "格式示例：「查 Table X → 行条件：Y → 列条件：Z → 得到 结果」。"
            "如有多个参数互相依赖，用 Markdown 表格列出参数之间的关系。"
        ),
        "limitations": (
            "列出影响这个数值成立的关键前提条件，包括：适用的构件类型或材料；"
            "是否需要查 National Annex 确认最终值；哪些工况下此值可能不适用。"
            "不要写「建议结合实际情况」之类的空话，必须说明具体是什么情况。"
        ),
    },
}

_RULE_TEMPLATE: dict[str, Any] = {
    "sections": [
        ("rule_content", "规定内容"),
        ("scope", "适用范围与限制"),
        ("engineering_action", "工程上怎么做"),
    ],
    "guidance": {
        "rule_content": (
            "先用 1-3 句中文概括这条规则在说什么，它要控制什么工程问题。"
            "然后引用原文中最关键的表述，标注 [Ref-N]。"
            "对中国工程师不直观的术语（如 accidental design situation、serviceability limit state）"
            "必须给出中文工程含义。"
        ),
        "scope": (
            "明确列出适用对象：什么类型的构件、什么工况、什么材料。"
            "明确指出不适用情况：什么条件下此规则不成立。"
            "指出边界因素：是否受 National Annex、项目参数或构件分类影响。"
        ),
        "engineering_action": (
            "把这条规则转化成具体工程动作。例如：设计阶段需要校核什么；"
            "施工审查时重点关注什么；出图标注时需要体现什么。"
            "不要只说「应按规范执行」，必须说明具体执行什么。"
        ),
    },
}

_CALCULATION_TEMPLATE: dict[str, Any] = {
    "sections": [
        ("steps", "逐步计算"),
        ("inputs", "输入条件"),
        ("result_summary", "计算结果摘要"),
        ("limitations", "使用限制"),
    ],
    "guidance": {
        "steps": (
            "按 Step 1 → Step 2 → … → 最终结果 的结构组织。每步必须包含：\n"
            "1. 公式编号和 LaTeX 表达式\n"
            "2. 参数含义、单位、取值来源\n"
            "3. 代入具体数值的计算过程\n"
            "选取典型参数（如 C30/37、B500、300×500mm 截面）完成数值算例。\n"
            "严格区分：规范表达式、推荐值（recommended）、本国最终值（标注 NA 待确认）、项目计算值。\n"
            "最后一步给出最终结果，格式为「参数名 = 数值 单位（公式 X.X [Ref-N]）」。\n"
            "如果输入条件不完整，推导到数据支持的步骤为止，说明缺什么参数才能继续。"
        ),
        "inputs": (
            "用 Markdown 表格列出所有参与计算的参数：\n"
            "| 符号 | 含义 | 单位 | 取值来源 | 当前取值 |\n"
            "对于缺失的参数，在「当前取值」列标注「缺失 — 需查 XX」。"
        ),
        "result_summary": (
            "用 1-3 行总结最终计算结果，格式为「参数名 = 数值 单位 [Ref-N]」。"
            "如果计算未能完成，说明「当前推导到 Step X，结果为 Y；最终结论还需 Z 参数」。"
        ),
        "limitations": (
            "列出这个计算方法适用的范围和限制条件，包括：公式适用于什么类型的构件和工况；"
            "哪些参数需要查 National Annex 确认；哪些输入需要用户根据项目条件补充。"
        ),
    },
}

_MECHANISM_TEMPLATE: dict[str, Any] = {
    "sections": [
        ("conclusion", "结论"),
        ("explanation", "原理解释"),
        ("impact", "工程影响"),
    ],
    "guidance": {
        "conclusion": (
            "用 1-3 句话直接回答用户的「为什么」问题，标注 [Ref-N]。"
            "如果检索到的条文没有直接解释原因，必须说明「当前片段未直接给出原因」，"
            "然后基于条文内容做有限分析。"
        ),
        "explanation": (
            "基于检索到的条文或注释解释这条规则的设计原理。"
            "只能使用检索片段中的内容，不能凭自身知识编造规范意图。"
            "如果检索到了 Designers' Guide 的解释性内容，可以引用。"
        ),
        "impact": (
            "说明这条规则的原理对实际工程意味着什么：对设计有什么影响；"
            "对施工有什么影响；违反时会有什么后果（仅当检索内容提及时）。"
        ),
    },
}

_OPEN_TEMPLATES: dict[str, dict[str, Any]] = {
    "parameter": _PARAMETER_TEMPLATE,
    "rule": _RULE_TEMPLATE,
    "calculation": _CALCULATION_TEMPLATE,
    "mechanism": _MECHANISM_TEMPLATE,
}
```

- [ ] **Step 3: Run import check**

Run: `uv run python -c "from server.core.generation import _OPEN_TEMPLATES; print(list(_OPEN_TEMPLATES.keys()))"`

Expected: `['parameter', 'rule', 'calculation', 'mechanism']`

- [ ] **Step 4: Commit**

```bash
git add server/core/generation.py
git commit -m "feat: define 4 specialized open mode templates"
```

---

### Task 4: Rewrite `build_open_system_prompt()` with template routing

**Files:**
- Modify: `server/core/generation.py:540-611` (replace `build_stream_system_prompt` + `build_open_system_prompt`)

- [ ] **Step 1: Delete `build_stream_system_prompt()` and rewrite `build_open_system_prompt()`**

Delete `build_stream_system_prompt()` (the function body at lines 540-603) entirely.

Then replace `build_open_system_prompt()` (lines 606-611) with:

```python
def build_open_system_prompt(
    question_type: str | QuestionType | None = None,
    engineering_context: EngineeringContext | dict[str, Any] | None = None,
) -> str:
    """根据问题类型路由到专属模板，构建流式系统提示词。"""
    qt = _normalize_question_type(question_type) or "rule"
    ctx = _normalize_engineering_context(engineering_context)
    template = _OPEN_TEMPLATES[qt]

    # Part A: 角色 + 基础规则（含反空话和极度保守规则）
    lines: list[str] = [
        "你是一位精通欧洲建筑规范（Eurocode）的专家，"
        "正在帮助不熟悉 Eurocode 的中国工程师理解规范要求，并把结论安全地用于真实工程项目。",
        "",
        "基础规则：",
    ]
    for i, rule in enumerate(_STREAM_BASE_RULES, 1):
        lines.append(f"{i}. {rule}")

    # Part B: 问题类型专属模板
    section_count = len(template["sections"])
    section_names = "、".join(name for _, name in template["sections"])
    lines.extend([
        "",
        f"问题类型：{qt}。",
        f"回答结构要求：严格使用以下 {section_count} 个三级标题（### ）并按顺序输出（{section_names}）。",
    ])
    for key, zh_name in template["sections"]:
        guidance = template["guidance"][key]
        lines.append(f"### {zh_name}")
        lines.append(f"   {guidance}")

    # Part C: 工程上下文与条件化答案
    lines.append("")
    if ctx:
        known = {
            k: v for k, v in ctx.model_dump().items()
            if v is not None and not (isinstance(v, str) and not v.strip())
        }
        missing = ctx.missing_fields
        if known:
            items = ", ".join(
                f"{k}={'是' if v is True else '否' if v is False else v}"
                for k, v in known.items()
            )
            lines.append(f"已识别工程上下文：{items}")
        if missing:
            lines.append(
                "以下工程背景未提供：" + "、".join(missing) + "。"
                "请先给出一般原则下的回答，然后在最后一个段落末尾列出"
                "「若需确定性答案，还需提供：……」。"
            )
    else:
        lines.append(
            "工程上下文未识别。请给出通用原则回答，"
            "并在最后一个段落末尾提示工程师需要补充哪些项目信息。"
        )

    lines.extend(["", "目标：输出适合前端直接渲染的高质量 Markdown 中文答案。"])
    return "\n".join(lines)
```

- [ ] **Step 2: Delete `_STREAM_SYSTEM_PROMPT_LEGACY`**

Delete the entire `_STREAM_SYSTEM_PROMPT_LEGACY` block (lines 354-396 area) and its comment.

- [ ] **Step 3: Run tests to see progress**

Run: `uv run python -m pytest tests/server/test_generation.py::TestAnswerPrompts -v --tb=short`

Expected: Template routing tests and fallback tests should now PASS. Old header absence tests should PASS. Anti-vagueness tests should PASS.

- [ ] **Step 4: Commit**

```bash
git add server/core/generation.py
git commit -m "feat: rewrite build_open_system_prompt with template routing"
```

---

### Task 5: Strengthen `build_exact_system_prompt()` with anti-vagueness rules

**Files:**
- Modify: `server/core/generation.py` (the `build_exact_system_prompt` function)

- [ ] **Step 1: Add rules 7 and 8 to `build_exact_system_prompt()`**

In the `build_exact_system_prompt()` function, after rule 6, add:

```
7. 禁止输出不含实际信息的句子，包括但不限于：「请查阅表 X」— 如果检索到了表 X 的数据，必须直接提取数值；「需参见规范」— 必须指出具体哪条规范的哪个条款；「根据规范要求应…」— 必须说明是哪条规范的哪条具体要求；「建议结合项目实际情况」— 必须说明哪些具体的项目参数会影响结论。
8. 回答中出现的每个具体数值（系数、限值、参数值、判断阈值）都必须标注 [Ref-N]。没有 [Ref-N] 支撑的数值不允许出现在回答中。
```

- [ ] **Step 2: Run exact mode tests**

Run: `uv run python -m pytest tests/server/test_generation.py::TestAnswerPrompts::test_anti_vagueness_rules_in_exact_template tests/server/test_generation.py::TestAnswerPrompts::test_exact_value_citation_rule tests/server/test_generation.py::TestAnswerPrompts::test_exact_system_prompt_structure -v`

Expected: All 3 PASS.

- [ ] **Step 3: Commit**

```bash
git add server/core/generation.py
git commit -m "feat: add anti-vagueness and value-citation rules to exact mode"
```

---

### Task 6: Run full test suite and fix any regressions

**Files:**
- Modify: `tests/server/test_generation.py` (if any integration test breaks)
- Modify: `server/core/generation.py` (if any runtime issue)

- [ ] **Step 1: Run full generation test suite**

Run: `uv run python -m pytest tests/server/test_generation.py -v --tb=long`

Expected: All tests pass. If any test references `build_stream_system_prompt` or `_STREAM_SYSTEM_PROMPT_LEGACY`, it will fail at import time — these were handled in Task 1 Step 2-3.

- [ ] **Step 2: Run the complete project test suite**

Run: `uv run python -m pytest tests/ -v --tb=short`

Expected: All tests pass. If any other test file imports deleted symbols, fix the import.

- [ ] **Step 3: Fix any failing tests**

If any test references the deleted `build_stream_system_prompt` symbol in unexpected places (e.g. other test files or integration tests), update those imports and assertions.

- [ ] **Step 4: Commit fixes if any**

```bash
git add -u
git commit -m "fix: resolve test regressions from template specialization"
```

---

### Task 7: Final validation and commit

**Files:**
- No new modifications expected

- [ ] **Step 1: Verify all 4 template prompts render correctly**

Run a quick smoke test to print each template's section headers:

```bash
uv run python -c "
from server.core.generation import build_open_system_prompt
for qt in ['parameter', 'rule', 'calculation', 'mechanism', None]:
    prompt = build_open_system_prompt(question_type=qt)
    headers = [line for line in prompt.splitlines() if line.startswith('### ')]
    print(f'{qt}: {headers}')
"
```

Expected output:
```
parameter: ['### 直接结果', '### 怎么查到的', '### 使用限制']
rule: ['### 规定内容', '### 适用范围与限制', '### 工程上怎么做']
calculation: ['### 逐步计算', '### 输入条件', '### 计算结果摘要', '### 使用限制']
mechanism: ['### 结论', '### 原理解释', '### 工程影响']
None: ['### 规定内容', '### 适用范围与限制', '### 工程上怎么做']
```

- [ ] **Step 2: Verify exact mode has 8 rules**

```bash
uv run python -c "
from server.core.generation import build_exact_system_prompt
prompt = build_exact_system_prompt()
rules = [line for line in prompt.splitlines() if line.strip().startswith(('1.', '2.', '3.', '4.', '5.', '6.', '7.', '8.'))]
for r in rules:
    print(r.strip()[:80])
"
```

Expected: 8 rules listed, including rule 7 (anti-vagueness) and rule 8 (value citation).

- [ ] **Step 3: Run full test suite one final time**

Run: `uv run python -m pytest tests/ -v --tb=short`

Expected: All tests pass with 0 failures.

- [ ] **Step 4: Check there are no stale references to deleted symbols**

```bash
uv run python -c "
import server.core.generation as g
# These should NOT exist
for name in ['ANSWER_SECTIONS', '_SECTION_GUIDANCE', '_TYPE_EMPHASIS',
             '_CALC_FORMULAS_GUIDANCE', '_CALC_VARIABLES_GUIDANCE',
             'build_stream_system_prompt', '_STREAM_SYSTEM_PROMPT_LEGACY']:
    assert not hasattr(g, name), f'{name} still exists!'
print('All stale symbols confirmed deleted.')
"
```

Expected: `All stale symbols confirmed deleted.`
