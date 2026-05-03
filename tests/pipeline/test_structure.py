"""Test Markdown -> structured document tree."""
import pytest
from pipeline.content_list import resolve_section_page_metadata
from pipeline.structure import (
    DocumentNode,
    ElementType,
    TreePruningConfig,
    extract_cross_refs,
    parse_markdown_to_tree,
    prune_document_tree,
)


class TestParseMarkdownToTree:
    def test_basic_section_hierarchy(self):
        md = (
            "# Section 1 General\n\n"
            "## 1.1 Scope\n\n"
            "(1) EN 1990 establishes Principles and requirements.\n\n"
            "(2) EN 1990 is intended to be used in conjunction.\n\n"
            "## 1.2 Normative references\n\n"
            "This European Standard incorporates...\n"
        )
        tree = parse_markdown_to_tree(md, source="EN 1990:2002")
        assert len(tree.children) == 1
        section = tree.children[0]
        assert "Section 1" in section.title
        assert len(section.children) == 2
        assert "1.1" in section.children[0].title
        assert "1.2" in section.children[1].title

    def test_table_detection(self):
        md = (
            "## 2.3 Design working life\n\n"
            "(1) The design working life should be specified.\n\n"
            "| Category | Years | Examples |\n"
            "|---|---|---|\n"
            "|1|10|Temporary|\n"
            "|5|100|Bridges|\n"
        )
        tree = parse_markdown_to_tree(md, source="EN 1990:2002")
        subsection = tree.children[0]
        tables = [c for c in subsection.children if c.element_type == ElementType.TABLE]
        assert len(tables) == 1

    def test_html_table_detection_preserves_caption_and_removes_html_from_text(self):
        md = (
            "## 2.3 Design working life\n\n"
            "(1) The design working life should be specified.\n\n"
            "NOTE Indicative categories are given in Table 2.1.\n\n"
            "Table 2.1 - Indicative design working life\n\n"
            "<table><tr><td>1</td><td>10</td><td>Temporary structures</td></tr></table>\n"
        )
        tree = parse_markdown_to_tree(md, source="EN 1990:2002")

        subsection = tree.children[0]
        tables = [c for c in subsection.children if c.element_type == ElementType.TABLE]

        assert len(tables) == 1
        assert "NOTE Indicative categories are given in Table 2.1." in subsection.content
        assert "<table>" not in subsection.content
        assert tables[0].title == "Table 2.1 - Indicative design working life"
        assert tables[0].content.startswith("Table 2.1 - Indicative design working life")
        assert "<table>" in tables[0].content

    def test_formula_detection(self):
        md = (
            "## 6.3.5 Design resistance\n\n"
            "(1) The design resistance Rd:\n\n"
            "$$R_d = \\frac{1}{\\gamma_{Rd}} R\\{X_{d,i}; a_d\\}$$\n\n"
            "where:\n\n"
            "- $\\gamma_{Rd}$ is a partial factor\n"
            "- $X_{d,i}$ is the design value\n"
        )
        tree = parse_markdown_to_tree(md, source="EN 1990:2002")
        subsection = tree.children[0]
        formulas = [c for c in subsection.children if c.element_type == ElementType.FORMULA]
        assert len(formulas) == 1
        assert "gamma_{Rd}" in formulas[0].content

    def test_image_detection(self):
        md = (
            "## 3.1 Overview\n\n"
            "![Figure 3.1](images/figure_3_1.png)\n\n"
            "Some text after image.\n"
        )
        tree = parse_markdown_to_tree(md, source="EN 1990:2002")
        images = [c for c in tree.children[0].children if c.element_type == ElementType.IMAGE]
        assert len(images) == 1

    def test_assigns_page_metadata_from_content_list(self):
        md = (
            "# Section 2 Requirements\n\n"
            "## 2.3 Design working life\n\n"
            "(1) The design working life should be specified.\n\n"
            "(2)P Indicative categories are given in Table 2.1.\n"
        )
        content_list = [
            {"type": "text", "text": "Section 2 Requirements", "text_level": 1, "page_idx": 4},
            {"type": "text", "text": "2.3 Design working life", "text_level": 2, "page_idx": 5},
            {
                "type": "text",
                "text": "(1) The design working life should be specified.",
                "text_level": 0,
                "page_idx": 5,
            },
            {
                "type": "text",
                "text": "(2)P Indicative categories are given in Table 2.1.",
                "text_level": 0,
                "page_idx": 6,
            },
        ]

        tree = parse_markdown_to_tree(
            md,
            source="EN 1990:2002",
            content_list=content_list,
        )

        section = tree.children[0]
        subsection = section.children[0]
        assert section.page_numbers == [5, 6, 7]
        assert section.page_file_index == [4, 5, 6]
        assert subsection.page_numbers == [6, 7]
        assert subsection.page_file_index == [5, 6]


class TestPruneDocumentTree:
    """文档树清洗测试。"""

    def test_removes_prefix_before_foreword(self):
        """封面、目录、法国前言等应在 Foreword 之前被裁剪。"""
        md = (
            "# NF EN 1990\n\n"
            "Cover page content.\n\n"
            "# A.P. 1: Introduction\n\n"
            "French national foreword.\n\n"
            "# FOREWORD...\n\n"
            "BACKGROUND OF THE EUROCODE PROGRAMME ... 5\n"
            "SECTION 1 GENERAL .. 9\n\n"
            "# Foreword\n\n"
            "Real foreword paragraph.\n\n"
            "# Section 1 General\n\n"
            "Actual section body.\n"
        )
        tree = parse_markdown_to_tree(md, source="EN 1990:2002")
        pruned = prune_document_tree(tree)
        titles = [n.title for n in pruned.children]
        assert titles == ["Foreword", "Section 1 General"]
        assert pruned.children[0].content == "Real foreword paragraph."

    def test_cleans_page_numbers_from_titles(self):
        """标题中的 dot-leader + 页码应被清洗。"""
        md = (
            "# Foreword\n\n"
            "Content.\n\n"
            "# SECTION 1 GENERAL .. 0\n\n"
            "Body text.\n\n"
            "# SECTION 2 REQUIREMENTS ... . 23\n\n"
            "More body.\n"
        )
        tree = parse_markdown_to_tree(md, source="EN 1990:2002")
        pruned = prune_document_tree(tree)
        titles = [n.title for n in pruned.children]
        assert titles == ["Foreword", "SECTION 1 GENERAL", "SECTION 2 REQUIREMENTS"]

    def test_removes_empty_sections(self):
        """空内容且标题在 removable 列表中的节点应被删除。"""
        md = (
            "# Foreword\n\n"
            "Content.\n\n"
            "# Modifications\n\n"
            "# Corrections\n\n"
            "# Section 1\n\n"
            "Body.\n"
        )
        tree = parse_markdown_to_tree(md, source="EN 1990:2002")
        pruned = prune_document_tree(tree)
        titles = [n.title for n in pruned.children]
        assert "Modifications" not in titles
        assert "Corrections" not in titles
        assert "Foreword" in titles
        assert "Section 1" in titles

    def test_merges_running_headers(self):
        """页眉节点（如 EN 1990:2002 (E)）应合并到前一个 section。"""
        md = (
            "# Foreword\n\n"
            "Paragraph A.\n\n"
            "# EN 1990:2002 (E)\n\n"
            "Paragraph B.\n\n"
            "# Section 1 General\n\n"
            "Paragraph C.\n"
        )
        tree = parse_markdown_to_tree(md, source="EN 1990:2002")
        pruned = prune_document_tree(tree)
        titles = [n.title for n in pruned.children]
        assert titles == ["Foreword", "Section 1 General"]
        # 页眉内容合并到 Foreword
        assert "Paragraph A." in pruned.children[0].content
        assert "Paragraph B." in pruned.children[0].content

    def test_preserves_all_when_no_foreword(self):
        """找不到 Foreword 起点时，保守保留所有节点。"""
        md = (
            "# NF EN 1990\n\n"
            "Cover.\n\n"
            "# Section 1 General\n\n"
            "Body.\n"
        )
        tree = parse_markdown_to_tree(md, source="EN 1990:2002")
        pruned = prune_document_tree(tree)
        # 未裁剪前缀，但标题仍会被清洗
        assert len(pruned.children) == 2

    def test_disabled_pruning_returns_copy(self):
        """禁用清洗时返回未修改的深拷贝。"""
        md = "# Cover\n\nNoise.\n\n# Foreword\n\nReal.\n"
        tree = parse_markdown_to_tree(md, source="test")
        cfg = TreePruningConfig(enabled=False)
        pruned = prune_document_tree(tree, cfg)
        assert len(pruned.children) == len(tree.children)
        # 确认是深拷贝
        assert pruned is not tree

    def test_skips_toc_foreword_entry(self):
        """目录中的 FOREWORD 标题（带页码）不应被当作正文起点。"""
        md = (
            "# FOREWORD...\n\n"
            "BACKGROUND ... 5\nSTATUS ... 6\nSECTION 1 GENERAL .. 9\n\n"
            "# Foreword\n\n"
            "Actual foreword content.\n"
        )
        tree = parse_markdown_to_tree(md, source="EN 1990:2002")
        pruned = prune_document_tree(tree)
        # 应跳过 TOC 中的 FOREWORD，从真正的 Foreword 开始
        assert len(pruned.children) == 1
        assert pruned.children[0].title == "Foreword"
        assert "Actual foreword content." in pruned.children[0].content


class TestContentListBbox:
    """Tests for bbox extraction via ContentListEntry and resolve_section_page_metadata."""

    def test_prefers_body_text_bbox_over_heading(self):
        """当 section 有 body text entry 时，返回 body entry 的 bbox 而非 heading 的。"""
        segments = [(2, "Design working life", "body text")]
        raw = [
            {
                "type": "text",
                "text": "Design working life",
                "page_idx": 27,
                "text_level": 2,
                "bbox": [139, 451, 374, 471],  # heading bbox
            },
            {
                "type": "text",
                "text": "(1) The design working life should be specified.",
                "page_idx": 27,
                "text_level": 0,
                "bbox": [139, 488, 529, 504],  # body text bbox
            },
        ]
        results = resolve_section_page_metadata(segments, raw)
        _, _, bbox, bbox_page_idx = results[0]
        # 应返回 body text bbox，不是 heading bbox
        assert bbox == [139.0, 488.0, 529.0, 504.0]
        assert bbox_page_idx == 27

    def test_falls_back_to_heading_when_no_body_entries(self):
        """当 section 只有 heading 没有 body text 时，返回 heading 的 bbox。"""
        segments = [(2, "Design working life", "body text")]
        raw = [
            {
                "type": "text",
                "text": "Design working life",
                "page_idx": 27,
                "text_level": 2,
                "bbox": [186, 362, 858, 420],
            }
        ]
        results = resolve_section_page_metadata(segments, raw)
        _, _, bbox, bbox_page_idx = results[0]
        assert bbox == [186.0, 362.0, 858.0, 420.0]
        assert bbox_page_idx == 27

    def test_rejects_invalid_bbox_via_resolve(self):
        segments = [(2, "Hello", "body")]
        raw = [
            {
                "type": "text",
                "text": "Hello",
                "page_idx": 0,
                "text_level": 2,
                "bbox": [100, 200],  # 只有2个值，无效
            }
        ]
        results = resolve_section_page_metadata(segments, raw)
        _, _, bbox, _ = results[0]
        assert bbox == []

    def test_rejects_out_of_range_bbox(self):
        segments = [(2, "Hello", "body")]
        raw = [
            {
                "type": "text",
                "text": "Hello",
                "page_idx": 0,
                "text_level": 2,
                "bbox": [100, 200, 1500, 400],  # 1500 超出0-1000范围
            }
        ]
        results = resolve_section_page_metadata(segments, raw)
        _, _, bbox, _ = results[0]
        assert bbox == []

    def test_unmatched_heading_returns_sentinel(self):
        segments = [(2, "Nonexistent Heading", "body")]
        raw = [
            {
                "type": "text",
                "text": "Different Heading",
                "page_idx": 5,
                "text_level": 2,
                "bbox": [0, 0, 100, 50],
            }
        ]
        results = resolve_section_page_metadata(segments, raw)
        page_numbers, page_file_indexes, bbox, bbox_page_idx = results[0]
        assert page_numbers == []
        assert page_file_indexes == []
        assert bbox == []
        assert bbox_page_idx == -1

    def test_empty_content_list_returns_sentinels(self):
        segments = [(1, "Section 1", "body")]
        results = resolve_section_page_metadata(segments, [])
        page_numbers, page_file_indexes, bbox, bbox_page_idx = results[0]
        assert page_numbers == []
        assert page_file_indexes == []
        assert bbox == []
        assert bbox_page_idx == -1

    def test_missing_bbox_field_returns_empty(self):
        """Entries without a bbox key should yield empty bbox."""
        segments = [(1, "Section A", "body")]
        raw = [
            {
                "type": "text",
                "text": "Section A",
                "page_idx": 3,
                "text_level": 1,
                # bbox キーなし
            }
        ]
        results = resolve_section_page_metadata(segments, raw)
        _, _, bbox, bbox_page_idx = results[0]
        assert bbox == []
        assert bbox_page_idx == 3

    def test_bbox_values_coerced_to_float(self):
        """Integer bbox values should be returned as floats."""
        segments = [(1, "Intro", "text")]
        raw = [
            {
                "type": "text",
                "text": "Intro",
                "page_idx": 0,
                "text_level": 1,
                "bbox": [0, 0, 500, 100],
            }
        ]
        results = resolve_section_page_metadata(segments, raw)
        _, _, bbox, _ = results[0]
        assert bbox == [0.0, 0.0, 500.0, 100.0]
        assert all(isinstance(v, float) for v in bbox)


class TestDocumentNodeBbox:
    def test_section_node_receives_bbox_from_content_list(self):
        md = "## 2.3 Design working life\n\n(1) The design working life should be specified.\n"
        content_list = [
            {"type": "text", "text": "2.3 Design working life",
             "page_idx": 27, "text_level": 2, "bbox": [186, 362, 858, 420]},
            {"type": "text", "text": "The design working life should be specified.",
             "page_idx": 27, "text_level": 0, "bbox": [186, 430, 858, 470]},
        ]
        tree = parse_markdown_to_tree(md, source="EN 1990:2002", content_list=content_list)
        section = tree.children[0]
        # 应返回 body text entry 的 bbox，不是 heading 的
        assert section.bbox == [186.0, 430.0, 858.0, 470.0]
        assert section.bbox_page_idx == 27

    def test_section_without_content_list_has_empty_bbox(self):
        md = "## 2.3 Design working life\n\n(1) Specified.\n"
        tree = parse_markdown_to_tree(md, source="EN 1990:2002")
        section = tree.children[0]
        assert section.bbox == []
        assert section.bbox_page_idx == -1


class TestExtractCrossRefs:
    def test_extract_en_references(self):
        text = "See also EN 1991-1-2 and EN 1992 for details."
        refs = extract_cross_refs(text)
        assert "EN 1991-1-2" in refs
        assert "EN 1992" in refs

    def test_extract_annex_references(self):
        text = "See Annex A and Annex B3 for more."
        refs = extract_cross_refs(text)
        assert "Annex A" in refs
        assert "Annex B3" in refs

    def test_no_refs(self):
        text = "A simple paragraph with no references."
        refs = extract_cross_refs(text)
        assert refs == []

    def test_extract_internal_object_references(self):
        text = (
            "See Table 3.1, Figure 3.3 and Expression (3.14). "
            "The stress-strain relation defined in 3.1.7 may be used."
        )
        refs = extract_cross_refs(text)
        assert "Table 3.1" in refs
        assert "Figure 3.3" in refs
        assert "Expression (3.14)" in refs
        assert "3.1.7" in refs


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
