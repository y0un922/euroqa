"""混合分块策略：将文档树转为 parent-child 文本块 + 独立特殊元素块。

核心策略：
- 纯文本 → parent-child 分块（section = parent，subsection = child）
- 表格/公式/图片 → 独立块，通过 parent_text_chunk_id 链回所属文本块
"""
from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

from pipeline.structure import DocumentNode
from pipeline.structure import ElementType as StructElementType
from server.models.schemas import Chunk, ChunkMetadata
from server.models.schemas import ElementType as ChunkElementType

if TYPE_CHECKING:
    pass

# ---------------------------------------------------------------------------
# 配置常量
# ---------------------------------------------------------------------------

_CHILD_MAX_TOKENS = 800
_PARENT_MAX_TOKENS = 4000

# 特殊元素类型到占位符文本的映射
_PLACEHOLDER_MAP: dict[StructElementType, str] = {
    StructElementType.TABLE: "[-> Table]",
    StructElementType.FORMULA: "[-> Formula]",
    StructElementType.IMAGE: "[-> Image]",
}

# structure.ElementType → schemas.ElementType 的映射
_ELEMENT_TYPE_MAP: dict[StructElementType, ChunkElementType] = {
    StructElementType.SECTION: ChunkElementType.TEXT,
    StructElementType.TEXT: ChunkElementType.TEXT,
    StructElementType.TABLE: ChunkElementType.TABLE,
    StructElementType.FORMULA: ChunkElementType.FORMULA,
    StructElementType.IMAGE: ChunkElementType.IMAGE,
}


# ---------------------------------------------------------------------------
# 公共 API
# ---------------------------------------------------------------------------


def create_chunks(tree: DocumentNode, source_title: str = "") -> list[Chunk]:
    """将文档树转换为混合分块列表。

    Parameters
    ----------
    tree:
        由 ``parse_markdown_to_tree`` 生成的文档根节点。
    source_title:
        文档标题，如 ``"Basis of structural design"``。

    Returns
    -------
    list[Chunk]
        包含 parent 文本块、child 文本块和独立特殊元素块的列表。
    """
    chunks: list[Chunk] = []
    _walk_sections(tree, [], source_title, chunks)
    return chunks


# ---------------------------------------------------------------------------
# 内部递归遍历
# ---------------------------------------------------------------------------


def _walk_sections(
    node: DocumentNode,
    ancestor_path: list[str],
    source_title: str,
    out: list[Chunk],
) -> None:
    """深度优先遍历文档树，在合适的层级生成块。"""
    # 获取当前节点的 section 路径
    current_path = (
        ancestor_path + [node.title] if node.title != "root" else ancestor_path
    )

    # 筛选子节点中的 section 子节点和特殊元素子节点
    section_children = [
        c for c in node.children if c.element_type == StructElementType.SECTION
    ]
    special_children = [
        c for c in node.children if c.element_type != StructElementType.SECTION
    ]

    if section_children:
        # 非叶节点：先递归处理所有 section 子节点
        child_text_chunks: list[Chunk] = []
        for child in section_children:
            _walk_sections(child, current_path, source_title, out)
            # 收集刚刚添加的、属于该子节点的 TEXT 类型 child chunk
            # （用于构建 parent 块）

        # 收集该 section 下所有直接子 section 生成的文本块
        child_text_chunks = [
            c
            for c in out
            if c.metadata.element_type == ChunkElementType.TEXT
            and len(c.metadata.section_path) == len(current_path) + 1
            and c.metadata.section_path[: len(current_path)] == current_path
        ]

        # 仅当存在子文本块时，才生成 parent 块
        if child_text_chunks and node.title != "root":
            parent_chunk = _build_parent_chunk(
                node, current_path, source_title, child_text_chunks
            )
            out.append(parent_chunk)

            # 将子文本块的 parent_chunk_id 指向 parent 块
            for child_chunk in child_text_chunks:
                child_chunk.metadata.parent_chunk_id = parent_chunk.chunk_id

        # 非叶节点自身也可能有直接附属的特殊元素（罕见但可能）
        if special_children and node.title != "root":
            text_chunk_id = (
                child_text_chunks[0].chunk_id if child_text_chunks else None
            )
            for special in special_children:
                out.append(
                    _build_special_chunk(
                        special, current_path, source_title, node, text_chunk_id
                    )
                )
    else:
        # 叶节点（subsection）：生成 child 文本块 + 特殊元素块
        if node.title == "root":
            return

        text_chunk = _build_child_text_chunk(
            node, current_path, source_title, special_children
        )
        out.append(text_chunk)

        # 为每个特殊元素生成独立块，链回文本块
        for special in special_children:
            out.append(
                _build_special_chunk(
                    special, current_path, source_title, node, text_chunk.chunk_id
                )
            )


# ---------------------------------------------------------------------------
# 块构建函数
# ---------------------------------------------------------------------------


def _build_child_text_chunk(
    node: DocumentNode,
    section_path: list[str],
    source_title: str,
    special_children: list[DocumentNode],
) -> Chunk:
    """为叶 section 节点构建子文本块。"""
    # 在文本内容中为特殊元素插入占位符
    content = _insert_placeholders(node.content, special_children)

    chunk_id = _make_chunk_id(node.source, section_path, "child")
    return Chunk(
        chunk_id=chunk_id,
        content=content,
        embedding_text=content,
        metadata=ChunkMetadata(
            source=node.source,
            source_title=source_title,
            section_path=section_path,
            page_numbers=node.page_numbers,
            page_file_index=[],
            clause_ids=node.clause_ids,
            element_type=ChunkElementType.TEXT,
            cross_refs=node.cross_refs,
            parent_chunk_id=None,  # 稍后由 parent 构建时回填
        ),
    )


def _build_parent_chunk(
    node: DocumentNode,
    section_path: list[str],
    source_title: str,
    child_chunks: list[Chunk],
) -> Chunk:
    """为非叶 section 节点构建父文本块（拼接所有子文本内容）。"""
    # 拼接所有子块文本，用换行分隔
    parts: list[str] = []
    for child in child_chunks:
        parts.append(child.content)
    combined = "\n\n".join(parts)

    # 超长截断
    combined = _truncate_by_tokens(combined, _PARENT_MAX_TOKENS)

    chunk_id = _make_chunk_id(node.source, section_path, "parent")

    # 汇总子节点的元数据
    all_pages: list[int] = []
    all_clause_ids: list[str] = []
    all_cross_refs: list[str] = []
    seen_pages: set[int] = set()
    seen_clauses: set[str] = set()
    seen_refs: set[str] = set()

    for child in child_chunks:
        for p in child.metadata.page_numbers:
            if p not in seen_pages:
                seen_pages.add(p)
                all_pages.append(p)
        for c in child.metadata.clause_ids:
            if c not in seen_clauses:
                seen_clauses.add(c)
                all_clause_ids.append(c)
        for r in child.metadata.cross_refs:
            if r not in seen_refs:
                seen_refs.add(r)
                all_cross_refs.append(r)

    return Chunk(
        chunk_id=chunk_id,
        content=combined,
        embedding_text=combined,
        metadata=ChunkMetadata(
            source=node.source,
            source_title=source_title,
            section_path=section_path,
            page_numbers=all_pages,
            page_file_index=[],
            clause_ids=all_clause_ids,
            element_type=ChunkElementType.TEXT,
            cross_refs=all_cross_refs,
            parent_chunk_id=None,  # parent 块自身无父块
        ),
    )


def _build_special_chunk(
    special_node: DocumentNode,
    section_path: list[str],
    source_title: str,
    parent_section: DocumentNode,
    parent_text_chunk_id: str | None,
) -> Chunk:
    """为表格/公式/图片构建独立块。"""
    element_type = _ELEMENT_TYPE_MAP.get(
        special_node.element_type, ChunkElementType.TEXT
    )
    suffix = f"{element_type.value}_{special_node.title}"
    chunk_id = _make_chunk_id(parent_section.source, section_path, suffix)

    return Chunk(
        chunk_id=chunk_id,
        content=special_node.content,
        embedding_text=special_node.content,  # 后续 Task 5 会替换为 LLM 摘要
        metadata=ChunkMetadata(
            source=parent_section.source,
            source_title=source_title,
            section_path=section_path,
            page_numbers=parent_section.page_numbers,
            page_file_index=[],
            clause_ids=[],
            element_type=element_type,
            cross_refs=special_node.cross_refs,
            parent_text_chunk_id=parent_text_chunk_id,
        ),
    )


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------


def _make_chunk_id(source: str, section_path: list[str], suffix: str) -> str:
    """基于来源、章节路径和后缀生成确定性块 ID。"""
    raw = f"{source}|{'|'.join(section_path)}|{suffix}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()[:16]


def _estimate_tokens(text: str) -> int:
    """粗略估算 token 数（中英混合文本，约 2 字符 = 1 token）。"""
    return len(text) // 2


def _truncate_by_tokens(text: str, max_tokens: int) -> str:
    """按 token 估算截断文本。"""
    max_chars = max_tokens * 2
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "…"


def _insert_placeholders(
    text: str, special_children: list[DocumentNode]
) -> str:
    """在文本末尾追加特殊元素占位符。

    由于 structure.py 已将特殊元素从正文中提取，此处只需在
    文本尾部添加占位符以保持语义完整性。
    """
    if not special_children:
        return text

    placeholders: list[str] = []
    for child in special_children:
        placeholder = _PLACEHOLDER_MAP.get(child.element_type)
        if placeholder:
            placeholders.append(placeholder)

    if placeholders:
        return text + "\n" + "\n".join(placeholders)
    return text
