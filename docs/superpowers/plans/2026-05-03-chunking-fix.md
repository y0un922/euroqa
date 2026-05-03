# Chunking Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Per project CLAUDE.md:** every code edit and test execution should go through the `codex` skill. Steps below describe the change; the executor routes the actual `Edit`/`Bash` through Codex. Direct execution allowed only after Codex unavailability or two consecutive failures, logged as `CODEX_FALLBACK`.

**Goal:** Fix two structural defects in the Eurocode chunking pipeline so document hierarchy is preserved and no child chunk exceeds 800 tokens, providing a clean foundation for downstream contextual retrieval.

**Architecture:** Two surgical modifications: (1) `pipeline/structure.py` adds heading-level inference from numeric prefixes in title text, fixing MinerU's all-H1 output; (2) `pipeline/chunk.py` adds recursive splitting for oversized leaf sections, activating the previously dead `_CHILD_MAX_TOKENS = 800` constant. Indexing layer (Stage 4) and retrieval layer (`server/core`) are untouched.

**Tech Stack:** Python 3.12, pytest, structlog, existing pipeline (MinerU → Milvus + Elasticsearch BM25 + bge-m3 embeddings).

**Spec:** [docs/superpowers/specs/2026-05-03-chunking-fix-design.md](/Users/youngz/webdav/Euro_QA/docs/superpowers/specs/2026-05-03-chunking-fix-design.md)

**Branch:** `master` (no feature branch isolation — direct commits, granular for selective revert)

---

## File Structure

| File | Status | Responsibility |
|------|--------|----------------|
| `/Users/youngz/webdav/Euro_QA/pipeline/structure.py` | Modify | Add `_NUMERIC_PREFIX_RE` constant + `_infer_level()` function; integrate into `parse_markdown_to_tree` at existing line 188 to derive heading level from title text |
| `/Users/youngz/webdav/Euro_QA/pipeline/chunk.py` | Modify | Add `_RECURSIVE_TARGET_TOKENS`, `_RECURSIVE_SEPARATORS` constants; add `_recursive_split()`, `_greedy_merge()`, `_split_by_tokens_hard()` helpers; convert `_build_child_text_chunk` → `_build_child_text_chunks` (returns list); update `_walk_sections` for multi-chunk leaves and parent_chunk_id backfill |
| `/Users/youngz/webdav/Euro_QA/tests/pipeline/test_structure.py` | Modify | Append `TestInferLevel` class + `TestParseMarkdownLevels` class |
| `/Users/youngz/webdav/Euro_QA/tests/pipeline/test_chunk.py` | Modify | Append `TestRecursiveSplit`, `TestGreedyMerge`, `TestSplitByTokensHard`, `TestChildTextChunksSplit`, `TestWalkSectionsHierarchy` classes |

No new files. No dependency changes. No edits to `pipeline/parse.py`, `pipeline/index.py`, `pipeline/run.py`, `pipeline/summarize.py`, `pipeline/config.py`, or any `server/` code.

**Pre-flight tag** (before Task 1): `git tag pre-chunking-fix` to mark rollback anchor per spec D1 defense recommendation.

---

## Task 1: Pre-flight tag + read-only confirmation

**Files:**
- Read-only: `/Users/youngz/webdav/Euro_QA/pipeline/structure.py` lines 100-220
- Read-only: `/Users/youngz/webdav/Euro_QA/pipeline/chunk.py` (full file)
- Read-only: `/Users/youngz/webdav/Euro_QA/tests/pipeline/test_chunk.py` (head + tail)
- Read-only: `/Users/youngz/webdav/Euro_QA/tests/pipeline/test_structure.py` (head + tail)

- [ ] **Step 1: Tag the pre-fix master state for rollback anchor**

```bash
git tag pre-chunking-fix
git tag --list pre-chunking-fix
```

Expected: `pre-chunking-fix` printed.

- [ ] **Step 2: Verify pytest baseline is green before any changes**

```bash
cd /Users/youngz/webdav/Euro_QA && /Users/youngz/webdav/Euro_QA/.venv/bin/python -m pytest tests/pipeline/ -q 2>&1 | tail -20
```

Expected: 0 failures (record exit code; if any test already fails, STOP and surface to user — do not start with a red baseline).

- [ ] **Step 3: Confirm no pending diff in target files**

```bash
git status --short pipeline/structure.py pipeline/chunk.py tests/pipeline/test_chunk.py tests/pipeline/test_structure.py
```

Expected: empty output (no pending changes that this plan would clobber).

- [ ] **Step 4: No commit. Verification only.**

This task creates a tag and confirms a green baseline. Nothing to commit.

---

## Task 2: Add `_infer_level` function in `structure.py`

**Files:**
- Test: `/Users/youngz/webdav/Euro_QA/tests/pipeline/test_structure.py` (append new class)
- Modify: `/Users/youngz/webdav/Euro_QA/pipeline/structure.py` (add constant + function)

- [ ] **Step 1: Append the failing test class to `tests/pipeline/test_structure.py`**

Append at end of file (after the last existing test class):

```python


class TestInferLevel:
    """Heading level inference from numeric prefix in title text."""

    @pytest.mark.parametrize(
        "hashes, title, expected",
        [
            # Numeric prefix takes precedence
            ("#", "1.1 Scope", 2),
            ("#", "1.1.1 Scope of Eurocode 2", 3),
            ("#", "1.1.1.1 Detailed scope", 4),
            ("##", "1.1 Scope", 2),       # prefix overrides hashes
            ("###", "1.1 Scope", 2),
            # Whitespace tolerance before/within the prefix
            ("#", "  1.1.1   Scope", 3),
            # No prefix → fall back to markdown hashes
            ("#", "Introduction", 1),
            ("##", "Introduction", 2),
            ("###", "Foreword", 3),
            # Incomplete / non-matching prefixes → fall back
            ("#", "1. Scope", 1),         # trailing dot, no further digits
            ("#", "1 Scope", 1),          # no dot at all
            ("#", "A.2.3 Annex", 1),      # alphabetic prefix unsupported
            ("#", "(1)P A structure...", 1),
            ("#", "", 1),                 # empty title (defensive)
        ],
    )
    def test_infer_level(self, hashes, title, expected):
        from pipeline.structure import _infer_level
        assert _infer_level(hashes, title) == expected
```

- [ ] **Step 2: Run the new test class to verify it fails**

```bash
cd /Users/youngz/webdav/Euro_QA && /Users/youngz/webdav/Euro_QA/.venv/bin/python -m pytest tests/pipeline/test_structure.py::TestInferLevel -v 2>&1 | tail -25
```

Expected: ImportError or AttributeError on `_infer_level` (function not yet defined).

- [ ] **Step 3: Add `_NUMERIC_PREFIX_RE` regex and `_infer_level()` function in `pipeline/structure.py`**

In `pipeline/structure.py`, find the existing `_HEADING_RE` definition (around line 104):

```python
# Markdown 标题行：至少一个 # 后跟空格和标题文字
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)
```

Add immediately after it:

```python
# 标题前缀的数字层级，例 "1.1", "1.1.1", "1.1.1.1"。
# 至少需要一个点号；纯 "1" 不算（避免误把列表项编号当 heading 层级）。
_NUMERIC_PREFIX_RE = re.compile(r"^\s*(\d+(?:\.\d+)+)\b")


def _infer_level(markdown_hashes: str, title_text: str) -> int:
    """根据标题前缀的数字深度推断 heading level。

    无数字前缀的标题回退到 markdown ``#`` 的个数（保留 MinerU/作者的显式层级信号）。

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
    match = _NUMERIC_PREFIX_RE.match(title_text)
    if match:
        prefix = match.group(1)
        # "1.1" → 2 (1 个点 + 1)；"1.1.1" → 3；"1.1.1.1" → 4
        return prefix.count(".") + 1
    return len(markdown_hashes) if markdown_hashes else 1
```

- [ ] **Step 4: Run the test class to verify it passes**

```bash
cd /Users/youngz/webdav/Euro_QA && /Users/youngz/webdav/Euro_QA/.venv/bin/python -m pytest tests/pipeline/test_structure.py::TestInferLevel -v 2>&1 | tail -25
```

Expected: 14 tests pass (one per parametrized case).

- [ ] **Step 5: Commit**

```bash
git add pipeline/structure.py tests/pipeline/test_structure.py
git commit -m "feat(structure): add _infer_level for numeric prefix headings / 增加基于标题前缀的层级推断"
```

---

## Task 3: Integrate `_infer_level` into `parse_markdown_to_tree`

**Files:**
- Test: `/Users/youngz/webdav/Euro_QA/tests/pipeline/test_structure.py` (append new class)
- Modify: `/Users/youngz/webdav/Euro_QA/pipeline/structure.py` line 188

- [ ] **Step 1: Append the failing integration test**

Append to `tests/pipeline/test_structure.py`:

```python


class TestParseMarkdownLevels:
    """parse_markdown_to_tree must derive section nesting from numeric prefixes."""

    def test_flat_h1_with_numeric_prefixes_yields_nested_tree(self):
        from pipeline.structure import parse_markdown_to_tree, ElementType
        # MinerU output style: every heading is H1, hierarchy hidden in numeric prefixes
        md = (
            "# 1 General\n\nIntro paragraph.\n\n"
            "# 1.1 Scope\n\nScope paragraph.\n\n"
            "# 1.1.1 Scope of Eurocode 2\n\nDetail paragraph.\n\n"
            "# 1.2 Definitions\n\nDef paragraph.\n\n"
            "# Introduction\n\nNo-prefix top-level intro.\n"
        )
        tree = parse_markdown_to_tree(md, source="test")

        # Walk and collect (depth, title) pairs for SECTION nodes.
        def _walk(node, depth=0):
            for child in node.children:
                if child.element_type == ElementType.SECTION:
                    yield depth, child.title
                    yield from _walk(child, depth + 1)

        pairs = list(_walk(tree))
        titles_by_depth = {}
        for depth, title in pairs:
            titles_by_depth.setdefault(depth, []).append(title)

        # "1 General" is depth 0 (under root)
        assert any("1 General" in t for t in titles_by_depth.get(0, []))
        # "1.1 Scope" is one level deeper
        assert any("1.1 Scope" in t for t in titles_by_depth.get(1, []))
        # "1.1.1 Scope of Eurocode 2" is two levels deeper
        assert any("1.1.1" in t for t in titles_by_depth.get(2, []))
        # "Introduction" (no prefix) is at depth 0 alongside "1 General"
        assert any("Introduction" in t for t in titles_by_depth.get(0, []))

    def test_explicit_h2_h3_still_honored_when_no_prefix(self):
        from pipeline.structure import parse_markdown_to_tree, ElementType
        md = (
            "# Foreword\n\nPreface.\n\n"
            "## Background\n\nContext.\n\n"
            "### Reasons\n\nWhy.\n"
        )
        tree = parse_markdown_to_tree(md, source="test")

        def _walk(node, depth=0):
            for child in node.children:
                if child.element_type == ElementType.SECTION:
                    yield depth, child.title
                    yield from _walk(child, depth + 1)

        pairs = list(_walk(tree))
        depths = {title: depth for depth, title in pairs}
        assert depths["Foreword"] == 0
        assert depths["Background"] == 1
        assert depths["Reasons"] == 2
```

- [ ] **Step 2: Run the new tests to verify failure**

```bash
cd /Users/youngz/webdav/Euro_QA && /Users/youngz/webdav/Euro_QA/.venv/bin/python -m pytest tests/pipeline/test_structure.py::TestParseMarkdownLevels -v 2>&1 | tail -25
```

Expected: `test_flat_h1_with_numeric_prefixes_yields_nested_tree` fails — currently every heading lands at depth 0 because `level = len(match.group(1))` always returns 1.

- [ ] **Step 3: Replace the `level = ...` line in `parse_markdown_to_tree`**

In `pipeline/structure.py` at line 188, locate:

```python
        level = len(match.group(1))
```

Replace with:

```python
        level = _infer_level(match.group(1), match.group(2))
```

- [ ] **Step 4: Run integration tests + the full structure test file to catch regression**

```bash
cd /Users/youngz/webdav/Euro_QA && /Users/youngz/webdav/Euro_QA/.venv/bin/python -m pytest tests/pipeline/test_structure.py -v 2>&1 | tail -40
```

Expected: all tests in `test_structure.py` pass, including `TestInferLevel` (Task 2) and the new `TestParseMarkdownLevels`.

If any pre-existing test fails, the failure is informative: it likely tested explicit H1/H2/H3 markdown that now gets reshuffled by numeric-prefix inference. Inspect the failure carefully — if the test was wrong (assumed flat hierarchy when prefixes existed), update the assertion. Do not weaken `_infer_level` to compensate.

- [ ] **Step 5: Commit**

```bash
git add pipeline/structure.py tests/pipeline/test_structure.py
git commit -m "feat(structure): use prefix-based level inference in parse_markdown_to_tree / 把层级推断接入树解析"
```

---

## Task 4: Add `_split_by_tokens_hard` helper in `chunk.py`

**Files:**
- Test: `/Users/youngz/webdav/Euro_QA/tests/pipeline/test_chunk.py` (append)
- Modify: `/Users/youngz/webdav/Euro_QA/pipeline/chunk.py` (add helper)

- [ ] **Step 1: Append the failing test class**

Append to `tests/pipeline/test_chunk.py`:

```python


class TestSplitByTokensHard:
    """Last-resort hard splitter when no whitespace boundary is available."""

    def test_short_text_returned_as_single_piece(self):
        from pipeline.chunk import _split_by_tokens_hard
        text = "abc" * 10  # 30 chars ≈ 15 tokens
        pieces = _split_by_tokens_hard(text, max_tokens=100)
        assert pieces == [text]

    def test_long_text_split_into_multiple_pieces(self):
        from pipeline.chunk import _split_by_tokens_hard
        text = "x" * 5000  # 5000 chars ≈ 2500 tokens
        pieces = _split_by_tokens_hard(text, max_tokens=800)
        # max_chars = 800 * 2 = 1600 → 5000 / 1600 = 4 pieces (3 full + 1 tail)
        assert len(pieces) == 4
        assert all(len(p) <= 1600 for p in pieces)
        assert "".join(pieces) == text  # no content loss

    def test_exact_boundary(self):
        from pipeline.chunk import _split_by_tokens_hard
        text = "y" * 1600  # exactly max_chars
        pieces = _split_by_tokens_hard(text, max_tokens=800)
        assert pieces == [text]
```

- [ ] **Step 2: Run tests to verify failure**

```bash
cd /Users/youngz/webdav/Euro_QA && /Users/youngz/webdav/Euro_QA/.venv/bin/python -m pytest tests/pipeline/test_chunk.py::TestSplitByTokensHard -v 2>&1 | tail -15
```

Expected: ImportError on `_split_by_tokens_hard`.

- [ ] **Step 3: Add the helper in `pipeline/chunk.py`**

In `pipeline/chunk.py`, locate `_truncate_by_tokens` (line 447). Add the new helper directly below it:

```python
def _split_by_tokens_hard(text: str, max_tokens: int) -> list[str]:
    """无任何分隔符可用时按字符硬切；保证每片 ``_estimate_tokens(piece) <= max_tokens``。

    对应 ``_estimate_tokens`` 的 2 字符 = 1 token 假设：每片最多 ``max_tokens * 2`` 字符。
    """
    max_chars = max_tokens * 2
    if len(text) <= max_chars:
        return [text]
    return [text[i : i + max_chars] for i in range(0, len(text), max_chars)]
```

- [ ] **Step 4: Run tests to verify pass**

```bash
cd /Users/youngz/webdav/Euro_QA && /Users/youngz/webdav/Euro_QA/.venv/bin/python -m pytest tests/pipeline/test_chunk.py::TestSplitByTokensHard -v 2>&1 | tail -15
```

Expected: 3 tests pass.

- [ ] **Step 5: Commit**

```bash
git add pipeline/chunk.py tests/pipeline/test_chunk.py
git commit -m "feat(chunk): add _split_by_tokens_hard helper / 增加按 token 硬切兜底"
```

---

## Task 5: Add `_greedy_merge` helper in `chunk.py`

**Files:**
- Test: `/Users/youngz/webdav/Euro_QA/tests/pipeline/test_chunk.py` (append)
- Modify: `/Users/youngz/webdav/Euro_QA/pipeline/chunk.py` (add helper)

- [ ] **Step 1: Append the failing test class**

Append to `tests/pipeline/test_chunk.py`:

```python


class TestGreedyMerge:
    """Greedy merger packs parts up to (but not over) target_tokens, joining with sep."""

    def test_short_parts_merged_into_one(self):
        from pipeline.chunk import _greedy_merge
        # Each part ~50 chars = ~25 tokens; target 600 tokens.
        parts = ["a" * 50, "b" * 50, "c" * 50]
        out = _greedy_merge(parts, sep="\n\n", target_tokens=600)
        assert out == ["a" * 50 + "\n\n" + "b" * 50 + "\n\n" + "c" * 50]

    def test_each_part_in_own_chunk_when_target_small(self):
        from pipeline.chunk import _greedy_merge
        parts = ["a" * 200, "b" * 200, "c" * 200]   # each ~100 tokens
        out = _greedy_merge(parts, sep="\n", target_tokens=120)  # one part already exceeds
        assert len(out) == 3
        assert out[0] == "a" * 200
        assert out[1] == "b" * 200
        assert out[2] == "c" * 200

    def test_partial_merge_when_two_fit_one_extra_overflows(self):
        from pipeline.chunk import _greedy_merge
        parts = ["a" * 200, "b" * 200, "c" * 200, "d" * 200]  # ~100 tokens each
        out = _greedy_merge(parts, sep="\n", target_tokens=250)  # ~2 parts per chunk
        assert len(out) == 2
        assert out[0].count("a") + out[0].count("b") == 400
        assert out[1].count("c") + out[1].count("d") == 400

    def test_empty_parts_yields_empty_list(self):
        from pipeline.chunk import _greedy_merge
        assert _greedy_merge([], sep="\n\n", target_tokens=600) == []

    def test_separator_preserved_in_joined_output(self):
        from pipeline.chunk import _greedy_merge
        parts = ["alpha", "beta"]
        out = _greedy_merge(parts, sep=" || ", target_tokens=600)
        assert out == ["alpha || beta"]
```

- [ ] **Step 2: Run tests to verify failure**

```bash
cd /Users/youngz/webdav/Euro_QA && /Users/youngz/webdav/Euro_QA/.venv/bin/python -m pytest tests/pipeline/test_chunk.py::TestGreedyMerge -v 2>&1 | tail -15
```

Expected: ImportError on `_greedy_merge`.

- [ ] **Step 3: Add the helper in `pipeline/chunk.py`**

Add immediately after `_split_by_tokens_hard` (added in Task 4):

```python
def _greedy_merge(parts: list[str], sep: str, target_tokens: int) -> list[str]:
    """从左到右合并 ``parts``，每个累加块尽量靠近但不超 ``target_tokens``。

    单个 part 自身就超 ``target_tokens`` 时，让它独占一个 chunk（后续递归切再处理）。
    """
    out: list[str] = []
    buf: list[str] = []
    buf_tokens = 0
    for part in parts:
        part_tokens = _estimate_tokens(part)
        if buf and buf_tokens + part_tokens > target_tokens:
            out.append(sep.join(buf))
            buf = [part]
            buf_tokens = part_tokens
        else:
            buf.append(part)
            buf_tokens += part_tokens
    if buf:
        out.append(sep.join(buf))
    return out
```

- [ ] **Step 4: Run tests to verify pass**

```bash
cd /Users/youngz/webdav/Euro_QA && /Users/youngz/webdav/Euro_QA/.venv/bin/python -m pytest tests/pipeline/test_chunk.py::TestGreedyMerge -v 2>&1 | tail -15
```

Expected: 5 tests pass.

- [ ] **Step 5: Commit**

```bash
git add pipeline/chunk.py tests/pipeline/test_chunk.py
git commit -m "feat(chunk): add _greedy_merge helper / 增加贪心合并辅助函数"
```

---

## Task 6: Add `_recursive_split` function in `chunk.py`

**Files:**
- Test: `/Users/youngz/webdav/Euro_QA/tests/pipeline/test_chunk.py` (append)
- Modify: `/Users/youngz/webdav/Euro_QA/pipeline/chunk.py` (add constants + function)

- [ ] **Step 1: Append the failing test class**

Append to `tests/pipeline/test_chunk.py`:

```python


class TestRecursiveSplit:
    """Recursive splitter cascades through paragraph → line → sentence → word → hard-cut."""

    def test_short_text_not_split(self):
        from pipeline.chunk import _recursive_split
        text = "Short paragraph." * 5   # ~80 chars ≈ 40 tokens
        assert _recursive_split(text) == [text]

    def test_multi_paragraph_split_at_blank_line(self):
        from pipeline.chunk import _recursive_split
        para = "x" * 800   # ~400 tokens
        text = "\n\n".join([para, para, para, para])   # ~1600 tokens total
        pieces = _recursive_split(text)
        assert len(pieces) >= 2
        for p in pieces:
            assert len(p) // 2 <= 800   # each piece under hard cap

    def test_single_paragraph_falls_back_to_sentence(self):
        from pipeline.chunk import _recursive_split
        # One paragraph, multiple sentences, total ~2000 tokens
        sentence = "x" * 400 + "."
        text = (sentence + " ") * 10   # ~10 sentences, ~2000 tokens, no \n\n
        pieces = _recursive_split(text)
        assert len(pieces) >= 2
        for p in pieces:
            assert len(p) // 2 <= 800

    def test_no_separators_falls_back_to_hard_split(self):
        from pipeline.chunk import _recursive_split
        from structlog.testing import capture_logs
        text = "x" * 4000   # 2000 tokens, NO whitespace anywhere
        with capture_logs() as captured:
            pieces = _recursive_split(text)
        assert len(pieces) >= 2
        for p in pieces:
            assert len(p) <= 1600
        # Hard-split warning emitted (structlog has its own sink; pytest's `caplog`
        # only captures stdlib logging, so we use structlog.testing.capture_logs).
        assert any(entry.get("event") == "recursive_hard_split" for entry in captured), \
            f"Expected recursive_hard_split event; got {[e.get('event') for e in captured]}"

    def test_pieces_concatenation_preserves_content_modulo_separators(self):
        from pipeline.chunk import _recursive_split
        para = "a" * 1000
        text = f"{para}\n\n{para}\n\n{para}"
        pieces = _recursive_split(text)
        # Content preserved ignoring separator collapse
        rejoined = "".join(pieces).replace("\n\n", "")
        original = text.replace("\n\n", "")
        assert rejoined == original
```

- [ ] **Step 2: Run tests to verify failure**

```bash
cd /Users/youngz/webdav/Euro_QA && /Users/youngz/webdav/Euro_QA/.venv/bin/python -m pytest tests/pipeline/test_chunk.py::TestRecursiveSplit -v 2>&1 | tail -20
```

Expected: ImportError on `_recursive_split`.

- [ ] **Step 3: Add constants + function in `pipeline/chunk.py`**

In `pipeline/chunk.py` near line 30-31 (after `_PARENT_MAX_TOKENS`):

```python
_RECURSIVE_TARGET_TOKENS = 600    # greedy 合并目标，留 25% margin to _CHILD_MAX_TOKENS
_RECURSIVE_SEPARATORS: tuple[str, ...] = ("\n\n", "\n", ". ", " ", "")
```

Add `_recursive_split` immediately after `_greedy_merge` (added in Task 5):

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
                # Single piece still over cap → recurse with finer separator
                result.extend(_recursive_split(piece))
        return result
    # Should be unreachable (loop always returns when sep == "")
    return [text]
```

Confirm `logger` is already defined at module level. If not (check existing imports), add at the top of the file alongside other imports:

```python
import structlog
logger = structlog.get_logger()
```

(Reuse the existing `summarize.py` style; chunk.py may not yet have a logger — add only if missing.)

- [ ] **Step 4: Run tests to verify pass**

```bash
cd /Users/youngz/webdav/Euro_QA && /Users/youngz/webdav/Euro_QA/.venv/bin/python -m pytest tests/pipeline/test_chunk.py::TestRecursiveSplit -v 2>&1 | tail -20
```

Expected: 5 tests pass.

- [ ] **Step 5: Commit**

```bash
git add pipeline/chunk.py tests/pipeline/test_chunk.py
git commit -m "feat(chunk): add _recursive_split with paragraph/sentence cascade / 增加递归切分主算法"
```

---

## Task 7: Convert `_build_child_text_chunk` → `_build_child_text_chunks` (returns list)

**Files:**
- Test: `/Users/youngz/webdav/Euro_QA/tests/pipeline/test_chunk.py` (append)
- Modify: `/Users/youngz/webdav/Euro_QA/pipeline/chunk.py` lines 233-272

- [ ] **Step 1: Append the failing test class**

Append to `tests/pipeline/test_chunk.py`:

```python


class TestChildTextChunksSplit:
    """_build_child_text_chunks returns list; splits oversized leaf content."""

    def _make_leaf_node(self, content: str, title: str = "1.1.1 Leaf"):
        from pipeline.structure import DocumentNode, ElementType as StructElementType
        return DocumentNode(
            title=title,
            content=content,
            element_type=StructElementType.SECTION,
            source="test_source",
            page_numbers=[1],
            page_file_index=[0],
            clause_ids=[],
            cross_refs=[],
            bbox=[],
            bbox_page_idx=-1,
        )

    def test_short_content_returns_single_chunk_role_child(self):
        from pipeline.chunk import _build_child_text_chunks
        node = self._make_leaf_node("short paragraph here")
        chunks = _build_child_text_chunks(
            node, section_path=["1.1.1 Leaf"], node_identity=(0, 0, 0),
            source_title="test", special_children=[],
        )
        assert len(chunks) == 1
        # role embedded in chunk_id construction; chunk content equals input
        assert chunks[0].content == "short paragraph here"

    def test_oversized_content_yields_multiple_chunks(self):
        from pipeline.chunk import _build_child_text_chunks
        # 2000 tokens worth of paragraphs
        para = "x" * 1000
        big_content = f"{para}\n\n{para}\n\n{para}"
        node = self._make_leaf_node(big_content)
        chunks = _build_child_text_chunks(
            node, section_path=["1.1.1 Leaf"], node_identity=(0, 0, 0),
            source_title="test", special_children=[],
        )
        assert len(chunks) >= 2
        for c in chunks:
            assert len(c.content) // 2 <= 800

    def test_split_chunks_share_metadata_and_section_path(self):
        from pipeline.chunk import _build_child_text_chunks
        para = "y" * 1000
        node = self._make_leaf_node(f"{para}\n\n{para}\n\n{para}")
        chunks = _build_child_text_chunks(
            node, section_path=["1.1.1 Leaf"], node_identity=(0, 0, 0),
            source_title="test", special_children=[],
        )
        assert len(chunks) >= 2
        first_path = chunks[0].metadata.section_path
        first_pages = chunks[0].metadata.page_numbers
        for c in chunks[1:]:
            assert c.metadata.section_path == first_path
            assert c.metadata.page_numbers == first_pages

    def test_split_chunk_ids_are_unique_and_stable(self):
        from pipeline.chunk import _build_child_text_chunks, validate_unique_chunk_ids
        para = "z" * 1000
        node = self._make_leaf_node(f"{para}\n\n{para}\n\n{para}")
        chunks_a = _build_child_text_chunks(
            node, section_path=["1.1.1 Leaf"], node_identity=(0, 0, 0),
            source_title="test", special_children=[],
        )
        chunks_b = _build_child_text_chunks(
            node, section_path=["1.1.1 Leaf"], node_identity=(0, 0, 0),
            source_title="test", special_children=[],
        )
        # Determinism: same input → same chunk_ids
        assert [c.chunk_id for c in chunks_a] == [c.chunk_id for c in chunks_b]
        # Uniqueness: no collisions
        validate_unique_chunk_ids(chunks_a)

    def test_empty_content_returns_empty_list(self):
        from pipeline.chunk import _build_child_text_chunks
        node = self._make_leaf_node("   \n\n  \n")
        chunks = _build_child_text_chunks(
            node, section_path=["1.1.1 Leaf"], node_identity=(0, 0, 0),
            source_title="test", special_children=[],
        )
        assert chunks == []
```

- [ ] **Step 2: Run tests to verify failure**

```bash
cd /Users/youngz/webdav/Euro_QA && /Users/youngz/webdav/Euro_QA/.venv/bin/python -m pytest tests/pipeline/test_chunk.py::TestChildTextChunksSplit -v 2>&1 | tail -20
```

Expected: ImportError on `_build_child_text_chunks` (function not yet renamed).

- [ ] **Step 3: Replace `_build_child_text_chunk` with `_build_child_text_chunks`**

In `pipeline/chunk.py`, replace the entire function `_build_child_text_chunk` (lines 233-272) with:

```python
def _build_child_text_chunks(
    node: DocumentNode,
    section_path: list[str],
    node_identity: tuple[int, ...],
    source_title: str,
    special_children: list[DocumentNode],
) -> list[Chunk]:
    """为叶 section 节点构建子文本块（必要时按 ``_recursive_split`` 切多片）。"""
    content = _insert_placeholders(node.content, special_children)
    if not content.strip():
        return []

    pieces = _recursive_split(content)
    total = len(pieces)
    chunks: list[Chunk] = []

    for split_idx, piece in enumerate(pieces):
        if total == 1:
            role = "child"
            extra_parts: tuple[str, ...] = ()
        else:
            role = "child:split"
            extra_parts = (str(split_idx), str(total))

        chunk_id = _make_chunk_id(
            source=node.source,
            node_identity=node_identity,
            role=role,
            content=piece,
            extra_parts=extra_parts,
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

The original function returned `Chunk | None`. The new one returns `list[Chunk]`. **Task 8 will fix the call site in `_walk_sections`.** Until then, the build will fail anywhere that still calls `_build_child_text_chunk`. That's intentional — it surfaces the rename to the next task.

- [ ] **Step 4: Run new tests to verify pass; expect existing `test_chunk.py` failures from broken `_walk_sections` call site**

```bash
cd /Users/youngz/webdav/Euro_QA && /Users/youngz/webdav/Euro_QA/.venv/bin/python -m pytest tests/pipeline/test_chunk.py::TestChildTextChunksSplit -v 2>&1 | tail -15
```

Expected: 5 new tests pass.

```bash
cd /Users/youngz/webdav/Euro_QA && /Users/youngz/webdav/Euro_QA/.venv/bin/python -m pytest tests/pipeline/test_chunk.py -v 2>&1 | tail -30
```

Expected: existing tests in `TestCreateChunks` etc. fail with `NameError: _build_child_text_chunk` because `_walk_sections` still references the old name. Task 8 will fix this. **Do not commit yet** — broken state.

- [ ] **Step 5: Stage but do not commit (paired commit with Task 8)**

```bash
git add pipeline/chunk.py tests/pipeline/test_chunk.py
git status --short pipeline/chunk.py tests/pipeline/test_chunk.py
```

Expected: both files staged. The commit happens at end of Task 8 to keep the tree green at every commit boundary.

---

## Task 8: Update `_walk_sections` for multi-chunk leaves + parent_chunk_id backfill

**Files:**
- Test: `/Users/youngz/webdav/Euro_QA/tests/pipeline/test_chunk.py` (append)
- Modify: `/Users/youngz/webdav/Euro_QA/pipeline/chunk.py` lines 114-225

- [ ] **Step 1: Append the failing test class**

Append to `tests/pipeline/test_chunk.py`:

```python


class TestWalkSectionsHierarchy:
    """End-to-end create_chunks: hierarchy works, split chunks share parent_chunk_id."""

    def test_nested_sections_produce_parent_and_children(self):
        from pipeline.chunk import create_chunks
        from pipeline.structure import parse_markdown_to_tree
        md = (
            "# 1 General\n\nIntro.\n\n"
            "# 1.1 Scope\n\nScope para.\n\n"
            "# 1.1.1 Detail A\n\nFirst leaf paragraph.\n\n"
            "# 1.1.2 Detail B\n\nSecond leaf paragraph.\n"
        )
        tree = parse_markdown_to_tree(md, source="test")
        chunks = create_chunks(tree, source_title="test")
        # Children are leaves with parent_chunk_id set
        children = [c for c in chunks if c.metadata.parent_chunk_id is not None]
        assert len(children) >= 2
        # All children that share a section path should share parent_chunk_id
        # if their parent has children at the same level
        # (Detail A and Detail B both under 1.1 Scope)
        parent_ids = {c.metadata.parent_chunk_id for c in children}
        assert len(parent_ids) >= 1

    def test_oversized_leaf_yields_split_chunks_sharing_parent(self):
        from pipeline.chunk import create_chunks
        from pipeline.structure import parse_markdown_to_tree
        para = "x" * 1000   # ~500 tokens per paragraph
        big = f"{para}\n\n{para}\n\n{para}"   # ~1500 tokens, will split
        md = (
            "# 1 General\n\nIntro.\n\n"
            f"# 1.1 Scope\n\n{big}\n"
        )
        tree = parse_markdown_to_tree(md, source="test")
        chunks = create_chunks(tree, source_title="test")
        # Find the split children for "1.1 Scope" (multiple chunks, same section_path)
        scope_chunks = [c for c in chunks
                        if any("1.1 Scope" in p for p in c.metadata.section_path)
                        and c.metadata.element_type.value == "text"]
        leaf_splits = [c for c in scope_chunks if c.metadata.parent_chunk_id is not None]
        # If "1.1 Scope" is a leaf under "1 General", it splits into ≥2 chunks
        assert len(leaf_splits) >= 2
        # All splits share the same parent_chunk_id
        parent_ids = {c.metadata.parent_chunk_id for c in leaf_splits}
        assert len(parent_ids) == 1, f"Split chunks must share parent; got {parent_ids}"
        # Each split is under the cap
        for c in leaf_splits:
            assert len(c.content) // 2 <= 800

    def test_special_chunk_links_to_first_split_when_leaf_is_split(self):
        from pipeline.chunk import create_chunks
        from pipeline.structure import parse_markdown_to_tree
        from server.models.schemas import ElementType as ChunkElementType
        para = "y" * 1000
        big = f"{para}\n\n{para}\n\n{para}"
        md = (
            "# 1 General\n\nIntro.\n\n"
            f"# 1.1 Scope\n\n{big}\n\n"
            "| col1 | col2 |\n|---|---|\n| a | 1 |\n"
        )
        tree = parse_markdown_to_tree(md, source="test")
        chunks = create_chunks(tree, source_title="test")
        tables = [c for c in chunks if c.metadata.element_type == ChunkElementType.TABLE]
        assert len(tables) == 1
        # Table's parent_text_chunk_id points to a real text chunk (the representative)
        text_ids = {c.chunk_id for c in chunks
                    if c.metadata.element_type == ChunkElementType.TEXT}
        assert tables[0].metadata.parent_text_chunk_id in text_ids

    def test_unique_chunk_ids_under_split(self):
        from pipeline.chunk import create_chunks, validate_unique_chunk_ids
        from pipeline.structure import parse_markdown_to_tree
        para = "z" * 1000
        big = f"{para}\n\n{para}\n\n{para}"
        md = f"# 1 General\n\nIntro.\n\n# 1.1 Scope\n\n{big}\n"
        tree = parse_markdown_to_tree(md, source="test")
        chunks = create_chunks(tree, source_title="test")
        # validate_unique_chunk_ids raises on collision
        validate_unique_chunk_ids(chunks)
```

- [ ] **Step 2: Run tests to verify failure**

```bash
cd /Users/youngz/webdav/Euro_QA && /Users/youngz/webdav/Euro_QA/.venv/bin/python -m pytest tests/pipeline/test_chunk.py::TestWalkSectionsHierarchy -v 2>&1 | tail -25
```

Expected: tests fail because `_walk_sections` still calls renamed function `_build_child_text_chunk` (NameError) AND because the parent_chunk_id backfill loop assumes one child per leaf.

- [ ] **Step 3: Update `_walk_sections` in `pipeline/chunk.py`**

Replace the entire `_walk_sections` function body (lines 114-225) with:

```python
def _walk_sections(
    node: DocumentNode,
    ancestor_path: list[str],
    node_identity: tuple[int, ...],
    source_title: str,
) -> _ChunkBuildResult:
    """深度优先遍历文档树，在合适的层级生成块。

    叶 section 可能产出多个 child chunks（``_build_child_text_chunks`` 决定），
    但只有第一个被当作 representative_text_chunk 上交父级；其它 split chunks 也归属于
    同一 parent，由本函数的 backfill 逻辑统一回填 ``parent_chunk_id``。
    """
    current_path = (
        ancestor_path + [node.title] if node.title != "root" else ancestor_path
    )

    section_children = [
        (index, child)
        for index, child in enumerate(node.children)
        if child.element_type == StructElementType.SECTION
    ]
    special_children = [
        (index, child)
        for index, child in enumerate(node.children)
        if child.element_type != StructElementType.SECTION
    ]

    if section_children:
        chunks: list[Chunk] = []
        # 每个递归子结果带回 (representative, all_text_chunks_from_that_subtree)
        child_representatives: list[Chunk] = []
        # 收集 split sibling chunks 的引用以便 backfill
        all_sibling_text_chunks: list[Chunk] = []

        for index, child in section_children:
            child_result = _walk_sections(
                child,
                ancestor_path=current_path,
                node_identity=node_identity + (index,),
                source_title=source_title,
            )
            chunks.extend(child_result.chunks)
            if child_result.representative_text_chunk is not None:
                child_representatives.append(child_result.representative_text_chunk)
                all_sibling_text_chunks.extend(child_result.split_text_chunks)

        parent_chunk: Chunk | None = None
        if child_representatives and node.title != "root":
            parent_chunk = _build_parent_chunk(
                node,
                current_path,
                node_identity,
                source_title,
                child_representatives,
            )
            chunks.append(parent_chunk)

            # Backfill parent_chunk_id for all text chunks belonging to direct child sections
            for sibling_chunk in all_sibling_text_chunks:
                if sibling_chunk.metadata.parent_chunk_id is None:
                    sibling_chunk.metadata.parent_chunk_id = parent_chunk.chunk_id

        if special_children and node.title != "root":
            parent_text_chunk_id = (
                parent_chunk.chunk_id if parent_chunk is not None else None
            )
            type_positions: dict[StructElementType, int] = {}
            for index, special in special_children:
                same_type_index = type_positions.get(special.element_type, 0)
                type_positions[special.element_type] = same_type_index + 1
                chunks.append(
                    _build_special_chunk(
                        special,
                        current_path,
                        node_identity + (index,),
                        source_title,
                        node,
                        parent_text_chunk_id,
                        same_type_index=same_type_index,
                    )
                )

        return _ChunkBuildResult(
            chunks=chunks,
            representative_text_chunk=parent_chunk,
            split_text_chunks=[parent_chunk] if parent_chunk else [],
        )

    # Leaf branch: node has NO section children
    if node.title == "root":
        return _ChunkBuildResult(chunks=[], split_text_chunks=[])

    special_nodes = [child for _, child in special_children]
    text_chunks = _build_child_text_chunks(
        node,
        current_path,
        node_identity,
        source_title,
        special_nodes,
    )
    if not text_chunks:
        return _ChunkBuildResult(chunks=[], split_text_chunks=[])

    chunks = list(text_chunks)
    representative = text_chunks[0]   # first split chunk represents this leaf upward

    type_positions: dict[StructElementType, int] = {}
    for index, special in special_children:
        same_type_index = type_positions.get(special.element_type, 0)
        type_positions[special.element_type] = same_type_index + 1
        chunks.append(
            _build_special_chunk(
                special,
                current_path,
                node_identity + (index,),
                source_title,
                node,
                representative.chunk_id,
                same_type_index=same_type_index,
            )
        )

    return _ChunkBuildResult(
        chunks=chunks,
        representative_text_chunk=representative,
        split_text_chunks=text_chunks,
    )
```

Also update the `_ChunkBuildResult` dataclass at lines 55-60 to add the new field:

```python
@dataclass
class _ChunkBuildResult:
    """递归构建结果，包含当前子树的所有块及本节点代表文本块。

    ``split_text_chunks`` 收集本子树直接归属的 text chunks（含 split），便于父级在
    建出 parent chunk 后统一回填 ``parent_chunk_id``。
    """

    chunks: list[Chunk]
    representative_text_chunk: Chunk | None = None
    split_text_chunks: list[Chunk] = field(default_factory=list)
```

Add `from dataclasses import field` to the imports if not already present.

- [ ] **Step 4: Run full test suite for chunk.py to verify all tests pass**

```bash
cd /Users/youngz/webdav/Euro_QA && /Users/youngz/webdav/Euro_QA/.venv/bin/python -m pytest tests/pipeline/test_chunk.py -v 2>&1 | tail -40
```

Expected: all tests pass — `TestCreateChunks` (existing), `TestRecursiveSplit`, `TestGreedyMerge`, `TestSplitByTokensHard`, `TestChildTextChunksSplit`, `TestWalkSectionsHierarchy`.

If any existing `TestCreateChunks` test fails, inspect carefully:
- Is the assertion still semantically correct after hierarchy fix? (e.g., a test that expected `parent_chunk_id` to remain None on a flat tree may now legitimately see it filled.) Update assertion.
- Or is there a real regression in `_walk_sections`? Fix the implementation.

Also run the full pipeline test directory:

```bash
cd /Users/youngz/webdav/Euro_QA && /Users/youngz/webdav/Euro_QA/.venv/bin/python -m pytest tests/pipeline/ -v 2>&1 | tail -40
```

Expected: all green.

- [ ] **Step 5: Commit (paired with Task 7's staged changes)**

```bash
git add pipeline/chunk.py tests/pipeline/test_chunk.py
git commit -m "feat(chunk): split oversized leaf chunks recursively / 递归切分超大叶子块并回填父链"
```

This commit pairs Task 7's `_build_child_text_chunks` rename with Task 8's `_walk_sections` update — keeping the tree green at every commit boundary.

---

## Task 9: Coverage check + final smoke test

**Files:** Read-only verification.

- [ ] **Step 1: Run pytest with coverage on the modified modules**

```bash
cd /Users/youngz/webdav/Euro_QA && /Users/youngz/webdav/Euro_QA/.venv/bin/python -m pytest tests/pipeline/test_structure.py tests/pipeline/test_chunk.py \
  --cov=pipeline.structure --cov=pipeline.chunk \
  --cov-report=term-missing 2>&1 | tail -40
```

Expected: coverage ≥90% on `pipeline/structure.py` modifications and `pipeline/chunk.py` modifications. Note that legacy code in these files may bring overall coverage lower — focus on the **new functions** (`_infer_level`, `_recursive_split`, `_greedy_merge`, `_split_by_tokens_hard`, `_build_child_text_chunks`, updated `_walk_sections` branches).

If a new function shows missing coverage, add a parametrized test case to cover it before continuing.

- [ ] **Step 2: Run the full pipeline test directory one more time**

```bash
cd /Users/youngz/webdav/Euro_QA && /Users/youngz/webdav/Euro_QA/.venv/bin/python -m pytest tests/pipeline/ -q 2>&1 | tail -10
```

Expected: all green, 0 failures.

- [ ] **Step 3: Smoke-test on existing parsed markdown (no Stage 4 / no LLM)**

This verifies acceptance criteria 1, 2, 3 from the spec without rebuilding indexes.

**IMPORTANT correctness note (learned from initial implementation)**: a chunk with `parent_chunk_id != None` is NOT necessarily a leaf — it may be an intermediate parent chunk produced by `_build_parent_chunk` at level 2+ (capped at 4,000 tokens, not 800). The correct definition of "leaf chunk that should be ≤800 tokens" is: **a chunk whose `chunk_id` is not referenced as `parent_chunk_id` by any other chunk**. The smoke test below uses this strict definition.

```bash
cd /Users/youngz/webdav/Euro_QA && /Users/youngz/webdav/Euro_QA/.venv/bin/python << 'PY'
from pathlib import Path
from collections import Counter
from pipeline.structure import parse_markdown_to_tree
from pipeline.chunk import create_chunks

all_pass = True
for md_path in sorted(Path("data/parsed").glob("*/*.md")):
    md = md_path.read_text(encoding="utf-8")
    source = md_path.stem
    tree = parse_markdown_to_tree(md, source=source)
    chunks = create_chunks(tree, source_title=source)

    text_chunks = [c for c in chunks if c.metadata.element_type.value == "text"]

    # Strict leaf detection: chunk_id is not anyone else's parent_chunk_id.
    referenced_as_parent = {c.metadata.parent_chunk_id for c in text_chunks if c.metadata.parent_chunk_id}
    root_parents = [c for c in text_chunks if c.metadata.parent_chunk_id is None]
    mid_parents  = [c for c in text_chunks if c.metadata.parent_chunk_id is not None and c.chunk_id in referenced_as_parent]
    true_leaves  = [c for c in text_chunks if c.metadata.parent_chunk_id is not None and c.chunk_id not in referenced_as_parent]

    leaf_oversize        = [c for c in true_leaves if len(c.content) // 2 > 800]
    parent_oversize_4k   = [c for c in (root_parents + mid_parents) if len(c.content) // 2 > 4000]

    deep            = sum(1 for c in text_chunks if len(c.metadata.section_path) >= 2)
    pct_deep        = 100 * deep // max(len(text_chunks), 1)
    pct_with_parent = 100 * (len(mid_parents) + len(true_leaves)) // max(len(text_chunks), 1)

    ac1 = pct_deep >= 30
    ac2 = len(leaf_oversize) == 0
    ac2_parent = len(parent_oversize_4k) == 0
    ac3 = pct_with_parent >= 10

    print(f"\n--- {source} ---")
    print(f"  text chunks: {len(text_chunks)} = {len(root_parents)} root_parents + {len(mid_parents)} mid_parents + {len(true_leaves)} true_leaves")
    print(f"  AC1 (depth>=2 >= 30%):     {pct_deep}%   {'PASS' if ac1 else 'FAIL'}")
    print(f"  AC2 (true_leaves <= 800):  {len(leaf_oversize)} oversize  {'PASS' if ac2 else 'FAIL'}")
    print(f"     all parents <= 4000:    {len(parent_oversize_4k)} oversize  {'PASS' if ac2_parent else 'FAIL'}")
    print(f"  AC3 (parent_id >= 10%):    {pct_with_parent}%   {'PASS' if ac3 else 'FAIL'}")
    all_pass = all_pass and ac1 and ac2 and ac2_parent and ac3

print(f"\nOVERALL: {'ALL ACCEPTANCE CRITERIA MET' if all_pass else 'FAILURES DETECTED'}")
PY
```

Expected output (acceptance criteria):
- **AC1**: `depth>=2` percentage ≥ 30% on each document
- **AC2**: `true_leaves <= 800: 0 oversize` for each document AND `all parents <= 4000: 0 oversize`
- **AC3**: `parent_id >= 10%` percentage for each document
- **OVERALL: ALL ACCEPTANCE CRITERIA MET**

If any criterion fails, return to the relevant task and investigate. Do NOT commit a "fix" that simply weakens the assertion — find the structural bug.

- [ ] **Step 4: Update Trellis task status**

The Trellis task created during brainstorming for this work is at `.trellis/tasks/05-03-chunking-fix-chunking-pipeline/`. The Trellis CLI does NOT have an `update` subcommand — available verbs are `create`, `start`, `finish`, `add-context`, `validate`, `list`, etc. To mark this work complete, run:

```bash
cd /Users/youngz/webdav/Euro_QA && python3 .trellis/scripts/task.py finish --help
```

Inspect the actual `finish` argument shape (it does not accept the slug as a positional). Most likely workflow: navigate into the task directory, then `finish`. Or, the task can be left in `planning` state if Trellis bookkeeping is not critical — the implementation success is fully captured by the git tags `pre-chunking-fix` → `chunking-fix-complete` and the commit chain.

This step is administrative; non-blocking for the implementation.

- [ ] **Step 5: Commit (smoke test scripts not committed; just final tag)**

The Step 3 smoke-test is throwaway code — do NOT commit. Tag the completed state instead:

```bash
git tag chunking-fix-complete
git log --oneline pre-chunking-fix..chunking-fix-complete
```

Expected: 6-7 commits between the two tags (one per Task 2-8, plus this final tag).

---

## Verification Manifest (mapping spec acceptance criteria to plan steps)

| Spec AC | Verified by |
|---------|-------------|
| 1. ≥30% sections have level ≥ 2 | Task 9 Step 3 (smoke-test on real parsed markdown) |
| 2. all child chunks ≤ 800 tokens | Task 9 Step 3 + Task 8 unit test `test_oversized_leaf_yields_split_chunks_sharing_parent` |
| 3. ≥10% text chunks have parent_chunk_id | Task 9 Step 3 + Task 8 unit test `test_nested_sections_produce_parent_and_children` |
| 4. coverage ≥90% on modified modules | Task 9 Step 1 |
| 5. existing tests green | Task 8 Step 4 + Task 9 Step 2 |
| 6. retrieval quality (subjective) | Out of plan scope — user reruns Stage 1-4 indexing and runs own QA test set |

## Risk Register

| Risk | Mitigation |
|------|-----------|
| Existing `TestCreateChunks` tests assumed flat hierarchy and now break | Task 8 Step 4 explicitly inspects regressions; update assertions if semantically valid, fix code if not |
| `_walk_sections` rewrite has subtle off-by-one in parent_chunk_id backfill across multiple recursion levels | Task 8 unit tests cover both leaf-split + nested-section scenarios; integration test asserts split chunks share parent |
| `_recursive_split` infinite loop on degenerate input | Cascade always terminates: when `sep == ""` it falls through to `_split_by_tokens_hard` which is non-recursive |
| Tag `pre-chunking-fix` collides with existing tag | Task 1 Step 1 `git tag --list pre-chunking-fix` verification; if collision, abort and ask user for alternative tag name |
| Coverage report shows <90% on legacy code in `chunk.py` not touched by this plan | Acceptable; coverage requirement applies to **new/modified code per CLAUDE.md**, not legacy paths. Document gap if asked |

## Out of Plan Scope

- Indexing rebuild (Stage 4 / Milvus / ES) — user runs `python -m pipeline.run --start-stage 2` manually after merge
- Subjective retrieval quality validation
- Any change to `pipeline/index.py`, `pipeline/run.py`, `pipeline/summarize.py`, `pipeline/config.py`
- Any change to `server/` code
- Contextual retrieval (sub-project 2; deferred per separate spec)
