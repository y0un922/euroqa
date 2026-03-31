"""Markdown -> structured document tree parser (Stage 2).

Parses MinerU's Markdown output into a hierarchy of ``DocumentNode`` objects,
detecting headings, tables, formulas, and images along the way.
"""
from __future__ import annotations

import re
from copy import deepcopy
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from pipeline.content_list import resolve_section_page_metadata

# ---------------------------------------------------------------------------
# 元素类型枚举（比 schemas.py 多一个 SECTION）
# ---------------------------------------------------------------------------

class ElementType(str, Enum):
    """文档节点的元素类型。"""
    TEXT = "text"
    TABLE = "table"
    FORMULA = "formula"
    IMAGE = "image"
    SECTION = "section"


# ---------------------------------------------------------------------------
# 文档节点数据类
# ---------------------------------------------------------------------------

@dataclass
class DocumentNode:
    """文档树中的一个节点，代表章节、子节或特殊元素。"""
    title: str
    content: str = ""
    element_type: ElementType = ElementType.SECTION
    level: int = 0
    page_numbers: list[int] = field(default_factory=list)
    page_file_index: list[int] = field(default_factory=list)
    clause_ids: list[str] = field(default_factory=list)
    cross_refs: list[str] = field(default_factory=list)
    children: list[DocumentNode] = field(default_factory=list)
    source: str = ""


# ---------------------------------------------------------------------------
# 树清洗配置
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TreePruningConfig:
    """文档树后处理清洗配置。

    控制 ``prune_document_tree`` 的行为：哪些前置内容裁剪、
    哪些空节点删除、哪些页眉合并回前一节。
    """

    enabled: bool = True
    # 正文起始标题（casefold 后匹配），找到后其前所有顶层节点被裁剪
    body_start_titles: tuple[str, ...] = ("foreword",)
    # 空内容且无子节点的节点如果标题匹配则直接删除
    removable_empty_titles: tuple[str, ...] = (
        "contents",
        "modifications",
        "corrections",
        "national foreword",
        "english version",
    )
    # 页眉模式（如 "EN 1990:2002 (E)"），匹配到的节点合并到前一个有效 section
    running_header_patterns: tuple[str, ...] = (
        r"^en\s+\d{4}(?::\d{4})?(?:-\d+(?:-\d+)?)?(?:\s*\([a-z]\))?$",
    )

    @classmethod
    def from_pipeline_settings(
        cls,
        *,
        enabled: bool = True,
        body_start_titles: str = "",
    ) -> TreePruningConfig:
        """从 pipeline 配置字符串构建清洗配置。"""
        defaults = cls()
        titles = tuple(
            t.strip().casefold()
            for t in body_start_titles.split(",")
            if t.strip()
        )
        return cls(
            enabled=enabled,
            body_start_titles=titles or defaults.body_start_titles,
        )


# ---------------------------------------------------------------------------
# 正则模式
# ---------------------------------------------------------------------------

# Markdown 标题行：至少一个 # 后跟空格和标题文字
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)

# 行内数学公式块 $$...$$（可跨行）
_FORMULA_BLOCK_RE = re.compile(
    r"(\$\$.+?\$\$)"           # 公式主体
    r"("                        # 可选的 where 定义块
    r"\s*\n\s*where\s*:\s*\n"   # "where:" 行
    r"(?:.*\n?)*?"              # 定义列表内容（惰性匹配）
    r")?",
    re.DOTALL,
)

# Markdown 表格块：连续的以 | 开头的行（含分隔行 |---|）
_TABLE_LINE_RE = re.compile(r"^\|.*$", re.MULTILINE)
_HTML_TABLE_BLOCK_RE = re.compile(
    r"(?:(?P<caption>^Table\s+[^\n]+)\s*\n\s*)?(?P<table><table\b[^>]*>.*?</table>)",
    re.DOTALL | re.MULTILINE,
)

# Markdown 图片引用
_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")

# 交叉引用模式
_EN_REF_RE = re.compile(r"EN\s+\d{4}(?:-\d+(?:-\d+)?)?")
_ANNEX_REF_RE = re.compile(r"Annex\s+[A-Z]\d*")

# --- 清洗用正则 ---
# 标题尾部的 dot-leader + 页码（如 "SECTION 1 GENERAL .. 0"、"... . 23"）
# 允许点号之间有空格
_TITLE_PAGE_SUFFIX_RE = re.compile(r"\s*(?:[.\u00b7\u2026]\s*){2,}\d+\s*$")
# 标题尾部连续点号（如 "FOREWORD..."）
_TRAILING_DOTS_RE = re.compile(r"\s*(?:[.\u00b7\u2026]\s*){3,}$")
# 目录行：文本 + dot-leader + 页码（如 "1.1 SCOPE .. ... 9"）
_TOC_LINE_RE = re.compile(r"^.{3,}(?:[.\u00b7\u2026]\s*){2,}\d+\s*$")


# ---------------------------------------------------------------------------
# 公共 API
# ---------------------------------------------------------------------------

def extract_cross_refs(text: str) -> list[str]:
    """从文本中提取 Eurocode 交叉引用。

    识别两类引用：
    - ``EN nnnn`` 或 ``EN nnnn-n-n`` 格式的标准引用
    - ``Annex X`` 或 ``Annex Xn`` 格式的附录引用

    返回去重后的引用列表。
    """
    refs: list[str] = []
    seen: set[str] = set()
    for pattern in (_EN_REF_RE, _ANNEX_REF_RE):
        for match in pattern.finditer(text):
            ref = match.group()
            if ref not in seen:
                seen.add(ref)
                refs.append(ref)
    return refs


def parse_markdown_to_tree(
    markdown: str,
    source: str = "",
    content_list: object | None = None,
) -> DocumentNode:
    """将 Markdown 文本解析为文档树。

    Parameters
    ----------
    markdown:
        MinerU 输出的 Markdown 文本。
    source:
        来源标识，如 ``"EN 1990:2002"``。

    Returns
    -------
    DocumentNode
        根节点，其 ``children`` 包含顶层章节。
    """
    root = DocumentNode(title="root", source=source)

    # 找出所有标题及其在原文中的位置
    headings = list(_HEADING_RE.finditer(markdown))
    if not headings:
        # 无标题则整段作为根节点内容
        root.content = markdown.strip()
        root.cross_refs = extract_cross_refs(markdown)
        page_metadata = resolve_section_page_metadata([(0, "root", root.content)], content_list)
        if page_metadata:
            root.page_numbers, root.page_file_index, *_ = page_metadata[0]
        return root

    # 将文档拆分为 (level, title, body) 段落
    segments: list[tuple[int, str, str]] = []
    for i, match in enumerate(headings):
        level = len(match.group(1))
        title = match.group(2).strip()
        body_start = match.end()
        body_end = headings[i + 1].start() if i + 1 < len(headings) else len(markdown)
        body = markdown[body_start:body_end].strip()
        segments.append((level, title, body))

    section_pages = resolve_section_page_metadata(segments, content_list)

    # 用栈构建层级树
    # 栈中每个元素为 (level, node)
    stack: list[tuple[int, DocumentNode]] = [(0, root)]

    for (level, title, body), (page_numbers, page_file_index, *_) in zip(
        segments,
        section_pages,
        strict=False,
    ):
        node = DocumentNode(
            title=title,
            element_type=ElementType.SECTION,
            level=level,
            page_numbers=page_numbers,
            page_file_index=page_file_index,
            source=source,
        )

        # 解析正文中的特殊元素并提取纯文本
        text_content, special_children = _extract_special_elements(body, source)
        node.content = text_content
        for child in special_children:
            child.page_numbers = list(page_numbers)
            child.page_file_index = list(page_file_index)
        node.children.extend(special_children)
        node.cross_refs = extract_cross_refs(body)
        node.clause_ids = _extract_clause_ids(body)

        # 把章节标题中的编号（如 "3.1"、"B3.1"、"A1.2.1"）插入 clause_ids 开头
        section_number = _extract_section_number(title)
        if section_number and section_number not in node.clause_ids:
            node.clause_ids.insert(0, section_number)

        # 回退栈直到找到严格更小 level 的祖先节点
        while stack[-1][0] >= level:
            stack.pop()

        parent = stack[-1][1]
        parent.children.append(node)
        stack.append((level, node))

    return root


# ---------------------------------------------------------------------------
# 文档树清洗（Stage 2.5）
# ---------------------------------------------------------------------------

def prune_document_tree(
    tree: DocumentNode,
    config: TreePruningConfig | None = None,
) -> DocumentNode:
    """清洗文档树中的封面、目录、页眉等噪音节点。

    在 ``parse_markdown_to_tree`` 之后、``create_chunks`` 之前调用。
    返回深拷贝后的清洗结果，不修改原始树。
    """
    cfg = config or TreePruningConfig()
    pruned = deepcopy(tree)
    if not cfg.enabled:
        return pruned

    pruned.children = _prune_top_level(pruned.children, cfg)
    return pruned


def _prune_top_level(
    nodes: list[DocumentNode],
    cfg: TreePruningConfig,
) -> list[DocumentNode]:
    """顶层节点清洗：先裁剪正文前缀，再递归清洗每个节点。"""
    # 第一步：找到正文起始位置，裁剪其前所有节点
    body_idx = _find_body_start_index(nodes, cfg)
    if body_idx is not None:
        working = nodes[body_idx:]
    else:
        # 找不到正文起点时保守处理：保留所有节点
        working = list(nodes)

    # 第二步：递归清洗
    return _prune_nodes(working, cfg)


def _prune_nodes(
    nodes: list[DocumentNode],
    cfg: TreePruningConfig,
) -> list[DocumentNode]:
    """递归清洗节点列表：清洗标题、删空节点、合并页眉。"""
    kept: list[DocumentNode] = []

    for node in nodes:
        if node.element_type != ElementType.SECTION:
            kept.append(node)
            continue

        # 清洗标题中的页码残留
        node.title = _clean_heading_title(node.title)
        # 递归清洗子节点
        node.children = _prune_nodes(node.children, cfg)

        # 规则 1：删除可移除的空节点
        if _is_removable_empty(node, cfg):
            continue

        # 规则 2：页眉节点合并到前一个有效 section
        if _is_running_header(node.title, cfg):
            prev = _find_last_section(kept)
            if prev is not None:
                _merge_into_previous(prev, node)
                continue
            # 无前一节且自身为空则丢弃
            if not node.content.strip() and not node.children:
                continue

        kept.append(node)

    return kept


def _find_body_start_index(
    nodes: list[DocumentNode],
    cfg: TreePruningConfig,
) -> int | None:
    """在顶层节点中找到第一个真正的正文起始节点。

    必须同时满足：标题匹配 body_start_titles 且内容不像目录。
    """
    for i, node in enumerate(nodes):
        if node.element_type != ElementType.SECTION:
            continue
        cleaned = _clean_heading_title(node.title)
        if cleaned.casefold().strip(" .:") not in cfg.body_start_titles:
            continue
        # 排除 TOC 中的同名标题（如 "# FOREWORD..."，内容全是页码引用）
        if _looks_like_toc_content(node.title, node.content):
            continue
        return i
    return None


def _clean_heading_title(title: str) -> str:
    """清洗标题中的 dot-leader 和页码残留。

    "SECTION 1 GENERAL .. 0"  → "SECTION 1 GENERAL"
    "FOREWORD..."              → "FOREWORD"
    """
    cleaned = re.sub(r"\s+", " ", title.strip())
    # 先去 dot-leader + 页码
    cleaned = _TITLE_PAGE_SUFFIX_RE.sub("", cleaned)
    # 再去尾部连续点号
    cleaned = _TRAILING_DOTS_RE.sub("", cleaned)
    return cleaned.strip(" .") or title.strip()


def _looks_like_toc_content(raw_title: str, content: str) -> bool:
    """判断一个节点是否是目录条目（标题带页码或内容大部分是目录行）。"""
    # 标题自身带 dot-leader + 页码
    if _TITLE_PAGE_SUFFIX_RE.search(raw_title):
        return True
    # 内容中超过 60% 的非空行是目录样式
    lines = [line.strip() for line in content.splitlines() if line.strip()]
    if len(lines) < 2:
        return False
    toc_count = sum(1 for line in lines if _TOC_LINE_RE.match(line))
    return toc_count / len(lines) >= 0.6


def _is_removable_empty(node: DocumentNode, cfg: TreePruningConfig) -> bool:
    """判断空内容且无子节点的 section 是否应删除。"""
    if node.content.strip() or node.children:
        return False
    return node.title.casefold().strip(" .:") in cfg.removable_empty_titles


def _is_running_header(title: str, cfg: TreePruningConfig) -> bool:
    """判断标题是否匹配页眉模式（如 "EN 1990:2002 (E)"）。"""
    normalized = title.casefold().strip()
    return any(
        re.match(pattern, normalized)
        for pattern in cfg.running_header_patterns
    )


def _find_last_section(nodes: list[DocumentNode]) -> Optional[DocumentNode]:
    """从列表尾部向前找到最后一个 section 节点。"""
    for node in reversed(nodes):
        if node.element_type == ElementType.SECTION:
            return node
    return None


def _merge_into_previous(prev: DocumentNode, current: DocumentNode) -> None:
    """将页眉节点的内容和子节点合并到前一个 section。"""
    if current.content.strip():
        parts = [p for p in (prev.content, current.content) if p.strip()]
        prev.content = "\n\n".join(parts)
    prev.children.extend(current.children)
    # 合并去重元数据
    prev.page_numbers = list(dict.fromkeys(prev.page_numbers + current.page_numbers))
    prev.page_file_index = list(
        dict.fromkeys(prev.page_file_index + current.page_file_index)
    )
    prev.clause_ids = list(dict.fromkeys(prev.clause_ids + current.clause_ids))
    prev.cross_refs = list(dict.fromkeys(prev.cross_refs + current.cross_refs))


# ---------------------------------------------------------------------------
# 内部辅助函数
# ---------------------------------------------------------------------------

def _extract_special_elements(
    body: str, source: str
) -> tuple[str, list[DocumentNode]]:
    """从章节正文中提取表格、公式和图片等特殊元素。

    Returns
    -------
    tuple[str, list[DocumentNode]]
        (剩余纯文本, 特殊元素节点列表)
    """
    children: list[DocumentNode] = []
    remaining = body

    # --- 公式提取 ---
    remaining, formula_nodes = _extract_formulas(remaining, source)
    children.extend(formula_nodes)

    # --- 图片提取 ---
    remaining, image_nodes = _extract_images(remaining, source)
    children.extend(image_nodes)

    # --- 表格提取 ---
    remaining, table_nodes = _extract_tables(remaining, source)
    children.extend(table_nodes)

    return remaining.strip(), children


def _extract_formulas(
    text: str, source: str
) -> tuple[str, list[DocumentNode]]:
    """提取 $$...$$ 公式块（含可选的 where 定义）。"""
    nodes: list[DocumentNode] = []
    remaining = text

    # 使用更精确的逐步匹配：先找 $$...$$，再向后探测 where 块
    formula_re = re.compile(r"\$\$(.+?)\$\$", re.DOTALL)
    offset = 0
    parts: list[str] = []
    last_end = 0

    for match in formula_re.finditer(text):
        formula_content = match.group(0)  # 含 $$ 的完整匹配
        formula_inner = match.group(1)    # 不含 $$ 的内容
        block_start = match.start()
        block_end = match.end()

        # 探测 where 块：紧跟公式之后（允许空行）
        after_formula = text[block_end:]
        where_match = re.match(
            r"\s*\n\s*where\s*:\s*\n((?:.*\n?)*)",
            after_formula,
        )
        if where_match:
            where_text = where_match.group(0)
            # 修剪 where 块：到第一个空行段落结束或文本末尾
            where_lines: list[str] = []
            for line in where_text.split("\n"):
                # where 块中每行要么以 - 开头（列表项）要么是续行
                # 遇到不属于 where 定义的行则停止
                stripped = line.strip()
                if where_lines and stripped == "" :
                    # 空行后看下一行是否还是列表项
                    break
                where_lines.append(line)
            where_block = "\n".join(where_lines)
            formula_content = formula_content + "\n" + where_block.strip()
            block_end = block_end + len(where_block)

        parts.append(text[last_end:block_start])
        last_end = block_end

        node = DocumentNode(
            title="formula",
            content=formula_content.strip(),
            element_type=ElementType.FORMULA,
            source=source,
            cross_refs=extract_cross_refs(formula_content),
        )
        nodes.append(node)

    parts.append(text[last_end:])
    remaining = "".join(parts)
    return remaining, nodes


def _extract_images(
    text: str, source: str
) -> tuple[str, list[DocumentNode]]:
    """提取 Markdown 图片引用。"""
    nodes: list[DocumentNode] = []
    remaining = text

    for match in _IMAGE_RE.finditer(text):
        alt = match.group(1)
        path = match.group(2)
        node = DocumentNode(
            title=alt or "image",
            content=match.group(0),
            element_type=ElementType.IMAGE,
            source=source,
        )
        nodes.append(node)

    # 从剩余文本中移除已提取的图片标记
    remaining = _IMAGE_RE.sub("", remaining)
    return remaining, nodes


def _extract_tables(
    text: str, source: str
) -> tuple[str, list[DocumentNode]]:
    """提取 HTML/Markdown 表格块。"""
    remaining, html_nodes = _extract_html_tables(text, source)
    markdown_remaining, markdown_nodes = _extract_markdown_tables(remaining, source)
    return markdown_remaining, [*html_nodes, *markdown_nodes]


def _extract_html_tables(
    text: str, source: str
) -> tuple[str, list[DocumentNode]]:
    """提取 MinerU 产出的 HTML 表格块。"""
    nodes: list[DocumentNode] = []
    parts: list[str] = []
    cursor = 0

    for match in _HTML_TABLE_BLOCK_RE.finditer(text):
        start, end = match.span()
        parts.append(text[cursor:start])
        cursor = end

        caption = (match.group("caption") or "").strip()
        table_html = match.group("table").strip()
        content = f"{caption}\n{table_html}".strip() if caption else table_html
        nodes.append(
            DocumentNode(
                title=caption or "table",
                content=content,
                element_type=ElementType.TABLE,
                source=source,
                cross_refs=extract_cross_refs(content),
            )
        )

    parts.append(text[cursor:])
    return "".join(parts), nodes


def _extract_markdown_tables(
    text: str, source: str
) -> tuple[str, list[DocumentNode]]:
    """提取 Markdown 表格块（连续 | 开头的行）。"""
    nodes: list[DocumentNode] = []
    lines = text.split("\n")
    table_lines: list[str] = []
    non_table_lines: list[str] = []

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("|"):
            table_lines.append(line)
        else:
            # 如果之前积累了表格行，则生成表格节点
            if table_lines:
                table_content = "\n".join(table_lines)
                node = DocumentNode(
                    title="table",
                    content=table_content,
                    element_type=ElementType.TABLE,
                    source=source,
                    cross_refs=extract_cross_refs(table_content),
                )
                nodes.append(node)
                table_lines = []
            non_table_lines.append(line)

    # 处理尾部残留的表格行
    if table_lines:
        table_content = "\n".join(table_lines)
        node = DocumentNode(
            title="table",
            content=table_content,
            element_type=ElementType.TABLE,
            source=source,
            cross_refs=extract_cross_refs(table_content),
        )
        nodes.append(node)

    remaining = "\n".join(non_table_lines)
    return remaining, nodes


def _extract_clause_ids(text: str) -> list[str]:
    """从正文中提取条款编号，如 (1)、(2)P 等。"""
    clause_re = re.compile(r"^\((\d+)\)P?\b", re.MULTILINE)
    return [m.group(0) for m in clause_re.finditer(text)]


def _extract_section_number(title: str) -> str | None:
    """从章节标题中提取章节号，如 '3.1 General' -> '3.1'，'B3.1 Consequences classes' -> 'B3.1'。"""
    match = re.match(r"([A-Z]?\d+(?:\.\d+)*)\s", title)
    return match.group(1) if match else None
