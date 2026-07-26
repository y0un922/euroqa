"""Context reconstruction must follow server ref_labels, not category order."""

from eval_methodology.mvp.runner.client import (
    _chunk_contents_from_retrieval_context,
    _chunk_ids_from_retrieval_context,
)


def _ctx(**overrides):
    base = {
        "chunks": [
            {"chunk_id": "b", "content": "chunk b"},
            {"chunk_id": "c", "content": "chunk c"},
        ],
        "parent_chunks": [{"chunk_id": "a", "content": "parent a"}],
    }
    base.update(overrides)
    return base


def test_orders_by_ref_labels_when_present():
    ctx = _ctx(ref_labels={"a": "Ref-1", "b": "Ref-2", "c": "Ref-3"})
    assert _chunk_ids_from_retrieval_context(ctx) == ["a", "b", "c"]
    contents = _chunk_contents_from_retrieval_context(ctx)
    assert [c["chunk_id"] for c in contents] == ["a", "b", "c"]
    assert contents[0]["content"] == "parent a"


def test_unlabeled_chunks_follow_labeled_in_category_order():
    ctx = _ctx(ref_labels={"a": "Ref-1", "c": "Ref-2"})
    assert _chunk_ids_from_retrieval_context(ctx) == ["a", "c", "b"]


def test_accepts_camel_case_ref_labels():
    ctx = _ctx(refLabels={"c": "Ref-1", "a": "Ref-2", "b": "Ref-3"})
    assert _chunk_ids_from_retrieval_context(ctx) == ["c", "a", "b"]


def test_falls_back_to_category_order_without_ref_labels():
    assert _chunk_ids_from_retrieval_context(_ctx()) == ["b", "c", "a"]


def test_dedupes_across_categories_before_ordering():
    ctx = _ctx(
        parent_chunks=[
            {"chunk_id": "a", "content": "parent a"},
            {"chunk_id": "b", "content": "dup of b"},
        ],
        ref_labels={"a": "Ref-1", "b": "Ref-2", "c": "Ref-3"},
    )
    assert _chunk_ids_from_retrieval_context(ctx) == ["a", "b", "c"]
