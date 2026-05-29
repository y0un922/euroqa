"""Characterization snapshot tests for generation-side pure helpers.

These tests intentionally snapshot current behavior instead of asserting a new
spec. If a generation helper changes, review the JSON diff and delete/update the
affected snapshot only when the behavior change is intended.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import structlog

from server.config import ServerConfig
from server.core.generation import (
    _build_prioritized_source_chunks,
    _build_retrieval_context,
    _build_sources_from_chunks,
    build_prompt,
    decide_generation_mode,
    postprocess_citations,
)
from server.models.schemas import Chunk, ElementType

logger = structlog.get_logger(__name__)

SNAPSHOT_DIR = Path(__file__).parent / "snapshots"


def _jsonable(value: Any) -> Any:
    """Convert pydantic models and enums into deterministic JSON values."""
    if hasattr(value, "model_dump"):
        return _jsonable(value.model_dump())
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in sorted(value.items())}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if hasattr(value, "value"):
        return value.value
    return value


def _assert_snapshot(name: str, payload: Any) -> None:
    """Create a snapshot on first run; compare exactly on later runs."""
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    path = SNAPSHOT_DIR / f"{name}.json"
    serialized = (
        json.dumps(_jsonable(payload), ensure_ascii=False, indent=2, sort_keys=True)
        + "\n"
    )
    if not path.exists():
        path.write_text(serialized, encoding="utf-8")
        logger.info("generation_characterization_snapshot_created", path=str(path))
        return

    assert path.read_text(encoding="utf-8") == serialized


def _variant_chunk(
    base: Chunk,
    *,
    chunk_id: str,
    content: str | None = None,
    source: str | None = None,
    source_title: str | None = None,
    section_path: list[str] | None = None,
    clause_ids: list[str] | None = None,
    page_numbers: list[int] | None = None,
    element_type: ElementType | None = None,
) -> Chunk:
    metadata_update: dict[str, Any] = {}
    if source is not None:
        metadata_update["source"] = source
    if source_title is not None:
        metadata_update["source_title"] = source_title
    if section_path is not None:
        metadata_update["section_path"] = section_path
    if clause_ids is not None:
        metadata_update["clause_ids"] = clause_ids
    if page_numbers is not None:
        metadata_update["page_numbers"] = page_numbers
        metadata_update["page_file_index"] = [page - 1 for page in page_numbers]
        metadata_update["bbox_page_idx"] = page_numbers[0] - 1 if page_numbers else -1
    if element_type is not None:
        metadata_update["element_type"] = element_type

    return base.model_copy(
        update={
            "chunk_id": chunk_id,
            "content": content if content is not None else base.content,
            "embedding_text": content if content is not None else base.embedding_text,
            "metadata": base.metadata.model_copy(update=metadata_update),
        }
    )


@pytest.mark.parametrize(
    ("case_name", "kwargs"),
    [
        (
            "basic_text_and_table",
            {
                "question": "桥梁的设计使用年限是多少？",
                "glossary_terms": {"设计使用年限": "design working life"},
                "generation_mode": "grounded",
                "resolved_refs": ["Table 2.1"],
                "unresolved_refs": [],
            },
        ),
        (
            "history_and_unresolved_ref",
            {
                "question": "这个表还能用于临时结构吗？",
                "conversation_history": [
                    {
                        "question": "桥梁的设计使用年限是多少？",
                        "answer": "桥梁通常按 100 年设计。",
                    },
                    {
                        "question": "建筑结构呢？",
                        "answer": "普通建筑结构通常按 50 年设计。",
                    },
                ],
                "generation_mode": "partial",
                "resolved_refs": [],
                "unresolved_refs": ["National Annex"],
            },
        ),
        (
            "guide_and_example_context",
            {
                "question": "如何查表确定设计使用年限？",
                "generation_mode": "partial",
                "intent_label": "parameter_lookup",
            },
        ),
    ],
)
def test_build_prompt_characterization(
    case_name: str,
    kwargs: dict[str, Any],
    sample_text_chunk: Chunk,
    sample_table_chunk: Chunk,
) -> None:
    guide_chunk = _variant_chunk(
        sample_text_chunk,
        chunk_id="guide-design-life",
        content="Design guide note: choose the category before reading the years.",
        source="Designers Guide 2024",
        source_title="Designers Guide to EN 1990",
        section_path=["Guide", "Design working life"],
        clause_ids=["Guide 2.3"],
        page_numbers=[12],
    )
    guide_example_chunk = _variant_chunk(
        sample_text_chunk,
        chunk_id="guide-example-design-life",
        content="Worked example: bridge category 5 maps to 100 years.",
        source="Designers Guide 2024",
        source_title="Designers Guide to EN 1990",
        section_path=["Examples", "Bridge design working life"],
        clause_ids=["Example 2.3"],
        page_numbers=[13],
    )

    prompt = build_prompt(
        kwargs.pop("question"),
        [sample_text_chunk],
        [sample_table_chunk],
        ref_chunks=[sample_table_chunk],
        guide_chunks=[guide_chunk],
        guide_example_chunks=[guide_example_chunk],
        **kwargs,
    )

    _assert_snapshot(
        f"generation_build_prompt_{case_name}",
        {"case": case_name, "prompt": prompt},
    )


@pytest.mark.parametrize(
    ("case_name", "answer", "num_sources"),
    [
        (
            "normalizes_variants",
            "结论见【Ref 1】和(ref-2)，但 Ref 自然语言不应改写。",
            2,
        ),
        (
            "strips_out_of_bounds",
            "有效依据 [Ref-1]，无效依据 [Ref-0] 和 [Ref-9]。",
            3,
        ),
        (
            "dedupes_within_sentence",
            "同一句重复 [Ref-1] 与 [Ref-1]。下一句仍可再次引用 [Ref-1]！",
            1,
        ),
        (
            "keeps_empty_answer",
            "",
            4,
        ),
    ],
)
def test_postprocess_citations_characterization(
    case_name: str,
    answer: str,
    num_sources: int,
) -> None:
    _assert_snapshot(
        f"generation_postprocess_citations_{case_name}",
        {
            "case": case_name,
            "input": {"answer": answer, "num_sources": num_sources},
            "output": postprocess_citations(answer, num_sources),
        },
    )


@pytest.mark.parametrize(
    "case_name,groundedness",
    [
        ("grounded", "grounded"),
        ("partial", "partial"),
        ("not_grounded", "not_grounded"),
        ("unknown_defaults_partial", "open"),
        ("none_defaults_partial", None),
    ],
)
def test_decide_generation_mode_characterization(
    case_name: str,
    groundedness: str | None,
) -> None:
    _assert_snapshot(
        f"generation_decide_mode_{case_name}",
        {
            "case": case_name,
            "input": groundedness,
            "output": decide_generation_mode(groundedness),
        },
    )


@pytest.mark.parametrize(
    "case_name",
    ["main_then_parent_ref_guide_example", "dedupes_first_occurrence", "empty_inputs"],
)
def test_prioritized_source_chunks_characterization(
    case_name: str,
    sample_text_chunk: Chunk,
    sample_table_chunk: Chunk,
) -> None:
    guide_chunk = _variant_chunk(
        sample_text_chunk,
        chunk_id="guide-1",
        content="Guide context content.",
        source="Designers Guide",
        clause_ids=["Guide 1"],
    )
    example_chunk = _variant_chunk(
        sample_text_chunk,
        chunk_id="guide-example-1",
        content="Guide example content.",
        source="Designers Guide",
        clause_ids=["Example 1"],
    )

    if case_name == "empty_inputs":
        ordered = _build_prioritized_source_chunks([], [])
    elif case_name == "dedupes_first_occurrence":
        duplicate_text = sample_text_chunk.model_copy(
            update={"content": "Duplicate content should not win."}
        )
        ordered = _build_prioritized_source_chunks(
            [sample_text_chunk, duplicate_text],
            [sample_table_chunk, sample_table_chunk],
            ref_chunks=[sample_text_chunk],
            guide_chunks=[guide_chunk],
        )
    else:
        ordered = _build_prioritized_source_chunks(
            [sample_text_chunk],
            [sample_table_chunk],
            ref_chunks=[sample_table_chunk],
            guide_chunks=[guide_chunk],
            guide_example_chunks=[example_chunk],
            generation_mode="grounded",
            question="桥梁设计使用年限？",
            intent_label="parameter_lookup",
        )

    _assert_snapshot(
        f"generation_prioritized_chunks_{case_name}",
        {
            "case": case_name,
            "ordered_chunk_ids": [chunk.chunk_id for chunk in ordered],
            "ordered_sources": [chunk.metadata.source for chunk in ordered],
            "ordered_clauses": [chunk.metadata.clause_ids for chunk in ordered],
        },
    )


@pytest.mark.parametrize(
    "case_name",
    [
        "text_source_metadata",
        "table_source_metadata",
        "prioritized_order_with_duplicate_input",
    ],
)
def test_build_sources_from_chunks_characterization(
    case_name: str,
    sample_text_chunk: Chunk,
    sample_table_chunk: Chunk,
) -> None:
    cfg = ServerConfig(use_unified_tokenizer=False)
    if case_name == "text_source_metadata":
        sources = _build_sources_from_chunks([sample_text_chunk], config=cfg)
    elif case_name == "table_source_metadata":
        sources = _build_sources_from_chunks([sample_table_chunk], config=cfg)
    else:
        duplicate_text = sample_text_chunk.model_copy(
            update={"content": "Duplicate content should not appear in source list."}
        )
        prioritized = _build_prioritized_source_chunks(
            [sample_text_chunk],
            [sample_table_chunk],
        )
        sources = _build_sources_from_chunks(
            [sample_table_chunk, duplicate_text],
            config=cfg,
            prioritized_chunks=prioritized,
        )

    _assert_snapshot(
        f"generation_sources_from_chunks_{case_name}",
        {
            "case": case_name,
            "sources": [source.model_dump() for source in sources],
        },
    )


@pytest.mark.parametrize(
    "case_name",
    ["main_scores_only", "all_context_buckets", "resolved_and_unresolved_refs"],
)
def test_retrieval_context_characterization(
    case_name: str,
    sample_text_chunk: Chunk,
    sample_table_chunk: Chunk,
) -> None:
    guide_chunk = _variant_chunk(
        sample_text_chunk,
        chunk_id="guide-context",
        content="Guide context for choosing design working life category.",
        source="Designers Guide",
        source_title="Designers Guide to EN 1990",
        clause_ids=["Guide 2.3"],
        page_numbers=[44],
    )
    example_chunk = _variant_chunk(
        sample_text_chunk,
        chunk_id="guide-example",
        content="Example maps a bridge to category 5 and 100 years.",
        source="Designers Guide",
        source_title="Designers Guide to EN 1990",
        clause_ids=["Example 2.3"],
        page_numbers=[45],
    )

    if case_name == "main_scores_only":
        context = _build_retrieval_context(
            [sample_text_chunk],
            [],
            scores=[0.91],
            config=ServerConfig(use_unified_tokenizer=False),
        )
    elif case_name == "all_context_buckets":
        context = _build_retrieval_context(
            [sample_text_chunk],
            [sample_table_chunk],
            guide_chunks=[guide_chunk],
            guide_example_chunks=[example_chunk],
            ref_chunks=[sample_table_chunk],
            scores=[0.91],
            config=ServerConfig(use_unified_tokenizer=False),
        )
    else:
        context = _build_retrieval_context(
            [sample_text_chunk],
            [sample_table_chunk],
            ref_chunks=[sample_table_chunk],
            resolved_refs=["Table 2.1"],
            unresolved_refs=["National Annex"],
            config=ServerConfig(use_unified_tokenizer=False),
        )

    _assert_snapshot(
        f"generation_retrieval_context_{case_name}",
        {"case": case_name, "retrieval_context": context.model_dump()},
    )
