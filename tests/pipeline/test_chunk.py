"""Test mixed chunking strategy."""
import pytest
from pipeline.chunk import create_chunks
from pipeline.structure import parse_markdown_to_tree
from server.models.schemas import ElementType as ChunkElementType


class TestCreateChunks:
    def _make_tree(self, md: str) -> "DocumentNode":
        from pipeline.structure import DocumentNode
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

    def test_formula_independent_chunk(self):
        md = (
            "## 6.3 Design values\n\n"
            "(1) The design resistance:\n\n"
            "$$R_d = \\frac{1}{\\gamma_{Rd}} R\\{X_{d,i}\\}$$\n\n"
            "where:\n\n"
            "- $\\gamma_{Rd}$ is a partial factor\n"
        )
        tree = self._make_tree(md)
        chunks = create_chunks(tree, source_title="Basis of structural design")
        formula_chunks = [c for c in chunks if c.metadata.element_type == ChunkElementType.FORMULA]
        assert len(formula_chunks) == 1
        assert "gamma_{Rd}" in formula_chunks[0].content

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
