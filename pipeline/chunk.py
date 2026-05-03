"""混合分块策略：将文档树转为 parent-child 文本块 + 独立特殊元素块。

核心策略：
- 纯文本 → parent-child 分块（section = parent，subsection = child）
- 表格/公式/图片 → 独立块，通过 parent_text_chunk_id 链回所属文本块
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from pipeline.structure import DocumentNode
from pipeline.structure import ElementType as StructElementType
from shared.reference_graph import build_object_id
from shared.reference_graph import classify_reference_label
from shared.reference_graph import extract_clause_key
from shared.reference_graph import normalize_reference_label
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


@dataclass
class _ChunkBuildResult:
    """递归构建结果，包含当前子树的所有块及本节点代表文本块。"""

    chunks: list[Chunk]
    representative_text_chunk: Chunk | None = None


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
    result = _walk_sections(
        tree,
        ancestor_path=[],
        node_identity=(),
        source_title=source_title,
    )
    validate_unique_chunk_ids(result.chunks)
    return result.chunks


def validate_unique_chunk_ids(chunks: list[Chunk]) -> None:
    """Fail fast when chunk IDs are not unique within a stage output."""
    seen: dict[str, Chunk] = {}
    duplicates: list[str] = []

    for chunk in chunks:
        if chunk.chunk_id in seen:
            duplicates.append(chunk.chunk_id)
            continue
        seen[chunk.chunk_id] = chunk

    if not duplicates:
        return

    sample = ", ".join(duplicates[:5])
    raise ValueError(
        f"Duplicate chunk IDs detected ({len(duplicates)} collisions). "
        f"Sample IDs: {sample}"
    )


# ---------------------------------------------------------------------------
# 内部递归遍历
# ---------------------------------------------------------------------------


def _walk_sections(
    node: DocumentNode,
    ancestor_path: list[str],
    node_identity: tuple[int, ...],
    source_title: str,
 ) -> _ChunkBuildResult:
    """深度优先遍历文档树，在合适的层级生成块。"""
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
        child_text_chunks: list[Chunk] = []

        for index, child in section_children:
            child_result = _walk_sections(
                child,
                ancestor_path=current_path,
                node_identity=node_identity + (index,),
                source_title=source_title,
            )
            chunks.extend(child_result.chunks)
            if child_result.representative_text_chunk is not None:
                child_text_chunks.append(child_result.representative_text_chunk)

        parent_chunk: Chunk | None = None
        if child_text_chunks and node.title != "root":
            parent_chunk = _build_parent_chunk(
                node,
                current_path,
                node_identity,
                source_title,
                child_text_chunks,
            )
            chunks.append(parent_chunk)

            for child_chunk in child_text_chunks:
                child_chunk.metadata.parent_chunk_id = parent_chunk.chunk_id

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
        )

    if node.title == "root":
        return _ChunkBuildResult(chunks=[])

    special_nodes = [child for _, child in special_children]
    text_chunk = _build_child_text_chunk(
        node,
        current_path,
        node_identity,
        source_title,
        special_nodes,
    )
    if text_chunk is None:
        return _ChunkBuildResult(chunks=[])

    chunks = [text_chunk]

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
                text_chunk.chunk_id,
                same_type_index=same_type_index,
            )
        )

    return _ChunkBuildResult(
        chunks=chunks,
        representative_text_chunk=text_chunk,
    )


# ---------------------------------------------------------------------------
# 块构建函数
# ---------------------------------------------------------------------------


def _build_child_text_chunk(
    node: DocumentNode,
    section_path: list[str],
    node_identity: tuple[int, ...],
    source_title: str,
    special_children: list[DocumentNode],
) -> Chunk | None:
    """为叶 section 节点构建子文本块。"""
    # 在文本内容中为特殊元素插入占位符
    content = _insert_placeholders(node.content, special_children)
    if not content.strip():
        return None

    chunk_id = _make_chunk_id(
        source=node.source,
        node_identity=node_identity,
        role="child",
        content=content,
    )
    return Chunk(
        chunk_id=chunk_id,
        content=content,
        embedding_text=content,
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
            parent_chunk_id=None,  # 稍后由 parent 构建时回填
            bbox=list(node.bbox),
            bbox_page_idx=node.bbox_page_idx,
            **_build_clause_object_fields(node.source, node.title),
        ),
    )


def _build_parent_chunk(
    node: DocumentNode,
    section_path: list[str],
    node_identity: tuple[int, ...],
    source_title: str,
    child_chunks: list[Chunk],
) -> Chunk:
    """为非叶 section 节点构建父文本块（拼接所有子文本内容）。"""
    # 拼接所有子块文本，用换行分隔
    parts: list[str] = []
    for child in child_chunks:
        parts.append(child.content)
    combined = "\n\n".join(parts)
    full_combined = combined

    combined = _truncate_by_tokens(combined, _PARENT_MAX_TOKENS)
    chunk_id = _make_chunk_id(
        source=node.source,
        node_identity=node_identity,
        role="parent",
        content=full_combined,
        extra_parts=tuple(child.chunk_id for child in child_chunks),
    )

    # 汇总子节点的元数据
    all_pages: list[int] = []
    all_page_file_indexes: list[int] = []
    all_clause_ids: list[str] = []
    all_cross_refs: list[str] = []
    seen_pages: set[int] = set()
    seen_page_file_indexes: set[int] = set()
    seen_clauses: set[str] = set()
    seen_refs: set[str] = set()

    for child in child_chunks:
        for p in child.metadata.page_numbers:
            if p not in seen_pages:
                seen_pages.add(p)
                all_pages.append(p)
        for page_index in child.metadata.page_file_index:
            if page_index not in seen_page_file_indexes:
                seen_page_file_indexes.add(page_index)
                all_page_file_indexes.append(page_index)
        for c in child.metadata.clause_ids:
            if c not in seen_clauses:
                seen_clauses.add(c)
                all_clause_ids.append(c)
        for r in child.metadata.cross_refs:
            if r not in seen_refs:
                seen_refs.add(r)
                all_cross_refs.append(r)

    # 取第一个有 bbox 的子块的位置信息作为父块的代表性位置
    first_bbox: list[float] = []
    first_bbox_page_idx = -1
    for child in child_chunks:
        if child.metadata.bbox:
            first_bbox = list(child.metadata.bbox)
            first_bbox_page_idx = child.metadata.bbox_page_idx
            break

    return Chunk(
        chunk_id=chunk_id,
        content=combined,
        embedding_text=combined,
        metadata=ChunkMetadata(
            source=node.source,
            source_title=source_title,
            section_path=section_path,
            page_numbers=all_pages,
            page_file_index=all_page_file_indexes,
            clause_ids=all_clause_ids,
            element_type=ChunkElementType.TEXT,
            cross_refs=all_cross_refs,
            ref_labels=list(all_cross_refs),
            ref_object_ids=_build_ref_object_ids(node.source, all_cross_refs),
            parent_chunk_id=None,  # parent 块自身无父块
            bbox=first_bbox,
            bbox_page_idx=first_bbox_page_idx,
            **_build_clause_object_fields(node.source, node.title),
        ),
    )


def _build_special_chunk(
    special_node: DocumentNode,
    section_path: list[str],
    node_identity: tuple[int, ...],
    source_title: str,
    parent_section: DocumentNode,
    parent_text_chunk_id: str | None,
    same_type_index: int = 0,
) -> Chunk:
    """为表格/公式/图片构建独立块。"""
    element_type = _ELEMENT_TYPE_MAP.get(
        special_node.element_type, ChunkElementType.TEXT
    )
    chunk_id = _make_chunk_id(
        source=parent_section.source,
        node_identity=node_identity,
        role=f"special:{element_type.value}",
        content=special_node.content,
        extra_parts=(special_node.title,),
    )

    # 优先使用特殊节点自身的 bbox；若无则回退到父 section 的 bbox
    bbox = list(special_node.bbox) if special_node.bbox else list(parent_section.bbox)
    bbox_page_idx = (
        special_node.bbox_page_idx
        if special_node.bbox
        else parent_section.bbox_page_idx
    )

    return Chunk(
        chunk_id=chunk_id,
        content=special_node.content,
        embedding_text=special_node.content,  # 后续 Task 5 会替换为 LLM 摘要
        metadata=ChunkMetadata(
            source=parent_section.source,
            source_title=source_title,
            section_path=section_path,
            page_numbers=parent_section.page_numbers,
            page_file_index=parent_section.page_file_index,
            clause_ids=_extract_special_clause_ids(special_node),
            element_type=element_type,
            cross_refs=special_node.cross_refs,
            ref_labels=list(special_node.cross_refs),
            ref_object_ids=_build_ref_object_ids(parent_section.source, special_node.cross_refs),
            parent_text_chunk_id=parent_text_chunk_id,
            bbox=bbox,
            bbox_page_idx=bbox_page_idx,
            **_build_special_object_fields(
                parent_section.source,
                special_node,
                element_type,
                parent_section.content,
                same_type_index=same_type_index,
            ),
        ),
    )


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

def _make_chunk_id(
    source: str,
    node_identity: tuple[int, ...],
    role: str,
    content: str,
    extra_parts: tuple[str, ...] = (),
) -> str:
    normalized_content = _normalize_for_hash(content)
    content_hash = hashlib.sha256(
        normalized_content.encode("utf-8")
    ).hexdigest()
    identity = ".".join(str(part) for part in node_identity) or "root"
    raw = "|".join([source, identity, role, *extra_parts, content_hash])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def _normalize_for_hash(text: str) -> str:
    """Normalize content before hashing to reduce whitespace-only churn."""
    return re.sub(r"\s+", " ", text).strip()


def _estimate_tokens(text: str) -> int:
    """粗略估算 token 数（中英混合文本，约 2 字符 = 1 token）。"""
    return len(text) // 2


def _truncate_by_tokens(text: str, max_tokens: int) -> str:
    """按 token 估算截断文本。"""
    max_chars = max_tokens * 2
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "…"


def _split_by_tokens_hard(text: str, max_tokens: int) -> list[str]:
    """无任何分隔符可用时按字符硬切；保证每片 ``_estimate_tokens(piece) <= max_tokens``。

    对应 ``_estimate_tokens`` 的 2 字符 = 1 token 假设：每片最多 ``max_tokens * 2`` 字符。
    """
    max_chars = max_tokens * 2
    if len(text) <= max_chars:
        return [text]
    return [text[i : i + max_chars] for i in range(0, len(text), max_chars)]


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


def _extract_special_clause_ids(special_node: DocumentNode) -> list[str]:
    """Extract stable clause-like identifiers for special elements."""
    if special_node.element_type != StructElementType.TABLE:
        return []

    match = re.search(r"\b(Table\s+[A-Z]?\d+(?:\.\d+)*)\b", special_node.title)
    if match:
        return [match.group(1)]
    return []


def _build_clause_object_fields(source: str, title: str) -> dict[str, object]:
    normalized_title = normalize_reference_label(title)
    ref_type = classify_reference_label(normalized_title)
    if ref_type and ref_type != "clause":
        return {}

    clause_key = extract_clause_key(title)
    if not clause_key:
        return {}

    aliases = [clause_key, f"Clause {clause_key}", f"Section {clause_key}"]
    raw_title = title.strip()
    if raw_title and raw_title not in aliases:
        aliases.append(raw_title)

    return {
        "object_type": "clause",
        "object_label": clause_key,
        "object_id": build_object_id(source, "clause", clause_key),
        "object_aliases": aliases,
    }


def _build_special_object_fields(
    source: str,
    special_node: DocumentNode,
    element_type: ChunkElementType,
    parent_content: str,
    same_type_index: int = 0,
) -> dict[str, object]:
    label = ""
    object_type: str | None = None

    if element_type == ChunkElementType.TABLE:
        label = _extract_special_clause_ids(special_node)[0] if _extract_special_clause_ids(special_node) else ""
        object_type = "table" if label else None
    elif element_type == ChunkElementType.IMAGE:
        labels = re.findall(r"\bFigure\s+[A-Z]?\d+(?:\.\d+)*\b", parent_content, re.IGNORECASE)
        if same_type_index < len(labels):
            label = labels[same_type_index]
            object_type = "figure"
        else:
            match = re.search(r"\b(Figure\s+[A-Z]?\d+(?:\.\d+)*)\b", special_node.title, re.IGNORECASE)
            if match:
                label = match.group(1)
                object_type = "figure"
    elif element_type == ChunkElementType.FORMULA:
        labels = re.findall(
            r"\bExpression\s*\(\s*\d+(?:\.\d+)*\s*\)",
            parent_content,
            re.IGNORECASE,
        )
        if same_type_index < len(labels):
            label = re.sub(r"\s+", " ", labels[same_type_index]).replace("( ", "(").replace(" )", ")")
            object_type = "expression"
        else:
            match = re.search(r"\b(Expression\s*\(\s*\d+(?:\.\d+)*\s*\))\b", special_node.title, re.IGNORECASE)
            if match:
                label = re.sub(r"\s+", " ", match.group(1)).replace("( ", "(").replace(" )", ")")
                object_type = "expression"

    if not label or object_type is None:
        return {}

    aliases = [label]
    normalized_title = special_node.title.strip()
    if normalized_title and normalized_title not in aliases:
        aliases.append(normalized_title)

    return {
        "object_type": object_type,
        "object_label": label,
        "object_id": build_object_id(source, object_type, label),
        "object_aliases": aliases,
    }


def _build_ref_object_ids(source: str, refs: list[str]) -> list[str]:
    object_ids: list[str] = []
    seen: set[str] = set()

    for ref in refs:
        object_type = classify_reference_label(ref)
        if object_type is None:
            continue
        object_id = build_object_id(source, object_type, ref)
        if object_id not in seen:
            seen.add(object_id)
            object_ids.append(object_id)

    return object_ids
