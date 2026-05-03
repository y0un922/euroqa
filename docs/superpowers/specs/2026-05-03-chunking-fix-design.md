# Chunking Fix Design

## Status

- **Status**: APPROVED for implementation
- **Branch**: `master`（直接在主干上推进；用户判断 chunking 修复风险可控）
- **Depends on**: 无
- **Blocks**: [Contextual Retrieval Design](/Users/youngz/webdav/Euro_QA/docs/superpowers/specs/2026-05-03-contextual-retrieval-design.md)（sub-project 2 必须等本子项目落地后再启动；sub-project 2 将基于本工作之后的 master 开 `feature/contextual-retrieval` 分支）
- **Author**: yangzhuo
- **Date**: 2026-05-03

## Goal

修复 `pipeline/structure.py` + `pipeline/chunk.py` 当前分块管线的两个核心结构性缺陷，让 parent-child 树形分块机制对真实 Eurocode 语料生效，同时把所有 child chunk 的 token 大小收敛到 ≤800 tokens，为下游 bge-m3 embedding 提供质量稳定的输入，并为后续 contextual retrieval 提供干净的实验地基。

## Context

### 现状

通过对 `data/debug_runs/20260411T112426Z_607d7c41/artifacts/` 的实测分析（见下文"实测数据"），当前 chunking 在三篇生产语料上存在以下问题：

1. **扁平树**：所有 1,047 个 text chunk（DG_EN1990 320 + EN1992-1-1_2004 365 + DG_EN1992 部分）的 `metadata.section_path` 深度全部为 1。`metadata.parent_chunk_id` 全部为 `None`。`pipeline/chunk.py::_build_parent_chunk` 一次也没被调用过。`server/core/retrieval.py` 的"父块补全"特性在真实数据上是 no-op。
2. **死代码**：`pipeline/chunk.py:30` 定义了 `_CHILD_MAX_TOKENS = 800`，但 `_build_child_text_chunk`（第 233-272 行）从未调用 `_truncate_by_tokens`。结果 23-28% 的 chunk 超 800 tokens，最坏 4,970 tokens（DG_EN1990 的 "General" 章节）。
3. **embedding 表达力被稀释**：bge-m3 (`dim=1024`) 推荐 ≤512 tokens 取得最佳质量，Anthropic 论文使用 200-400 tokens chunk。当前数据 28% chunks > 800 tokens 直接稀释向量表达力，是检索不准的主因。

### 实测数据（2026-04-11 run）

| 文档 | text chunks | section_path depth=1 | >800 tokens | >4000 tokens | max tokens |
|------|-------------|---------------------|-------------|--------------|------------|
| DG_EN1990 | 320 | 100% | 91 (28%) | 2 | 4,970 |
| EN1992-1-1_2004 | 365 | 100% | 83 (23%) | 0 | 2,965 |

### 根因

通过 `head -50` 观察 `data/parsed/<doc>/<doc>.md` 与 `grep -oE "^#+\s"` 头分布发现：

| 文档 | H1 数 | H2-H6 数 |
|------|-------|----------|
| DG_EN1990 | 365 | 0 |
| EN1992-1-1_2004 | 489 | 0 |
| DG_EN1992-1-1__-1-2 | 369 | 0 |

**MinerU 把所有 PDF heading 输出为 markdown H1**。`structure.py::_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$")`（第 104 行）按 markdown `#` 数确定 level，于是 1,223 个 H1 全部被当作顶层节点，扁平树由此而来。

层级信号没丢——保留在标题文本的数字前缀里：
```
# 1.1 Scope                      → 实际应为 H2
# 1.1.1 Scope of Eurocode 2      → 实际应为 H3
# 1.1.2 Scope of Part 1-1...     → 实际应为 H3
# Introduction                    → 真实 H1（无前缀）
```

### PDF Outline 调研结论

通过 `fitz.open(pdf).get_toc()` 实测三篇 PDF：

| 文档 | PDF outline | 质量 |
|------|-------------|------|
| DG_EN1990 | 229 条，L1-L4 | 干净，标题清晰 |
| EN1992-1-1_2004 | **0 条** | 完全无 outline |
| DG_EN1992-1-1__-1-2 | 203 条，L1-L5 | 质量差：L1 是书名 "Beeby-revised_press"，标题带页码尾巴 |

PDF outline 不能作为主层级源——3 篇文档中至少 1 篇没有 outline，1 篇质量太差需要清洗。**标题数字前缀是 3/3 文档共有的稳定信号**。

## Decisions

| ID | 决策 | 拒绝的替代方案 | 理由 |
|----|------|----------------|------|
| D1 | 直接在 `master` 上推进（**不开 feature 分支**）| 独立分支 `feature/chunking-fix` / 与 contextual retrieval 共用分支 | 用户判断 chunking 修复结构性收益高、风险可控，愿意接受 master 直接演进；contextual retrieval 是真正的测试性功能，单独 `feature/contextual-retrieval` 分支隔离 |
| D2 | 仅基于标题数字前缀推断 level（P2a） | TOC 信号 / MinerU 配置改造 | TOC 覆盖率不足 1.5/3；MinerU 内部模型不可控；前缀 100% 覆盖 |
| D3 | 超 800 token 叶 section 走递归切分（Q3-recursive） | 删常量承认无上限 / 硬截断 | 删常量保留质量问题；硬截断丢失内容；递归切分零信息丢失 |
| D4 | 递归边界优先级 `["\n\n", "\n", ". ", " ", ""]`，贪心目标 600 tokens，硬上限 800 tokens | 仅段落切（`\n\n`） | 段落切对单个长段落无效；递归 + 贪心合并兼顾大小均匀和语义边界 |
| D5 | split chunks 之间 **不做 overlap** | 50-100 token overlap | 已有 `parent_chunk_id` + 父块补全机制提供等价上下文；overlap 涨索引 10-15% 且 debugging 困惑 |
| D6 | 数字前缀正则仅支持 `\d+(\.\d+)+`，字母前缀（"A.2.3"）不支持 | 同时支持字母前缀 | grep 三篇 .md 未发现字母前缀 case；YAGNI |
| D7 | 仅修改 `structure.py` 与 `chunk.py`；不动 `parse.py` / `index.py` / `retrieval.py` | 在 Stage 1 后处理 markdown | 保持改动局部；MinerU 输出文件原样保留以便未来切换解析器 |

## Architecture

### 数据流

```
PDF
 ├─ Stage 1 (parse.py / MinerU): 出 markdown，全 H1            ← 不动
 ├─ Stage 2 (structure.py): 读 markdown 建树                    ← 改动 ①
 │      ├─ _HEADING_RE 解析每行 heading
 │      ├─ NEW: _infer_level(markdown_hashes, title_text)
 │      └─ 用推断 level 建多层 DocumentNode 树
 ├─ Stage 3 (chunk.py): 树 → chunks                            ← 改动 ②
 │      ├─ _walk_sections (递归遍历)
 │      ├─ 非叶 section → _build_parent_chunk (4K cap，已有逻辑)
 │      └─ 叶 section → _build_child_text_chunk
 │             ├─ ≤800 tokens → 1 个 child chunk (已有逻辑)
 │             └─ >800 tokens → NEW: _recursive_split → N 个 split chunks
 ├─ Stage 3.5 (summarize.py): LLM 摘要特殊 chunk                ← 不动
 └─ Stage 4 (index.py): Milvus + ES 索引                       ← 不动
```

### 改动 ①：层级推断（`pipeline/structure.py`）

**新增正则**（在第 104 行 `_HEADING_RE` 之后）：

```python
# 标题前缀的数字层级，例 "1", "1.1", "1.1.1", "1.1.1.1"
_NUMERIC_PREFIX_RE = re.compile(r"^(\d+(?:\.\d+)+)\b")
```

**新增辅助函数**：

```python
def _infer_level(markdown_hashes: str, title_text: str) -> int:
    """根据标题前缀的数字深度推断 heading level。

    无数字前缀的标题回退到 markdown ``#`` 的个数（保持 MinerU 显式信号）。

    Examples
    --------
    >>> _infer_level("#", "1.1 Scope")
    2
    >>> _infer_level("#", "1.1.1 Scope of Eurocode 2")
    3
    >>> _infer_level("#", "Introduction")
    1
    >>> _infer_level("##", "Introduction")
    2
    """
    match = _NUMERIC_PREFIX_RE.match(title_text.strip())
    if match:
        prefix = match.group(1)
        # "1" → 1 (含 0 个点 + 1)，"1.1" → 2 (1 个点 + 1)，"1.1.1" → 3
        return prefix.count(".") + 1
    return len(markdown_hashes)
```

**集成点**：在 `parse_markdown_to_tree` 中，原来按 `len(hashes)` 取 level 的位置（约第 175-185 行 `headings = list(_HEADING_RE.finditer(markdown))` 之后的 `(level, title, body)` 段落构造逻辑）替换为：

```python
# 原来：level = len(hashes)
# 改为：
level = _infer_level(hashes, title)
```

具体集成行号在实现时确认；改动 ≤5 行。

### 改动 ②：递归切分（`pipeline/chunk.py`）

**新增模块级常量**（第 30-31 行附近）：

```python
_RECURSIVE_TARGET_TOKENS = 600    # 贪心合并目标
_RECURSIVE_SEPARATORS: tuple[str, ...] = ("\n\n", "\n", ". ", " ", "")
# _CHILD_MAX_TOKENS = 800  保持不变；从此真正起约束作用
```

**新增辅助函数**：

```python
def _recursive_split(text: str) -> list[str]:
    """按优先级递减的边界切分超长文本，贪心合并到接近 ``_RECURSIVE_TARGET_TOKENS``。

    切分产物保证 ``_estimate_tokens(piece) <= _CHILD_MAX_TOKENS``。
    无可用边界时按 token 硬切并 ``logger.warning("recursive_hard_split")``。
    """
    if _estimate_tokens(text) <= _CHILD_MAX_TOKENS:
        return [text]

    for sep in _RECURSIVE_SEPARATORS:
        if sep == "":
            # 兜底：硬按 char/token 切
            logger.warning("recursive_hard_split", text_len=len(text))
            return _split_by_tokens_hard(text, _CHILD_MAX_TOKENS)
        if sep not in text:
            continue
        parts = text.split(sep)
        merged = _greedy_merge(parts, sep, _RECURSIVE_TARGET_TOKENS)
        result: list[str] = []
        for piece in merged:
            if _estimate_tokens(piece) <= _CHILD_MAX_TOKENS:
                result.append(piece)
            else:
                # 单 piece 仍超限 → 用更细粒度 sep 递归
                result.extend(_recursive_split(piece))
        return result
    return [text]


def _greedy_merge(parts: list[str], sep: str, target_tokens: int) -> list[str]:
    """从左到右合并 ``parts``，每个累加块尽量靠近但不超 ``target_tokens``。"""
    out: list[str] = []
    buf: list[str] = []
    buf_tokens = 0
    for p in parts:
        p_tokens = _estimate_tokens(p)
        if buf and buf_tokens + p_tokens > target_tokens:
            out.append(sep.join(buf))
            buf = [p]
            buf_tokens = p_tokens
        else:
            buf.append(p)
            buf_tokens += p_tokens
    if buf:
        out.append(sep.join(buf))
    return out


def _split_by_tokens_hard(text: str, max_tokens: int) -> list[str]:
    """无任何边界可用时按 char 硬切；保证每片 ≤ ``max_tokens``。"""
    max_chars = max_tokens * 2  # 沿用 _estimate_tokens 的 2 字符 = 1 token 假设
    return [text[i : i + max_chars] for i in range(0, len(text), max_chars)]
```

**集成点 ① - `_build_child_text_chunk` 改造**：

原来产出单个 chunk，改为可能产出多个 chunk。函数签名从 `→ Chunk | None` 改为 `→ list[Chunk]`：

```python
def _build_child_text_chunks(
    node: DocumentNode,
    section_path: list[str],
    node_identity: tuple[int, ...],
    source_title: str,
    special_children: list[DocumentNode],
) -> list[Chunk]:
    content = _insert_placeholders(node.content, special_children)
    if not content.strip():
        return []

    pieces = _recursive_split(content)

    chunks: list[Chunk] = []
    total_pieces = len(pieces)
    for split_idx, piece in enumerate(pieces):
        role = "child" if total_pieces == 1 else f"child:split:{split_idx}"
        extra = () if total_pieces == 1 else (str(split_idx), str(total_pieces))
        chunk_id = _make_chunk_id(
            source=node.source,
            node_identity=node_identity,
            role=role,
            content=piece,
            extra_parts=extra,
        )
        chunks.append(Chunk(
            chunk_id=chunk_id,
            content=piece,
            embedding_text=piece,
            metadata=ChunkMetadata(
                source=node.source,
                source_title=source_title,
                section_path=section_path,
                page_numbers=node.page_numbers,
                page_file_index=node.page_file_index,
                clause_ids=node.clause_ids,
                element_type=ChunkElementType.TEXT,
                cross_refs=node.cross_refs,
                ref_labels=list(node.cross_refs),
                ref_object_ids=_build_ref_object_ids(node.source, node.cross_refs),
                parent_chunk_id=None,  # 由 _walk_sections 在 parent 构建后回填
                bbox=list(node.bbox),
                bbox_page_idx=node.bbox_page_idx,
                **_build_clause_object_fields(node.source, node.title),
            ),
        ))
    return chunks
```

**集成点 ② - `_walk_sections` 调整**：

`representative_text_chunk`（用于父块构建时拼接子内容）的语义需要明确：当一个 leaf section 被切成 N 片时，"代表"是哪一片？

**决定**：取**第一片**作为 representative_text_chunk，理由：parent chunk 的 content 是子节点 content 的拼接，用第一片即"section 开头"足够代表该 section 的主题，不会让 parent content 过大。

```python
# 原: text_chunk = _build_child_text_chunk(...)
# 改:
text_chunks = _build_child_text_chunks(...)
if not text_chunks:
    return _ChunkBuildResult(chunks=[])
chunks = list(text_chunks)
representative = text_chunks[0]
# special_children 链回时：parent_text_chunk_id 指向 representative.chunk_id
```

**parent_chunk_id 回填**（约第 162-163 行）：

```python
# 原: 只有一个 child_chunk 时回填
# 改: 同一 section 切出来的所有 split 都回填同一个 parent_chunk_id
for child_chunk in child_text_chunks:  # 这里 child_text_chunks 是所有 representative
    # 同时回填该 representative 同源的所有 split chunks
    same_section_chunks = [c for c in chunks if c.metadata.section_path == child_chunk.metadata.section_path]
    for sc in same_section_chunks:
        if sc.metadata.element_type == ChunkElementType.TEXT and sc.metadata.parent_chunk_id is None:
            sc.metadata.parent_chunk_id = parent_chunk.chunk_id
```

实现时需仔细处理"同 section 多 split 共享 parent_chunk_id"的回填逻辑——避免给已经回填的 chunk 重复赋值，避免误伤其他 section 的 chunk（用 `node_identity` 而非 `section_path` 做隔离更稳）。

## Edge Cases

| Case | 处理 |
|------|------|
| 标题无数字前缀（"Introduction"、"Foreword"）| 回退到 markdown `#` 个数（MinerU 全 H1 → level=1）|
| 标题数字前缀含字母（"A.2.3 Annex"）| 当前不支持，回退到 markdown `#` 个数。如果实测发现影响，未来可扩展正则 |
| 单段落 > 800 tokens 且无 `. ` 边界（罕见） | 递归降级到 ` ` 边界继续切，再不行硬切并记 `logger.warning("recursive_hard_split")` |
| Leaf section content 为空或仅含空白 | 返回空 list，不产出任何 chunk（沿用现有行为）|
| Leaf section content ≤800 tokens | 返回 1 个 chunk，role=`"child"`（不带 `:split:N` 后缀，保持向后兼容）|
| Leaf section 切出 split chunks 但其中某片为空字符串 | `_greedy_merge` 已规避（buf 为空时不 append）；保险起见在最终 `pieces` filter `p.strip()` |
| chunk_id 稳定性 | `_make_chunk_id(extra_parts=(split_idx, total_splits))` 保证同源同切方式 → 同 ID。若 split 数量因为内容变化而变化（如 leaf 增减一段），相关 chunk_id 全部变化——正常行为 |
| 现有 `data/debug_runs/*` artifact 的兼容 | 不兼容；本子项目要求重建索引。Stage 3 之前的 artifact (`stage1.md`, `stage2_tree.json`) 仍可复用 |

## Testing Strategy

### 单元测试

**`tests/pipeline/test_structure_level_inference.py`**

参数化测试 `_infer_level`：

| markdown_hashes | title | expected_level |
|-----------------|-------|----------------|
| `#` | `1.1 Scope` | 2 |
| `#` | `1.1.1 Scope of Eurocode 2` | 3 |
| `#` | `1.1.1.1 Foo` | 4 |
| `#` | `Introduction` | 1 |
| `##` | `Introduction` | 2 |
| `###` | `1.1 Scope` | 2（前缀覆盖 markdown）|
| `#` | `A.2.3 Annex` | 1（字母前缀不支持，回退）|
| `#` | `1.` | 1（不完整前缀，回退）|
| `#` | `1` | 1（无小数点，回退）|
| `#` | `  1.1.1   Scope` | 3（前导空白容忍）|

**`tests/pipeline/test_chunk_recursive_split.py`**

参数化测试 `_recursive_split` + `_greedy_merge`：

- 短文本（≤800 tokens）→ 不切，返回 1 片
- 多段落超长（3 段，1500 tokens）→ 段落边界切，每片 ≤800
- 单段落超长（无 `\n\n`）→ 句子边界切
- 单句超长（无 `. `）→ 单词边界切
- 无空白超长 → 硬切，logger.warning 被触发（用 `caplog` 验证）
- split chunk_id 稳定性：同输入两次切，chunk_id 列表完全相同
- split chunk_id 隔离性：同 source 不同 section 切，chunk_id 互不冲突

**`tests/pipeline/test_chunking_integration.py`**

固化 fixture markdown（含嵌套数字前缀 + 长 leaf section + 表格 + 公式），跑完整 `create_chunks`，断言：

1. 至少存在一个 `metadata.parent_chunk_id is not None` 的 chunk（证明 parent-child 链生效）
2. 所有 text chunks 的 `_estimate_tokens(content) <= 800`（除 parent chunks ≤4000）
3. split chunks 共享同一 parent_chunk_id 且 section_path 一致
4. special chunks（table/formula/image）的 `parent_text_chunk_id` 指向有效的 text chunk
5. `validate_unique_chunk_ids(chunks)` 通过（无 ID 冲突）

### 不做

- 跑真 PDF 的 e2e 测试（用户自己重建索引验证；CI 跑大 PDF 太重）
- `_HEADING_RE` 本身的单元测试（已有逻辑，本子项目不动）
- 跑 Milvus / ES 的集成测试（Stage 4 不动）

### 覆盖率要求

按 `CLAUDE.md` 全局要求 ≥90%，由 `pytest --cov=pipeline.structure --cov=pipeline.chunk` 验证。

## Acceptance Criteria

实施完成后，重建索引（`python -m pipeline.run --start-stage 2`）后，**用户验证**以下指标（不做 CI 自动化）：

1. **层级**：`stage2_tree_pruned.json` 中至少 30% 的 section 节点 `level >= 2`（证明嵌套树生效）
2. **chunk 大小**：`stage3_chunks.json` 中所有 `metadata.element_type == "text"` 且 `metadata.parent_chunk_id != None` 的 chunk，`len(content) // 2 <= 800`
3. **parent chunks 存在**：`stage3_chunks.json` 中至少 10% 的 text chunks 有非空 `parent_chunk_id`
4. **覆盖率**：单元测试通过，`pipeline/structure.py` + `pipeline/chunk.py` 修改部分覆盖率 ≥90%
5. **回归**：现有测试套件（`tests/pipeline/`）全绿
6. **embedding/检索质量**：用户用既有问答测试集做主观对比（这是回退判据；如果检索质量未提升，本子项目可整体回滚分支）

## Rollback Plan

子项目失败的判据：用户重建索引后，主观/抽样测试发现检索质量**没有提升甚至下降**。

由于本子项目直接在 `master` 上推进（D1），回退路径**比 feature 分支策略多一步**：

1. 定位本子项目的所有相关 commit（建议实施时为每个 commit 打 tag 或在 message 中加标识符如 `[chunking-fix]`，便于日后 grep）
2. 反向选择：
   - 若本子项目期间 master 上**没有**其他 commit 叠加 → `git reset --hard <last-pre-chunking-commit>`，干净回退
   - 若有叠加 → `git revert <commit-list>` 逐个反转，可能产生冲突需手动解决
3. 重建索引到回退版本（用旧 chunking 代码）
4. 子项目 2（contextual retrieval）相应推迟，等待新方案

**实施期防御措施**（强烈建议）：
- 在动手前打 tag `pre-chunking-fix` 标记起点：`git tag pre-chunking-fix`
- 子项目期间提交粒度细一点（层级推断、递归切分、parent_chunk_id 回填分别独立 commit），方便选择性 revert
- 完成全部子任务前**不要** `git push --force` 或重写 master 历史

代码级回退成本：低-中（取决于实施期间是否有其他 commit 叠加）。  
索引重建成本：~1 次 Stage 2-4 全跑（用户自己估算时间）。

## Out of Scope

- Contextual retrieval（sub-project 2，单独 spec）
- 修改 `_estimate_tokens` 算法（沿用 `len // 2` 中英混合粗估）
- 修改 `_PARENT_MAX_TOKENS = 4000` 常量
- 修改 retrieval 端任何逻辑
- 修改 MinerU 配置或调用方式
- 改写 PDF outline 提取逻辑（实测覆盖率不足，YAGNI）
- 字母前缀（"A.2.3"）支持（YAGNI）
- 重叠（overlap）切分（YAGNI，依赖父块补全）

## Open Questions

无。所有讨论决策已固化为上述 Decisions 表格。
