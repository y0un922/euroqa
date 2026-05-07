"""Tests for document outline construction used by contextual retrieval."""
from __future__ import annotations

import pytest
from structlog.testing import capture_logs

from pipeline.contextualizer import build_outline_from_tree
from pipeline.structure import DocumentNode
from pipeline.structure import ElementType as StructElementType


def _section(title: str, content: str = "", children: list[DocumentNode] | None = None) -> DocumentNode:
    return DocumentNode(
        title=title,
        content=content,
        element_type=StructElementType.SECTION,
        children=children or [],
        source="EN 1992-1-1:2004",
    )


def test_single_root_plus_two_sections():
    tree = _section(
        "root",
        children=[
            _section("1 General", "Scope paragraph.\n\nSecond paragraph."),
            _section("2 Basis of design", "Design paragraph."),
        ],
    )

    outline = build_outline_from_tree(tree)

    assert outline == (
        "1 General\n"
        "  Scope paragraph.\n"
        "2 Basis of design\n"
        "  Design paragraph."
    )


def test_multilevel_tree_four_levels_deep():
    tree = _section(
        "root",
        children=[
            _section(
                "1 General",
                "Top paragraph.",
                children=[
                    _section(
                        "1.1 Scope",
                        "Scope paragraph.",
                        children=[
                            _section(
                                "1.1.1 Eurocode 2 scope",
                                "Detail paragraph.",
                                children=[
                                    _section("1.1.1.1 Design assumptions", "Assumption paragraph."),
                                ],
                            )
                        ],
                    )
                ],
            )
        ],
    )

    outline = build_outline_from_tree(tree)

    assert "1 General" in outline
    assert "  1.1 Scope" in outline
    assert "    1.1.1 Eurocode 2 scope" in outline
    assert "      1.1.1.1 Design assumptions" in outline


def test_empty_tree_returns_empty_string():
    tree = _section("root")

    assert build_outline_from_tree(tree) == ""


def test_large_outline_falls_back_to_titles_only():
    huge = "x " * 120
    tree = _section(
        "root",
        children=[_section(f"{idx} Section", huge) for idx in range(1000)],
    )

    with capture_logs() as logs:
        outline = build_outline_from_tree(tree)

    assert outline.splitlines()[:2] == ["0 Section", "1 Section"]
    assert any(log["event"] == "outline_fallback_titles_only" for log in logs)


def test_long_paragraph_estimate_uses_truncated_excerpt():
    huge = "x " * 120000
    tree = _section("root", children=[_section("1 General", huge)])

    with capture_logs() as logs:
        outline = build_outline_from_tree(tree)

    assert outline.startswith("1 General\n  ")
    assert outline.endswith("…")
    assert not any(log["event"] == "outline_fallback_titles_only" for log in logs)


@pytest.mark.parametrize(
    ("paragraph", "expected"),
    [
        ("x" * 199, "1 General\n  " + ("x" * 199)),
        ("x" * 200, "1 General\n  " + ("x" * 200) + "…"),
    ],
)
def test_first_para_max_chars_boundary(paragraph: str, expected: str):
    tree = _section("root", children=[_section("1 General", paragraph)])

    assert build_outline_from_tree(tree, first_para_max_chars=200) == expected
