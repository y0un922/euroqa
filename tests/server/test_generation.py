"""Test generation layer (mock LLM)."""
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from server.config import ServerConfig
from server.core.generation import (
    _STREAM_BASE_RULES,
    _SYSTEM_PROMPT,
    _collect_exact_evidence_candidates,
    _build_exact_evidence_pack,
    build_exact_not_grounded_system_prompt,
    build_exact_system_prompt,
    build_open_system_prompt,
    _build_sources_from_chunks,
    _build_source_translation_prompt,
    _call_source_translation_llm,
    _fill_missing_source_translations,
    build_prompt,
    decide_generation_mode,
    generate_answer,
    generate_answer_stream,
    parse_llm_response,
)
from server.models.schemas import Confidence


class TestBuildPrompt:
    def test_includes_question(self, sample_text_chunk, sample_table_chunk):
        prompt = build_prompt("巴黎地铁寿命", [sample_text_chunk, sample_table_chunk], [])
        assert "巴黎地铁寿命" in prompt

    def test_includes_source_info(self, sample_text_chunk, sample_table_chunk):
        prompt = build_prompt("test", [sample_text_chunk], [])
        assert "EN 1990:2002" in prompt
        assert "2.3" in prompt or "Section 2" in prompt

    def test_includes_glossary(self, sample_text_chunk):
        glossary = {"设计使用年限": "design working life"}
        prompt = build_prompt("test", [sample_text_chunk], [], glossary_terms=glossary)
        assert "design working life" in prompt


class TestAnswerPrompts:
    def test_system_prompt_prefers_supported_answer_before_missing_info(self):
        assert "先给出基于当前片段可以直接确认的答案" in _SYSTEM_PROMPT
        assert "只有在当前片段连部分答案都无法支持时" in _SYSTEM_PROMPT

    def test_parameter_template_sections(self):
        prompt = build_open_system_prompt(question_type="parameter")
        assert "### 直接结果" in prompt
        assert "### 怎么查到的" in prompt
        assert "### 使用限制" in prompt

    def test_rule_template_sections(self):
        prompt = build_open_system_prompt(question_type="rule")
        assert "### 规定内容" in prompt
        assert "### 适用范围与限制" in prompt
        assert "### 工程上怎么做" in prompt

    def test_calculation_template_sections(self):
        prompt = build_open_system_prompt(question_type="calculation")
        assert "### 逐步计算" in prompt
        assert "### 输入条件" in prompt
        assert "### 计算结果摘要" in prompt
        assert "### 使用限制" in prompt

    def test_mechanism_template_sections(self):
        prompt = build_open_system_prompt(question_type="mechanism")
        assert "### 结论" in prompt
        assert "### 原理解释" in prompt
        assert "### 工程影响" in prompt

    def test_unknown_question_type_falls_back_to_rule(self):
        prompt = build_open_system_prompt(question_type=None)
        assert "### 规定内容" in prompt
        assert "### 适用范围与限制" in prompt
        assert "### 工程上怎么做" in prompt

    def test_invalid_question_type_falls_back_to_rule(self):
        prompt = build_open_system_prompt(question_type="nonsense_type")
        assert "### 规定内容" in prompt

    _OLD_SECTION_HEADERS = [
        "### 先说结论",
        "### 这条规则在说什么",
        "### 适用条件与边界",
        "### 工程上怎么用",
        "### 容易出错的点",
        "### 当前依据",
        "### 还需要补充确认的内容",
    ]

    @pytest.mark.parametrize("qt", ["parameter", "rule", "calculation", "mechanism", None])
    def test_old_section_headers_absent(self, qt):
        prompt = build_open_system_prompt(question_type=qt)
        for header in self._OLD_SECTION_HEADERS:
            assert header not in prompt, f"Old header '{header}' still in {qt} template"

    @pytest.mark.parametrize("qt", ["parameter", "rule", "calculation", "mechanism"])
    def test_anti_vagueness_rules_in_open_templates(self, qt):
        prompt = build_open_system_prompt(question_type=qt)
        assert "禁止输出以下模式的空话" in prompt

    def test_anti_vagueness_rules_in_exact_template(self):
        prompt = build_exact_system_prompt()
        assert "禁止输出不含实际信息" in prompt

    def test_exact_value_citation_rule(self):
        prompt = build_exact_system_prompt()
        assert "每个具体数值" in prompt
        assert "[Ref-N]" in prompt

    def test_exact_system_prompt_structure(self):
        prompt = build_exact_system_prompt()
        assert "### 直接答案" in prompt
        assert "### 关键依据" in prompt
        assert "### 这条规定应如何理解和使用" in prompt
        assert "### 使用时要再核对的条件" in prompt
        assert "先直接回答" in prompt
        assert "中度展开" in prompt or "必要解释" in prompt

    def test_exact_not_grounded_system_prompt_has_guardrails(self):
        prompt = build_exact_not_grounded_system_prompt()
        assert "### 当前能确认的内容" in prompt
        assert "### 为什么还不能直接下结论" in prompt
        assert "### 对工程决策的影响" in prompt
        assert "### 下一步应优先补查什么" in prompt
        assert "不能把相关材料包装成直接依据" in prompt

    def test_engineering_context_injected_in_all_templates(self):
        from server.models.schemas import EngineeringContext
        ctx = EngineeringContext(country="Germany", structure_type="bridge")
        for qt in ["parameter", "rule", "calculation", "mechanism"]:
            prompt = build_open_system_prompt(question_type=qt, engineering_context=ctx)
            assert "Germany" in prompt, f"Context missing in {qt} template"

    def test_engineering_context_missing_fields_use_generic_wording(self):
        from server.models.schemas import EngineeringContext
        ctx = EngineeringContext(country="Germany")
        prompt = build_open_system_prompt(question_type="rule", engineering_context=ctx)
        assert "还需要补充确认的内容" not in prompt

    def test_no_context_uses_generic_wording(self):
        prompt = build_open_system_prompt(question_type="rule")
        assert "还需要补充确认的内容" not in prompt

    def test_decide_generation_mode_prefers_groundedness(self):
        assert decide_generation_mode("exact", "grounded") == "exact"
        assert decide_generation_mode("exact", "exact_not_grounded") == "exact_not_grounded"
        assert decide_generation_mode("open", "grounded") == "open"
        assert decide_generation_mode(None, "grounded") == "open"

    @pytest.mark.parametrize("qt", ["parameter", "rule", "calculation", "mechanism"])
    def test_all_templates_target_chinese_engineers(self, qt):
        prompt = build_open_system_prompt(question_type=qt)
        assert "中国工程师" in prompt


class TestParseLlmResponse:
    def test_parse_valid_json(self):
        raw = json.dumps({
            "answer": "100年",
            "sources": [{"file": "EN 1990", "title": "Basis", "section": "2.3",
                         "page": 28, "clause": "Table 2.1", "original_text": "bridges",
                         "translation": "桥梁"}],
            "related_refs": ["Annex A"],
            "confidence": "high"
        })
        result = parse_llm_response(raw)
        assert result.answer == "100年"
        assert result.confidence == Confidence.HIGH
        assert len(result.sources) == 1

    def test_parse_json_in_code_block(self):
        raw = '```json\n{"answer": "test", "sources": [], "related_refs": [], "confidence": "low"}\n```'
        result = parse_llm_response(raw)
        assert result.answer == "test"
        assert result.confidence == Confidence.LOW

    def test_fallback_on_invalid_json(self):
        raw = "这是一个非 JSON 的回答"
        result = parse_llm_response(raw)
        assert result.answer == raw
        assert result.confidence == Confidence.LOW


class TestSourceTranslationFill:
    def test_build_sources_from_chunks_keeps_full_original_text(
        self, sample_text_chunk
    ):
        long_text = "A" * 1201
        long_chunk = sample_text_chunk.model_copy(update={"content": long_text})

        sources = _build_sources_from_chunks([long_chunk])

        assert sources[0].original_text == long_text

    def test_build_sources_from_chunks_sets_document_id_and_locator_text(
        self, sample_text_chunk
    ):
        sources = _build_sources_from_chunks([sample_text_chunk])

        assert sources[0].document_id == "EN1990_2002"
        assert sources[0].locator_text
        assert sources[0].highlight_text
        assert "\n" not in sources[0].locator_text
        assert "[->" not in sources[0].locator_text
        assert "[->" not in sources[0].highlight_text
        assert "  " not in sources[0].locator_text
        assert len(sources[0].locator_text) <= 240
        assert "2.3 Design working life" in sources[0].locator_text
        assert "The design working life should be specified." in sources[0].locator_text
        assert "The design working life should be specified." in sources[0].highlight_text
        assert "NOTE Indicative categories are given in Table 2.1." in sources[0].highlight_text

    def test_build_sources_from_chunks_keeps_full_highlight_text_without_truncation(
        self, sample_text_chunk
    ):
        chunk = sample_text_chunk.model_copy(
            update={
                "content": (
                    "Paragraph one keeps growing with enough context to exceed the old "
                    "locator truncation threshold. " * 8
                ).strip()
            }
        )

        sources = _build_sources_from_chunks([chunk])

        assert sources[0].highlight_text == chunk.content
        assert len(sources[0].highlight_text) > 240

    def test_build_sources_from_chunks_keeps_full_highlight_text_for_multi_page_chunk(
        self, sample_text_chunk
    ):
        chunk = sample_text_chunk.model_copy(
            update={
                "content": "Page 1 paragraph.\n\nPage 2 paragraph.",
                "metadata": sample_text_chunk.metadata.model_copy(
                    update={"page_numbers": [10, 11]}
                ),
            }
        )

        sources = _build_sources_from_chunks([chunk])

        assert sources[0].highlight_text == "Page 1 paragraph.\n\nPage 2 paragraph."

    def test_build_sources_from_chunks_keeps_non_marker_bracket_content(
        self, sample_text_chunk
    ):
        chunk = sample_text_chunk.model_copy(
            update={
                "content": (
                    "Keep [Clause A] for search.\n"
                    "[-> Internal retrieval marker]\n"
                    "Keep [Annex B] as well."
                )
            }
        )

        sources = _build_sources_from_chunks([chunk])

        assert "[Clause A]" in sources[0].locator_text
        assert "[Annex B]" in sources[0].locator_text
        assert "[-> Internal retrieval marker]" not in sources[0].locator_text

    def test_build_sources_from_chunks_locator_text_falls_back_when_marker_only(
        self, sample_text_chunk
    ):
        chunk = sample_text_chunk.model_copy(
            update={"content": "[-> Internal retrieval marker]"}
        )

        sources = _build_sources_from_chunks([chunk])

        assert sources[0].locator_text
        assert sources[0].locator_text == "[-> Internal retrieval marker]"

    def test_build_source_translation_prompt_keeps_full_original_text(
        self, sample_text_chunk
    ):
        long_text = "B" * 1201
        long_chunk = sample_text_chunk.model_copy(update={"content": long_text})
        sources = _build_sources_from_chunks([long_chunk])

        prompt = _build_source_translation_prompt(sources)

        assert long_text in prompt

    def test_build_source_translation_prompt_requests_markdown_friendly_output(
        self, sample_text_chunk
    ):
        sources = _build_sources_from_chunks([sample_text_chunk])

        prompt = _build_source_translation_prompt(sources)

        assert "Markdown" in prompt
        assert "表格" in prompt

    def test_build_sources_from_chunks_enriches_table_bbox_and_element_type(
        self, tmp_path: Path
    ):
        from server.models.schemas import Chunk, ChunkMetadata, ElementType

        chunk = Chunk(
            chunk_id="chunk_t_2_1",
            content=(
                "Table 2.1 - Indicative design working life\n"
                "<table><tr><td>1</td><td>10</td><td>Temporary structures</td></tr></table>"
            ),
            embedding_text="table summary",
            metadata=ChunkMetadata(
                source="EN 1990:2002",
                source_title="Eurocode - Basis of structural design",
                section_path=["Section 2 Requirements", "2.3 Design working life"],
                page_numbers=[28],
                page_file_index=[27],
                clause_ids=["Table 2.1"],
                element_type=ElementType.TABLE,
            ),
        )
        parsed_dir = tmp_path / "parsed" / "EN1990_2002"
        parsed_dir.mkdir(parents=True)
        (parsed_dir / "EN1990_2002_content_list.json").write_text(
            json.dumps(
                [
                    {
                        "type": "table",
                        "page_idx": 27,
                        "bbox": [186, 591, 858, 768],
                        "table_caption": ["Table 2.1 - Indicative design working life"],
                        "table_body": "<table><tr><td>1</td><td>10</td><td>Temporary structures</td></tr></table>",
                    }
                ]
            ),
            encoding="utf-8",
        )

        sources = _build_sources_from_chunks(
            [chunk],
            config=ServerConfig(parsed_dir=str(tmp_path / "parsed")),
        )

        assert sources[0].element_type == "table"
        assert sources[0].bbox == [186.0, 591.0, 858.0, 768.0]
        assert sources[0].highlight_text.startswith("Table 2.1 - Indicative design working life")

    def test_build_exact_evidence_pack_prefers_text_clause_then_visual_support(
        self, sample_text_chunk, sample_table_chunk
    ):
        evidence = _build_exact_evidence_pack(
            [sample_table_chunk, sample_text_chunk],
            question="设计使用年限怎么确定？",
        )

        assert evidence["primary_clause"] is sample_text_chunk
        assert evidence["supporting_visuals"] == [sample_table_chunk]

    def test_collect_exact_evidence_candidates_keeps_parent_visuals_only(
        self, sample_text_chunk, sample_table_chunk
    ):
        parent_text = sample_text_chunk.model_copy(
            update={"chunk_id": "parent-text"}
        )
        candidates = _collect_exact_evidence_candidates(
            [sample_text_chunk],
            [parent_text, sample_table_chunk],
            [],
        )

        assert [chunk.chunk_id for chunk in candidates] == [
            sample_text_chunk.chunk_id,
            sample_table_chunk.chunk_id,
        ]

    def test_build_sources_from_chunks_can_prioritize_exact_evidence_order(
        self, sample_text_chunk, sample_table_chunk
    ):
        sources = _build_sources_from_chunks(
            [sample_table_chunk, sample_text_chunk],
            prioritized_chunks=[sample_text_chunk, sample_table_chunk],
        )

        assert [source.element_type for source in sources] == ["text", "table"]

    def test_build_exact_evidence_pack_prefers_ref_visuals_before_parent_visuals(
        self, sample_text_chunk, sample_table_chunk
    ):
        parent_visual = sample_table_chunk.model_copy(
            update={"chunk_id": "parent-table", "content": "Parent table context"}
        )

        evidence = _build_exact_evidence_pack(
            [sample_text_chunk, sample_table_chunk, parent_visual],
            question="设计使用年限怎么确定？",
        )

        assert [chunk.chunk_id for chunk in evidence["supporting_visuals"]] == [
            sample_table_chunk.chunk_id,
            "parent-table",
        ]

    @pytest.mark.asyncio
    async def test_fill_missing_source_translations_uses_llm_result(
        self, sample_text_chunk
    ):
        sources = _build_sources_from_chunks([sample_text_chunk])
        mock_llm = AsyncMock(
            return_value=json.dumps(
                {
                    "translations": [
                        {
                            "index": 0,
                            "translation": "设计使用年限应予规定。说明性类别见表 2.1。",
                        }
                    ]
                }
            )
        )

        with patch("server.core.generation._call_source_translation_llm", mock_llm):
            translated = await _fill_missing_source_translations(sources)

        assert translated[0].translation.startswith("设计使用年限应予规定")

    @pytest.mark.asyncio
    async def test_fill_missing_source_translations_retries_per_source_when_batch_json_is_truncated(
        self, sample_text_chunk
    ):
        second_chunk = sample_text_chunk.model_copy(
            update={"chunk_id": "chunk-2", "content": "Second source content."}
        )
        sources = _build_sources_from_chunks([sample_text_chunk, second_chunk])
        mock_llm = AsyncMock(
            side_effect=[
                '{"translations":[{"index":0,"translation":"第一条译文"},{"index":1,"translation":"',
                json.dumps(
                    {"translations": [{"index": 0, "translation": "第一条译文"}]}
                ),
                json.dumps(
                    {"translations": [{"index": 1, "translation": "第二条译文"}]}
                ),
            ]
        )

        with patch("server.core.generation._call_source_translation_llm", mock_llm):
            translated = await _fill_missing_source_translations(sources)

        assert [source.translation for source in translated] == [
            "第一条译文",
            "第二条译文",
        ]
        assert mock_llm.await_count == 3

    @pytest.mark.asyncio
    async def test_call_source_translation_llm_does_not_send_max_tokens(self):
        seen_kwargs: dict[str, object] = {}

        class _FakeClient:
            def __init__(self, *args, **kwargs):
                self.chat = SimpleNamespace(
                    completions=SimpleNamespace(create=self._create)
                )

            async def _create(self, **kwargs):
                seen_kwargs.update(kwargs)
                return SimpleNamespace(
                    choices=[
                        SimpleNamespace(
                            message=SimpleNamespace(
                                content=json.dumps(
                                    {
                                        "translations": [
                                            {
                                                "index": 0,
                                                "translation": "设计使用年限应予规定。",
                                            }
                                        ]
                                    }
                                )
                            )
                        )
                    ]
                )

        with patch("server.core.generation.AsyncOpenAI", _FakeClient):
            await _call_source_translation_llm("translate this")

        assert "max_tokens" not in seen_kwargs


class TestGenerateAnswer:
    @pytest.mark.asyncio
    async def test_generate_answer_exact_prompt_includes_evidence_pack_sections(
        self, sample_text_chunk, sample_table_chunk
    ):
        seen_user_prompts: list[str] = []
        raw = json.dumps({"answer": "可直接确认。", "sources": [], "related_refs": [], "confidence": "high"})

        class _FakeClient:
            def __init__(self, *args, **kwargs):
                self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

            async def _create(self, **kwargs):
                seen_user_prompts.append(kwargs["messages"][1]["content"])
                return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=raw))], usage=None)

        with patch("server.core.generation.AsyncOpenAI", _FakeClient):
            await generate_answer(
                "设计使用年限怎么确定？",
                [sample_text_chunk],
                [sample_table_chunk],
                answer_mode="exact",
                groundedness="grounded",
            )

        assert seen_user_prompts
        assert "主依据条款" in seen_user_prompts[0]
        assert "相关表/图/公式" in seen_user_prompts[0]

    @pytest.mark.asyncio
    async def test_generate_answer_exact_prompt_includes_resolved_and_unresolved_refs(
        self, sample_text_chunk, sample_table_chunk
    ):
        seen_user_prompts: list[str] = []
        raw = json.dumps({"answer": "当前可确认。", "sources": [], "related_refs": [], "confidence": "medium"})

        class _FakeClient:
            def __init__(self, *args, **kwargs):
                self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

            async def _create(self, **kwargs):
                seen_user_prompts.append(kwargs["messages"][1]["content"])
                return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=raw))], usage=None)

        with patch("server.core.generation.AsyncOpenAI", _FakeClient):
            await generate_answer(
                "设计使用年限怎么确定？",
                [sample_text_chunk],
                [],
                ref_chunks=[sample_table_chunk],
                answer_mode="exact",
                groundedness="exact_not_grounded",
                resolved_refs=["Table 2.1"],
                unresolved_refs=["Annex A"],
            )

        assert seen_user_prompts
        assert "已补齐的直接引用" in seen_user_prompts[0]
        assert "Table 2.1" in seen_user_prompts[0]
        assert "尚未补齐的直接引用" in seen_user_prompts[0]
        assert "Annex A" in seen_user_prompts[0]

    @pytest.mark.asyncio
    async def test_generate_answer_uses_exact_system_prompt(self, sample_text_chunk):
        seen_system_prompts: list[str] = []
        raw = json.dumps({"answer": "可直接确认。", "sources": [], "related_refs": [], "confidence": "high"})

        class _FakeClient:
            def __init__(self, *args, **kwargs):
                self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

            async def _create(self, **kwargs):
                seen_system_prompts.append(kwargs["messages"][0]["content"])
                return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=raw))], usage=None)

        with patch("server.core.generation.AsyncOpenAI", _FakeClient):
            await generate_answer(
                "基本假设是什么？",
                [sample_text_chunk],
                [],
                answer_mode="exact",
                groundedness="grounded",
            )

        assert seen_system_prompts
        assert "八个三级标题" not in seen_system_prompts[0]
        assert "回答必须简短" not in seen_system_prompts[0]
        assert "必要解释" in seen_system_prompts[0] or "中度展开" in seen_system_prompts[0]

    @pytest.mark.asyncio
    async def test_generate_answer_uses_exact_not_grounded_system_prompt(self, sample_text_chunk):
        seen_system_prompts: list[str] = []
        raw = json.dumps({"answer": "当前可确认有限。", "sources": [], "related_refs": [], "confidence": "low"})

        class _FakeClient:
            def __init__(self, *args, **kwargs):
                self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

            async def _create(self, **kwargs):
                seen_system_prompts.append(kwargs["messages"][0]["content"])
                return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=raw))], usage=None)

        with patch("server.core.generation.AsyncOpenAI", _FakeClient):
            await generate_answer(
                "基本假设是什么？",
                [sample_text_chunk],
                [],
                answer_mode="exact",
                groundedness="exact_not_grounded",
            )

        assert seen_system_prompts
        assert "当前能确认的内容" in seen_system_prompts[0]
        assert "为什么还不能直接下结论" in seen_system_prompts[0]
        assert "下一步应优先补查什么" in seen_system_prompts[0]

    @pytest.mark.asyncio
    async def test_generate_answer_includes_retrieval_context_snapshot(
        self, sample_text_chunk, sample_table_chunk
    ):
        raw = json.dumps(
            {
                "answer": "根据条文应予规定。",
                "sources": [],
                "related_refs": [],
                "confidence": "medium",
            }
        )

        class _FakeClient:
            def __init__(self, *args, **kwargs):
                self.chat = SimpleNamespace(
                    completions=SimpleNamespace(create=self._create)
                )

            async def _create(self, **kwargs):
                return SimpleNamespace(
                    choices=[SimpleNamespace(message=SimpleNamespace(content=raw))]
                )

        with patch("server.core.generation.AsyncOpenAI", _FakeClient):
            result = await generate_answer(
                "设计使用年限怎么确定？",
                [sample_text_chunk],
                [sample_table_chunk],
                scores=[0.91],
                ref_chunks=[sample_table_chunk],
                resolved_refs=["Table 2.1"],
                unresolved_refs=["Annex A"],
            )

        assert result.retrieval_context is not None
        assert result.retrieval_context.chunks == [
            {
                "chunk_id": "chunk_023",
                "document_id": "EN1990_2002",
                "file": "EN 1990:2002",
                "title": "Eurocode - Basis of structural design",
                "section": "Section 2 Requirements > 2.3 Design working life",
                "page": "28",
                "clause": "2.3(1)",
                "content": sample_text_chunk.content,
                "score": 0.91,
            }
        ]
        assert result.retrieval_context.parent_chunks == [
            {
                "chunk_id": "chunk_t_2_1",
                "document_id": "EN1990_2002",
                "file": "EN 1990:2002",
                "title": "Eurocode - Basis of structural design",
                "section": "Section 2 Requirements > 2.3 Design working life",
                "page": "28",
                "clause": "Table 2.1",
                "content": sample_table_chunk.content,
            }
        ]
        assert result.retrieval_context.ref_chunks == [
            {
                "chunk_id": "chunk_t_2_1",
                "document_id": "EN1990_2002",
                "file": "EN 1990:2002",
                "title": "Eurocode - Basis of structural design",
                "section": "Section 2 Requirements > 2.3 Design working life",
                "page": "28",
                "clause": "Table 2.1",
                "content": sample_table_chunk.content,
            }
        ]
        assert result.retrieval_context.resolved_refs == ["Table 2.1"]
        assert result.retrieval_context.unresolved_refs == ["Annex A"]

    @pytest.mark.asyncio
    async def test_generate_answer_exact_sources_follow_evidence_order(
        self, sample_text_chunk, sample_table_chunk
    ):
        raw = json.dumps(
            {
                "answer": "根据条文应予规定。",
                "sources": [],
                "related_refs": [],
                "confidence": "high",
            }
        )
        extra_text = sample_text_chunk.model_copy(
            update={"chunk_id": "text-extra", "content": "Auxiliary explanatory text."}
        )

        class _FakeClient:
            def __init__(self, *args, **kwargs):
                self.chat = SimpleNamespace(
                    completions=SimpleNamespace(create=self._create)
                )

            async def _create(self, **kwargs):
                return SimpleNamespace(
                    choices=[SimpleNamespace(message=SimpleNamespace(content=raw))]
                )

        with patch("server.core.generation.AsyncOpenAI", _FakeClient):
            result = await generate_answer(
                "设计使用年限怎么确定？",
                [extra_text, sample_text_chunk],
                [],
                ref_chunks=[sample_table_chunk],
                answer_mode="exact",
                groundedness="grounded",
            )

        assert [source.clause for source in result.sources[:3]] == [
            "2.3(1)",
            "Table 2.1",
            "2.3(1)",
        ]

    @pytest.mark.asyncio
    async def test_generate_answer_leaves_missing_source_translation_empty(
        self, sample_text_chunk
    ):
        raw = json.dumps(
            {
                "answer": "根据条文应予规定。",
                "sources": [
                    {
                        "file": "EN 1990:2002",
                        "title": "Basis",
                        "section": "2.3",
                        "page": 28,
                        "clause": "2.3(1)",
                        "original_text": "The design working life should be specified.",
                        "translation": "",
                    }
                ],
                "related_refs": [],
                "confidence": "medium",
            }
        )

        class _FakeClient:
            def __init__(self, *args, **kwargs):
                self.chat = SimpleNamespace(
                    completions=SimpleNamespace(create=self._create)
                )

            async def _create(self, **kwargs):
                return SimpleNamespace(
                    choices=[SimpleNamespace(message=SimpleNamespace(content=raw))]
                )

        mock_translation = AsyncMock(
            return_value=json.dumps(
                {
                    "translations": [
                        {"index": 0, "translation": "设计使用年限应予规定。"}
                    ]
                }
            )
        )

        with patch("server.core.generation.AsyncOpenAI", _FakeClient), patch(
            "server.core.generation._call_source_translation_llm",
            mock_translation,
        ):
            result = await generate_answer("设计使用年限怎么确定？", [sample_text_chunk], [])

        assert result.sources[0].translation == ""
        assert result.sources[0].document_id == "EN1990_2002"
        assert result.sources[0].locator_text
        assert result.sources[0].highlight_text
        assert "\n" not in result.sources[0].locator_text
        assert "[->" not in result.sources[0].locator_text
        mock_translation.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_generate_answer_preserves_source_when_llm_omits_translation(
        self, sample_text_chunk
    ):
        raw = json.dumps(
            {
                "answer": "根据条文应予规定。",
                "sources": [
                    {
                        "file": "EN 1990:2002",
                        "title": "Basis",
                        "section": "2.3",
                        "page": 28,
                        "clause": "2.3(1)",
                        "original_text": "The design working life should be specified.",
                    }
                ],
                "related_refs": [],
                "confidence": "medium",
            }
        )

        class _FakeClient:
            def __init__(self, *args, **kwargs):
                self.chat = SimpleNamespace(
                    completions=SimpleNamespace(create=self._create)
                )

            async def _create(self, **kwargs):
                return SimpleNamespace(
                    choices=[SimpleNamespace(message=SimpleNamespace(content=raw))]
                )

        with patch("server.core.generation.AsyncOpenAI", _FakeClient):
            result = await generate_answer("设计使用年限怎么确定？", [sample_text_chunk], [])

        assert len(result.sources) == 1
        assert result.sources[0].translation == ""
        assert result.sources[0].document_id == "EN1990_2002"
        assert result.sources[0].locator_text

    @pytest.mark.asyncio
    async def test_generate_answer_clears_llm_provided_source_translation(
        self, sample_text_chunk
    ):
        raw = json.dumps(
            {
                "answer": "根据条文应予规定。",
                "sources": [
                    {
                        "file": "EN 1990:2002",
                        "title": "Basis",
                        "section": "2.3",
                        "page": 28,
                        "clause": "2.3(1)",
                        "original_text": "The design working life should be specified.",
                        "translation": "设计使用年限应予规定。",
                    }
                ],
                "related_refs": [],
                "confidence": "medium",
            }
        )

        class _FakeClient:
            def __init__(self, *args, **kwargs):
                self.chat = SimpleNamespace(
                    completions=SimpleNamespace(create=self._create)
                )

            async def _create(self, **kwargs):
                return SimpleNamespace(
                    choices=[SimpleNamespace(message=SimpleNamespace(content=raw))]
                )

        with patch("server.core.generation.AsyncOpenAI", _FakeClient):
            result = await generate_answer("设计使用年限怎么确定？", [sample_text_chunk], [])

        assert len(result.sources) == 1
        assert result.sources[0].translation == ""

    @pytest.mark.asyncio
    async def test_generate_answer_uses_canonical_retrieval_sources_over_llm_source_metadata(
        self, sample_text_chunk
    ):
        raw = json.dumps(
            {
                "answer": "根据条文应予规定。",
                "sources": [
                    {
                        "file": "LLM rewritten source",
                        "title": "Wrong title",
                        "section": "Wrong section",
                        "page": 999,
                        "clause": "Wrong clause",
                        "original_text": "Wrong original text.",
                        "translation": "Wrong translation.",
                    }
                ],
                "related_refs": [],
                "confidence": "medium",
            }
        )

        class _FakeClient:
            def __init__(self, *args, **kwargs):
                self.chat = SimpleNamespace(
                    completions=SimpleNamespace(create=self._create)
                )

            async def _create(self, **kwargs):
                return SimpleNamespace(
                    choices=[SimpleNamespace(message=SimpleNamespace(content=raw))]
                )

        with patch("server.core.generation.AsyncOpenAI", _FakeClient):
            result = await generate_answer("设计使用年限怎么确定？", [sample_text_chunk], [])

        expected = _build_sources_from_chunks([sample_text_chunk])
        assert [source.model_dump() for source in result.sources] == [
            source.model_dump() for source in expected
        ]

    @pytest.mark.asyncio
    async def test_generate_answer_uses_canonical_sources_when_llm_sources_empty(
        self, sample_text_chunk
    ):
        raw = json.dumps(
            {
                "answer": "根据条文应予规定。",
                "sources": [],
                "related_refs": [],
                "confidence": "medium",
            }
        )

        class _FakeClient:
            def __init__(self, *args, **kwargs):
                self.chat = SimpleNamespace(
                    completions=SimpleNamespace(create=self._create)
                )

            async def _create(self, **kwargs):
                return SimpleNamespace(
                    choices=[SimpleNamespace(message=SimpleNamespace(content=raw))]
                )

        with patch("server.core.generation.AsyncOpenAI", _FakeClient):
            result = await generate_answer("设计使用年限怎么确定？", [sample_text_chunk], [])

        expected = _build_sources_from_chunks([sample_text_chunk])
        assert [source.model_dump() for source in result.sources] == [
            source.model_dump() for source in expected
        ]

    @pytest.mark.asyncio
    async def test_generate_answer_uses_canonical_sources_when_llm_sources_missing(
        self, sample_text_chunk
    ):
        raw = json.dumps(
            {
                "answer": "根据条文应予规定。",
                "related_refs": [],
                "confidence": "medium",
            }
        )

        class _FakeClient:
            def __init__(self, *args, **kwargs):
                self.chat = SimpleNamespace(
                    completions=SimpleNamespace(create=self._create)
                )

            async def _create(self, **kwargs):
                return SimpleNamespace(
                    choices=[SimpleNamespace(message=SimpleNamespace(content=raw))]
                )

        with patch("server.core.generation.AsyncOpenAI", _FakeClient):
            result = await generate_answer("设计使用年限怎么确定？", [sample_text_chunk], [])

        expected = _build_sources_from_chunks([sample_text_chunk])
        assert [source.model_dump() for source in result.sources] == [
            source.model_dump() for source in expected
        ]


class TestBuildSourcesBbox:
    def test_uses_metadata_bbox_for_text_chunk(self, sample_text_chunk):
        sources = _build_sources_from_chunks([sample_text_chunk])
        assert sources[0].bbox == [186, 362, 858, 420]
        assert sources[0].page == "28"  # bbox_page_idx 27 + 1

    def test_uses_metadata_bbox_for_table_chunk(self, sample_table_chunk):
        sources = _build_sources_from_chunks([sample_table_chunk])
        assert sources[0].bbox == [186, 591, 858, 768]

    def test_prefers_physical_page_index_when_no_bbox(self, sample_text_chunk):
        """page_file_index（物理页码）应优先于 page_numbers（逻辑页码）。"""
        no_bbox_chunk = sample_text_chunk.model_copy(
            update={"metadata": sample_text_chunk.metadata.model_copy(
                update={
                    "bbox": [],
                    "bbox_page_idx": -1,
                    "page_numbers": [30],
                    "page_file_index": [27],
                }
            )}
        )
        sources = _build_sources_from_chunks([no_bbox_chunk])
        assert sources[0].bbox == []
        assert sources[0].page == "28"  # page_file_index[0] + 1

    def test_falls_back_to_page_numbers_when_no_physical_page(self, sample_text_chunk):
        """page_file_index 为空时退回 page_numbers。"""
        no_bbox_chunk = sample_text_chunk.model_copy(
            update={"metadata": sample_text_chunk.metadata.model_copy(
                update={
                    "bbox": [],
                    "bbox_page_idx": -1,
                    "page_numbers": [30],
                    "page_file_index": [],
                }
            )}
        )
        sources = _build_sources_from_chunks([no_bbox_chunk])
        assert sources[0].bbox == []
        assert sources[0].page == "30"


class TestGenerateAnswerStream:
    @pytest.mark.asyncio
    async def test_generate_answer_stream_uses_open_prompt_by_default(self, sample_text_chunk):
        seen_system_prompts: list[str] = []

        class _FakeStreamClient:
            def __init__(self, *args, **kwargs):
                self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

            async def _create(self, **kwargs):
                seen_system_prompts.append(kwargs["messages"][0]["content"])

                async def _stream():
                    yield SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content="结论：开放式回答。"), finish_reason="stop")])

                return _stream()

        with patch("server.core.generation.AsyncOpenAI", _FakeStreamClient):
            events = []
            async for event_type, data in generate_answer_stream(
                "设计使用年限怎么确定？",
                [sample_text_chunk],
                [],
                scores=[0.9],
            ):
                events.append((event_type, data))

        assert seen_system_prompts
        assert "### 先说结论" in seen_system_prompts[0]
        assert events[-1][0] == "done"
    @pytest.mark.asyncio
    async def test_generate_answer_stream_emits_reasoning_event(
        self, sample_text_chunk
    ):
        class _FakeStreamClient:
            def __init__(self, *args, **kwargs):
                self.chat = SimpleNamespace(
                    completions=SimpleNamespace(create=self._create)
                )

            async def _create(self, **kwargs):
                async def _stream():
                    yield SimpleNamespace(
                        choices=[
                            SimpleNamespace(
                                delta=SimpleNamespace(
                                    reasoning_content="先定位条款。", content=None
                                )
                            )
                        ]
                    )
                    yield SimpleNamespace(
                        choices=[
                            SimpleNamespace(
                                delta=SimpleNamespace(
                                    reasoning_content=None, content="结论：应按规范指定。"
                                )
                            )
                        ]
                    )

                return _stream()

        mock_translation = AsyncMock(
            return_value=json.dumps(
                {
                    "translations": [
                        {
                            "index": 0,
                            "translation": "设计使用年限应按规范明确指定。",
                        }
                    ]
                }
            )
        )

        events: list[tuple[str, dict]] = []
        with patch("server.core.generation.AsyncOpenAI", _FakeStreamClient), patch(
            "server.core.generation._call_source_translation_llm",
            mock_translation,
        ):
            async for event_type, data in generate_answer_stream(
                "设计使用年限怎么确定？",
                [sample_text_chunk],
                [],
                scores=[0.9],
            ):
                events.append((event_type, data))

        assert events[0] == ("reasoning", {"text": "先定位条款。"})
        assert events[1] == ("chunk", {"text": "结论：应按规范指定。", "done": False})

    @pytest.mark.asyncio
    async def test_generate_answer_stream_done_payload_keeps_translation_empty(
        self, sample_text_chunk
    ):
        class _FakeStreamClient:
            def __init__(self, *args, **kwargs):
                self.chat = SimpleNamespace(
                    completions=SimpleNamespace(create=self._create)
                )

            async def _create(self, **kwargs):
                async def _stream():
                    yield SimpleNamespace(
                        choices=[
                            SimpleNamespace(
                                delta=SimpleNamespace(content="结论：")
                            )
                        ]
                    )
                    yield SimpleNamespace(
                        choices=[
                            SimpleNamespace(
                                delta=SimpleNamespace(content="应按规范指定。")
                            )
                        ]
                    )

                return _stream()

        mock_translation = AsyncMock(
            return_value=json.dumps(
                {
                    "translations": [
                        {
                            "index": 0,
                            "translation": "设计使用年限应按规范明确指定。",
                        }
                    ]
                }
            )
        )

        events: list[tuple[str, dict]] = []
        with patch("server.core.generation.AsyncOpenAI", _FakeStreamClient), patch(
            "server.core.generation._call_source_translation_llm",
            mock_translation,
        ):
            async for event_type, data in generate_answer_stream(
                "设计使用年限怎么确定？",
                [sample_text_chunk],
                [],
                scores=[0.9],
            ):
                events.append((event_type, data))

        assert events[0] == ("chunk", {"text": "结论：", "done": False})
        assert events[1] == ("chunk", {"text": "应按规范指定。", "done": False})
        done_event, done_payload = events[-1]
        assert done_event == "done"
        assert done_payload["sources"][0]["translation"] == ""
        assert done_payload["sources"][0]["document_id"] == "EN1990_2002"
        assert done_payload["sources"][0]["locator_text"]
        assert done_payload["confidence"] == "high"
        mock_translation.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_generate_answer_stream_done_payload_includes_retrieval_context_snapshot(
        self, sample_text_chunk, sample_table_chunk
    ):
        class _FakeStreamClient:
            def __init__(self, *args, **kwargs):
                self.chat = SimpleNamespace(
                    completions=SimpleNamespace(create=self._create)
                )

            async def _create(self, **kwargs):
                async def _stream():
                    yield SimpleNamespace(
                        choices=[
                            SimpleNamespace(
                                delta=SimpleNamespace(content="结论：应按规范指定。")
                            )
                        ]
                    )

                return _stream()

        events: list[tuple[str, dict]] = []
        with patch("server.core.generation.AsyncOpenAI", _FakeStreamClient):
            async for event_type, data in generate_answer_stream(
                "设计使用年限怎么确定？",
                [sample_text_chunk],
                [sample_table_chunk],
                scores=[0.91],
            ):
                events.append((event_type, data))

        done_event, done_payload = events[-1]
        assert done_event == "done"
        assert done_payload["retrieval_context"] == {
            "chunks": [
                {
                    "chunk_id": "chunk_023",
                    "document_id": "EN1990_2002",
                    "file": "EN 1990:2002",
                    "title": "Eurocode - Basis of structural design",
                    "section": "Section 2 Requirements > 2.3 Design working life",
                    "page": "28",
                    "clause": "2.3(1)",
                    "content": sample_text_chunk.content,
                    "score": 0.91,
                }
            ],
            "parent_chunks": [
                {
                    "chunk_id": "chunk_t_2_1",
                    "document_id": "EN1990_2002",
                    "file": "EN 1990:2002",
                    "title": "Eurocode - Basis of structural design",
                    "section": "Section 2 Requirements > 2.3 Design working life",
                    "page": "28",
                    "clause": "Table 2.1",
                    "content": sample_table_chunk.content,
                }
            ],
            "ref_chunks": [],
            "resolved_refs": [],
            "unresolved_refs": [],
        }

    @pytest.mark.asyncio
    async def test_generate_answer_matches_stream_done_sources_for_same_chunks(
        self, sample_text_chunk
    ):
        answer_raw = json.dumps(
            {
                "answer": "根据条文应予规定。",
                "sources": [
                    {
                        "file": "LLM rewritten source",
                        "title": "Wrong title",
                        "section": "Wrong section",
                        "page": 999,
                        "clause": "Wrong clause",
                        "original_text": "Wrong original text.",
                        "translation": "Wrong translation.",
                    }
                ],
                "related_refs": [],
                "confidence": "medium",
            }
        )

        class _FakeAnswerClient:
            def __init__(self, *args, **kwargs):
                self.chat = SimpleNamespace(
                    completions=SimpleNamespace(create=self._create)
                )

            async def _create(self, **kwargs):
                return SimpleNamespace(
                    choices=[SimpleNamespace(message=SimpleNamespace(content=answer_raw))]
                )

        class _FakeStreamClient:
            def __init__(self, *args, **kwargs):
                self.chat = SimpleNamespace(
                    completions=SimpleNamespace(create=self._create)
                )

            async def _create(self, **kwargs):
                async def _stream():
                    yield SimpleNamespace(
                        choices=[SimpleNamespace(delta=SimpleNamespace(content="结论：应按规范指定。"))]
                    )

                return _stream()

        with patch("server.core.generation.AsyncOpenAI", _FakeAnswerClient):
            answer_result = await generate_answer(
                "设计使用年限怎么确定？",
                [sample_text_chunk],
                [],
            )

        stream_events: list[tuple[str, dict]] = []
        with patch("server.core.generation.AsyncOpenAI", _FakeStreamClient):
            async for event_type, data in generate_answer_stream(
                "设计使用年限怎么确定？",
                [sample_text_chunk],
                [],
                scores=[0.9],
            ):
                stream_events.append((event_type, data))

        done_event, done_payload = stream_events[-1]
        assert done_event == "done"
        assert [source.model_dump() for source in answer_result.sources] == done_payload[
            "sources"
        ]
