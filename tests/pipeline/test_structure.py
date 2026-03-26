"""Test Markdown -> structured document tree."""
import pytest
from pipeline.structure import DocumentNode, ElementType, parse_markdown_to_tree, extract_cross_refs


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
