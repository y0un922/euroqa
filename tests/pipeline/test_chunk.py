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
