"""Test mixed chunking strategy."""
import pytest
from pipeline.chunk import create_chunks
from pipeline.chunk import validate_unique_chunk_ids
from pipeline.structure import DocumentNode
from pipeline.structure import ElementType as StructElementType
from pipeline.structure import parse_markdown_to_tree
from server.models.schemas import ElementType as ChunkElementType


class TestCreateChunks:
    def _make_tree(self, md: str) -> "DocumentNode":
        return parse_markdown_to_tree(md, source="EN 1990:2002")

    def test_text_parent_child_chunks(self):
        md = (
            "# Section 2 Requirements\n\n"
            "## 2.1 Basic requirements\n\n"
            "(1)P A structure shall be designed and executed.\n\n"
            "(2)P A structure shall have adequate resistance.\n\n"
            "## 2.3 Design working life\n\n"
            "(1) The design working life should be specified.\n"
        )
        tree = self._make_tree(md)
        chunks = create_chunks(tree, source_title="Basis of structural design")
        children = [c for c in chunks if c.metadata.parent_chunk_id is not None]
        parents = [c for c in chunks if c.metadata.element_type == ChunkElementType.TEXT
                   and c.metadata.parent_chunk_id is None
                   and any("Section" in p for p in c.metadata.section_path)]
        assert len(children) >= 2
        assert len(parents) >= 1

    def test_table_independent_chunk(self):
        md = (
            "## 2.3 Design working life\n\n"
            "(1) The design working life should be specified.\n\n"
            "| Category | Years | Examples |\n"
            "|---|---|---|\n"
            "|1|10|Temporary|\n"
        )
        tree = self._make_tree(md)
        chunks = create_chunks(tree, source_title="Basis of structural design")
        table_chunks = [c for c in chunks if c.metadata.element_type == ChunkElementType.TABLE]
        assert len(table_chunks) == 1
        assert table_chunks[0].metadata.parent_text_chunk_id is not None

    def test_html_table_independent_chunk_uses_caption_as_clause(self):
        md = (
            "## 2.3 Design working life\n\n"
            "(1) The design working life should be specified.\n\n"
            "Table 2.1 - Indicative design working life\n\n"
            "<table><tr><td>1</td><td>10</td><td>Temporary structures</td></tr></table>\n"
        )
        tree = self._make_tree(md)
        chunks = create_chunks(tree, source_title="Basis of structural design")

        text_chunk = next(c for c in chunks if c.metadata.element_type == ChunkElementType.TEXT)
        table_chunk = next(
            c for c in chunks if c.metadata.element_type == ChunkElementType.TABLE
        )

        assert "[-> Table]" in text_chunk.content
        assert "<table>" not in text_chunk.content
        assert table_chunk.metadata.parent_text_chunk_id == text_chunk.chunk_id
        assert table_chunk.metadata.clause_ids == ["Table 2.1"]
        assert table_chunk.content.startswith("Table 2.1 - Indicative design working life")
        assert table_chunk.metadata.object_type == "table"
        assert table_chunk.metadata.object_label == "Table 2.1"
        assert table_chunk.metadata.object_id
        assert "Table 2.1" in table_chunk.metadata.object_aliases

    def test_formula_independent_chunk(self):
        md = (
            "## 6.3 Design values\n\n"
            "(1) The design resistance:\n\n"
            "Expression (3.14)\n\n"
            "$$R_d = \\frac{1}{\\gamma_{Rd}} R\\{X_{d,i}\\}$$\n\n"
            "where:\n\n"
            "- $\\gamma_{Rd}$ is a partial factor\n"
        )
        tree = self._make_tree(md)
        chunks = create_chunks(tree, source_title="Basis of structural design")
        formula_chunks = [c for c in chunks if c.metadata.element_type == ChunkElementType.FORMULA]
        assert len(formula_chunks) == 1
        assert "gamma_{Rd}" in formula_chunks[0].content
        assert formula_chunks[0].metadata.object_type == "expression"
        assert formula_chunks[0].metadata.object_label == "Expression (3.14)"
        assert formula_chunks[0].metadata.object_id.endswith("#expression:3.14")

    def test_image_chunk_can_infer_figure_object_metadata(self):
        md = (
            "## 3.1.7 Stress-strain relations for the design of cross-sections\n\n"
            "(1) For the design of cross-sections, the following stress-strain relationship may be used.\n\n"
            "Figure 3.3: Parabola-rectangle diagram for concrete under compression.\n"
            "![Figure 3.3](images/figure-3-3.png)\n"
        )
        tree = self._make_tree(md)
        chunks = create_chunks(tree, source_title="Concrete structures")
        image_chunk = next(
            c for c in chunks if c.metadata.element_type == ChunkElementType.IMAGE
        )

        assert image_chunk.metadata.object_type == "figure"
        assert image_chunk.metadata.object_label == "Figure 3.3"
        assert image_chunk.metadata.object_id.endswith("#figure:3.3")

    def test_clause_chunk_gets_object_metadata_and_ref_object_ids(self):
        md = (
            "## 3.1.7 Stress-strain relations for the design of cross-sections\n\n"
            "(1) For the design of cross-sections, the following stress-strain relationship may be used, "
            "see Figure 3.3.\n\n"
            "where:\n\n"
            "n is the exponent according to Table 3.1.\n"
            "The relation defined in 3.1.6 may also be considered.\n"
        )
        tree = self._make_tree(md)
        chunks = create_chunks(tree, source_title="Concrete structures")
        text_chunk = next(
            c for c in chunks if c.metadata.element_type == ChunkElementType.TEXT
        )

        assert text_chunk.metadata.object_type == "clause"
        assert text_chunk.metadata.object_label == "3.1.7"
        assert text_chunk.metadata.object_id
        assert "3.1.7" in text_chunk.metadata.object_aliases
        assert "Clause 3.1.7" in text_chunk.metadata.object_aliases
        assert "Table 3.1" in text_chunk.metadata.ref_labels
        assert "Figure 3.3" in text_chunk.metadata.ref_labels
        assert "3.1.6" in text_chunk.metadata.ref_labels
        assert any(ref.endswith("#table:3.1") for ref in text_chunk.metadata.ref_object_ids)
        assert any(ref.endswith("#clause:3.1.6") for ref in text_chunk.metadata.ref_object_ids)

    def test_table_like_section_title_does_not_emit_clause_object_metadata(self):
        root = DocumentNode(title="root", source="EN 1992-1-1:2004")
        root.children.append(
            DocumentNode(
                title="Table 6.1: Coefficients for rectangular sections",
                content="Values for rectangular sections are given here.",
                source="EN 1992-1-1:2004",
                element_type=StructElementType.SECTION,
            )
        )

        chunks = create_chunks(root, source_title="Concrete structures")
        text_chunk = next(
            c for c in chunks if c.metadata.element_type == ChunkElementType.TEXT
        )

        assert text_chunk.metadata.object_type is None
        assert text_chunk.metadata.object_label == ""
        assert text_chunk.metadata.object_id == ""
        assert text_chunk.metadata.object_aliases == []

    def test_metadata_completeness(self):
        md = (
            "# Section 2 Requirements\n\n"
            "## 2.1 Basic requirements\n\n"
            "(1) A structure shall be designed. See also EN 1991-1-2.\n"
        )
        tree = self._make_tree(md)
        chunks = create_chunks(tree, source_title="Basis of structural design")
        child = [c for c in chunks if any("2.1" in p for p in c.metadata.section_path)]
        assert len(child) >= 1
        meta = child[0].metadata
        assert meta.source == "EN 1990:2002"
        assert meta.source_title == "Basis of structural design"
        assert len(meta.section_path) >= 2
        assert "EN 1991-1-2" in meta.cross_refs

    def test_propagates_page_indexes_from_tree_metadata(self):
        md = (
            "# Section 2 Requirements\n\n"
            "## 2.3 Design working life\n\n"
            "(1) The design working life should be specified.\n"
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
        ]

        tree = parse_markdown_to_tree(
            md,
            source="EN 1990:2002",
            content_list=content_list,
        )
        chunks = create_chunks(tree, source_title="Basis of structural design")

        child = next(
            c
            for c in chunks
            if c.metadata.parent_chunk_id is not None and "2.3" in c.metadata.section_path[-1]
        )
        parent = next(
            c
            for c in chunks
            if c.metadata.parent_chunk_id is None and c.metadata.section_path == ["Section 2 Requirements"]
        )

        assert child.metadata.page_numbers == [6]
        assert child.metadata.page_file_index == [5]
        assert parent.metadata.page_numbers == [6]
        assert parent.metadata.page_file_index == [5]


class TestChunkBboxInheritance:
    """Tests for bbox propagation from DocumentNode to ChunkMetadata."""

    def test_child_text_chunk_inherits_section_bbox(self):
        md = "## 2.3 Design working life\n\n(1) The design working life.\n"
        tree = parse_markdown_to_tree(md, source="EN 1990:2002")
        tree.children[0].bbox = [186, 362, 858, 420]
        tree.children[0].bbox_page_idx = 27
        chunks = create_chunks(tree, source_title="Basis")
        text_chunks = [c for c in chunks if c.metadata.element_type == ChunkElementType.TEXT]
        assert len(text_chunks) >= 1
        assert text_chunks[0].metadata.bbox == [186, 362, 858, 420]
        assert text_chunks[0].metadata.bbox_page_idx == 27

    def test_special_chunk_inherits_parent_section_bbox(self):
        md = (
            "## 2.3 Design working life\n\n"
            "(1) Specified.\n\n"
            "| Cat | Years |\n|---|---|\n|1|10|\n"
        )
        tree = parse_markdown_to_tree(md, source="EN 1990:2002")
        tree.children[0].bbox = [186, 362, 858, 420]
        tree.children[0].bbox_page_idx = 27
        chunks = create_chunks(tree, source_title="Basis")
        table_chunks = [c for c in chunks if c.metadata.element_type == ChunkElementType.TABLE]
        assert len(table_chunks) >= 1
        assert table_chunks[0].metadata.bbox == [186, 362, 858, 420]

    def test_parent_chunk_uses_first_child_bbox(self):
        md = (
            "# Section 2\n\n"
            "## 2.1 Basic\n\n(1) A structure.\n\n"
            "## 2.3 Design\n\n(1) Specified.\n"
        )
        tree = parse_markdown_to_tree(md, source="EN 1990:2002")
        tree.children[0].children[0].bbox = [100, 200, 300, 400]
        tree.children[0].children[0].bbox_page_idx = 10
        tree.children[0].children[1].bbox = [100, 500, 300, 600]
        tree.children[0].children[1].bbox_page_idx = 12
        chunks = create_chunks(tree, source_title="Basis")
        parent_chunks = [
            c for c in chunks
            if c.metadata.parent_chunk_id is None
            and c.metadata.element_type == ChunkElementType.TEXT
            and any("Section 2" in p for p in c.metadata.section_path)
            and len(c.metadata.section_path) == 1
        ]
        assert len(parent_chunks) >= 1
        assert parent_chunks[0].metadata.bbox == [100, 200, 300, 400]
        assert parent_chunks[0].metadata.bbox_page_idx == 10

    def test_chunk_without_bbox_has_defaults(self):
        md = "## 2.3 Design working life\n\n(1) Specified.\n"
        tree = parse_markdown_to_tree(md, source="EN 1990:2002")
        chunks = create_chunks(tree, source_title="Basis")
        text_chunks = [c for c in chunks if c.metadata.element_type == ChunkElementType.TEXT]
        assert text_chunks[0].metadata.bbox == []
        assert text_chunks[0].metadata.bbox_page_idx == -1


class TestChunkIdentityAndUniqueness:
    def test_non_leaf_duplicate_siblings_do_not_cross_collect_children(self):
        root = DocumentNode(title="root", source="EN 1992-1-1:2004")
        parent = DocumentNode(
            title="Section 1",
            source="EN 1992-1-1:2004",
            element_type=StructElementType.SECTION,
        )
        first_group = DocumentNode(
            title="Repeated subsection",
            source="EN 1992-1-1:2004",
            element_type=StructElementType.SECTION,
        )
        second_group = DocumentNode(
            title="Repeated subsection",
            source="EN 1992-1-1:2004",
            element_type=StructElementType.SECTION,
        )
        first_leaf = DocumentNode(
            title="Leaf",
            content="alpha only",
            source="EN 1992-1-1:2004",
            element_type=StructElementType.SECTION,
        )
        second_leaf = DocumentNode(
            title="Leaf",
            content="beta only",
            source="EN 1992-1-1:2004",
            element_type=StructElementType.SECTION,
        )
        first_group.children.append(first_leaf)
        second_group.children.append(second_leaf)
        parent.children.extend([first_group, second_group])
        root.children.append(parent)

        chunks = create_chunks(root, source_title="Concrete structures")

        repeated_parents = [
            c
            for c in chunks
            if c.metadata.element_type == ChunkElementType.TEXT
            and c.metadata.section_path == ["Section 1", "Repeated subsection"]
        ]
        assert len(repeated_parents) == 2
        assert {c.content for c in repeated_parents} == {"alpha only", "beta only"}

    def test_duplicate_leaf_sections_with_identical_content_get_distinct_ids(self):
        root = DocumentNode(title="root", source="EN 1992-1-1:2004")
        first = DocumentNode(
            title="Repeated subsection",
            content="identical content",
            source="EN 1992-1-1:2004",
            element_type=StructElementType.SECTION,
        )
        second = DocumentNode(
            title="Repeated subsection",
            content="identical content",
            source="EN 1992-1-1:2004",
            element_type=StructElementType.SECTION,
        )
        root.children.extend([first, second])

        chunks = create_chunks(root, source_title="Concrete structures")
        text_chunks = [
            c for c in chunks if c.metadata.element_type == ChunkElementType.TEXT
        ]

        assert len(text_chunks) == 2
        assert len({c.chunk_id for c in text_chunks}) == 2

    def test_duplicate_special_nodes_get_distinct_ids_and_attach_to_parent_chunk(self):
        root = DocumentNode(title="root", source="EN 1992-1-1:2004")
        parent = DocumentNode(
            title="Section with formulas",
            source="EN 1992-1-1:2004",
            element_type=StructElementType.SECTION,
        )
        child = DocumentNode(
            title="Leaf",
            content="child text",
            source="EN 1992-1-1:2004",
            element_type=StructElementType.SECTION,
        )
        parent_formula_a = DocumentNode(
            title="Eq",
            content="$$x=1$$",
            source="EN 1992-1-1:2004",
            element_type=StructElementType.FORMULA,
        )
        parent_formula_b = DocumentNode(
            title="Eq",
            content="$$x=1$$",
            source="EN 1992-1-1:2004",
            element_type=StructElementType.FORMULA,
        )
        parent.children.extend([child, parent_formula_a, parent_formula_b])
        root.children.append(parent)

        chunks = create_chunks(root, source_title="Concrete structures")

        parent_text = next(
            c
            for c in chunks
            if c.metadata.element_type == ChunkElementType.TEXT
            and c.metadata.section_path == ["Section with formulas"]
        )
        formulas = [
            c for c in chunks if c.metadata.element_type == ChunkElementType.FORMULA
        ]

        assert len(formulas) == 2
        assert len({c.chunk_id for c in formulas}) == 2
        assert {c.metadata.parent_text_chunk_id for c in formulas} == {parent_text.chunk_id}

    def test_empty_leaf_section_does_not_generate_text_chunk(self):
        root = DocumentNode(title="root", source="EN 1992-1-1:2004")
        root.children.append(
            DocumentNode(
                title="SECTION 1 GENERAL",
                content="",
                source="EN 1992-1-1:2004",
                element_type=StructElementType.SECTION,
            )
        )

        chunks = create_chunks(root, source_title="Concrete structures")

        assert chunks == []

    def test_empty_leaf_with_special_child_keeps_placeholder_text_chunk(self):
        root = DocumentNode(title="root", source="EN 1992-1-1:2004")
        leaf = DocumentNode(
            title="Figure section",
            content="",
            source="EN 1992-1-1:2004",
            element_type=StructElementType.SECTION,
        )
        leaf.children.append(
            DocumentNode(
                title="Figure 1",
                content="figure payload",
                source="EN 1992-1-1:2004",
                element_type=StructElementType.IMAGE,
            )
        )
        root.children.append(leaf)

        chunks = create_chunks(root, source_title="Concrete structures")

        text_chunk = next(
            c for c in chunks if c.metadata.element_type == ChunkElementType.TEXT
        )
        image_chunk = next(
            c for c in chunks if c.metadata.element_type == ChunkElementType.IMAGE
        )

        assert text_chunk.content == "\n[-> Image]"
        assert image_chunk.metadata.parent_text_chunk_id == text_chunk.chunk_id

    def test_validate_unique_chunk_ids_raises_on_duplicates(self):
        root = DocumentNode(title="root", source="EN 1992-1-1:2004")
        root.children.extend(
            [
                DocumentNode(
                    title="Repeated subsection",
                    content="identical content",
                    source="EN 1992-1-1:2004",
                    element_type=StructElementType.SECTION,
                ),
                DocumentNode(
                    title="Repeated subsection",
                    content="identical content",
                    source="EN 1992-1-1:2004",
                    element_type=StructElementType.SECTION,
                ),
            ]
        )
        chunks = create_chunks(root, source_title="Concrete structures")
        duplicate_chunks = chunks + [chunks[0].model_copy()]

        with pytest.raises(ValueError, match="Duplicate chunk IDs detected"):
            validate_unique_chunk_ids(duplicate_chunks)
