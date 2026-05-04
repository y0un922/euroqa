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

    def test_separator_tokens_count_toward_budget(self):
        from pipeline.chunk import _greedy_merge
        parts = ["a"] * 2000
        out = _greedy_merge(parts, sep=". ", target_tokens=600)
        assert len(out) > 1
        assert all(len(piece) // 2 <= 600 for piece in out)


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

    def test_many_tiny_sentences_do_not_recurse_forever(self):
        from pipeline.chunk import _recursive_split
        text = ". ".join(["a"] * 2000)
        pieces = _recursive_split(text)
        assert len(pieces) >= 2
        assert all(len(p) // 2 <= 800 for p in pieces)

    def test_no_separators_falls_back_to_hard_split(self):
        from pipeline.chunk import _recursive_split
        from structlog.testing import capture_logs
        text = "x" * 4000   # 2000 tokens, NO whitespace anywhere
        with capture_logs() as captured:
            pieces = _recursive_split(text)
        assert len(pieces) >= 2
        for p in pieces:
            assert len(p) <= 1600
        # Hard-split warning was emitted
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
