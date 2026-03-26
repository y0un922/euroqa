"""Markdown -> structured document tree parser (Stage 2).

Parses MinerU's Markdown output into a hierarchy of ``DocumentNode`` objects,
detecting headings, tables, formulas, and images along the way.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

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
    clause_ids: list[str] = field(default_factory=list)
    cross_refs: list[str] = field(default_factory=list)
    children: list[DocumentNode] = field(default_factory=list)
    source: str = ""


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

# Markdown 图片引用
_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")

# 交叉引用模式
_EN_REF_RE = re.compile(r"EN\s+\d{4}(?:-\d+(?:-\d+)?)?")
_ANNEX_REF_RE = re.compile(r"Annex\s+[A-Z]\d*")


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


def parse_markdown_to_tree(markdown: str, source: str = "") -> DocumentNode:
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

    # 用栈构建层级树
    # 栈中每个元素为 (level, node)
    stack: list[tuple[int, DocumentNode]] = [(0, root)]

    for level, title, body in segments:
        node = DocumentNode(
            title=title,
            element_type=ElementType.SECTION,
            level=level,
            source=source,
        )

        # 解析正文中的特殊元素并提取纯文本
        text_content, special_children = _extract_special_elements(body, source)
        node.content = text_content
        node.children.extend(special_children)
        node.cross_refs = extract_cross_refs(body)
        node.clause_ids = _extract_clause_ids(body)

        # 回退栈直到找到严格更小 level 的祖先节点
        while stack[-1][0] >= level:
            stack.pop()

        parent = stack[-1][1]
        parent.children.append(node)
        stack.append((level, node))

    return root


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
        )
        nodes.append(node)

    remaining = "\n".join(non_table_lines)
    return remaining, nodes


def _extract_clause_ids(text: str) -> list[str]:
    """从正文中提取条款编号，如 (1)、(2)P 等。"""
    clause_re = re.compile(r"^\((\d+)\)P?\b", re.MULTILINE)
    return [m.group(0) for m in clause_re.finditer(text)]
