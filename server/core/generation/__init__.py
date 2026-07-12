"""Generation support facade for citations, sources, and retrieval context."""

from __future__ import annotations

from openai import AsyncOpenAI
from shared.tokenizers import count_for_llm

from server.core.generation.citations import (
    _CANONICAL_REF_RE,
    _CITATION_VARIANTS_RE,
    _extract_json_text,
    postprocess_citations,
)
from server.core.generation.context import (
    _build_retrieval_context,
    _build_retrieval_context_entry,
    _dedupe_chunks_and_scores,
    _dedupe_chunks_by_id,
)
from server.core.generation.sources import (
    _build_document_id,
    _build_highlight_text,
    _build_locator_text,
    _build_prioritized_source_chunks,
    _build_sources_from_chunks,
    _collect_pending_source_indexes,
    _extract_content_list_caption,
    _extract_table_caption,
    _extract_table_html,
    _load_content_list_payload,
    _load_parse_option_file_name,
    _normalize_sources,
    _normalize_table_html,
    _parse_source_payload,
    _resolve_chunk_display_title,
    _resolve_content_list_path,
    _resolve_document_id,
    _resolve_table_source_geometry,
)
from server.core.generation.translation import (
    _SOURCE_TRANSLATION_SYSTEM_PROMPT,
    _build_source_translation_prompt,
    _call_source_translation_llm,
    _fill_missing_source_translations,
    _parse_source_translation_map,
    _translate_source_batch,
)

__all__ = [
    "AsyncOpenAI",
    "_CANONICAL_REF_RE",
    "_CITATION_VARIANTS_RE",
    "_SOURCE_TRANSLATION_SYSTEM_PROMPT",
    "_build_document_id",
    "_build_highlight_text",
    "_build_locator_text",
    "_build_prioritized_source_chunks",
    "_build_retrieval_context",
    "_build_retrieval_context_entry",
    "_build_source_translation_prompt",
    "_build_sources_from_chunks",
    "_call_source_translation_llm",
    "_collect_pending_source_indexes",
    "_dedupe_chunks_and_scores",
    "_dedupe_chunks_by_id",
    "_extract_content_list_caption",
    "_extract_json_text",
    "_extract_table_caption",
    "_extract_table_html",
    "_fill_missing_source_translations",
    "_load_content_list_payload",
    "_load_parse_option_file_name",
    "_normalize_sources",
    "_normalize_table_html",
    "_parse_source_payload",
    "_parse_source_translation_map",
    "_resolve_chunk_display_title",
    "_resolve_content_list_path",
    "_resolve_document_id",
    "_resolve_table_source_geometry",
    "_translate_source_batch",
    "count_for_llm",
    "postprocess_citations",
]
