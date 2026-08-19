"""Source translation helpers for generation responses."""

from __future__ import annotations

import json

import httpx
import structlog
from openai import AsyncOpenAI

from server.config import ServerConfig
from server.core.generation.citations import _extract_json_text
from server.core.generation.sources import _collect_pending_source_indexes
from server.models.schemas import Source
from shared.llm_clients import get_async_openai_client
from shared.usage import record_usage, vendor_from_base_url

logger = structlog.get_logger(__name__)


def _current_async_openai_factory():
    """Resolve package-level AsyncOpenAI so legacy patch paths still work."""
    from server.core import generation as generation_package

    return getattr(generation_package, "AsyncOpenAI", AsyncOpenAI)


_SOURCE_TRANSLATION_SYSTEM_PROMPT = """你是一位精通欧洲建筑规范（Eurocode）的专家，负责把规范原文片段翻译成简洁、准确的中文解释。

规则：
1. 严格基于给定原文翻译，不补充原文没有的信息。
2. 保留关键英文术语、条款号、表格号、公式号和文件名。
3. 输出应适合直接展示在"中文解释"面板中，优先使用自然中文，不写额外说明。
4. 如果原文中包含表格、枚举、层级说明或分点要求，请优先转换成 GFM Markdown 结构：
   - 表格优先转换为 Markdown table
   - 条列内容优先转换为项目列表或有序列表
   - 普通说明保持自然段
5. 不要输出 HTML 标签，不要输出 Markdown 代码块围栏。
6. 只输出严格 json，格式如下：
{
  "translations": [
    {"index": 0, "translation": "中文解释"}
  ]
}"""


def _should_enable_prompt_cache(
    cfg: ServerConfig,
    *,
    base_url: str,
    model: str,
) -> bool:
    """Return whether this concrete LLM endpoint should receive cache markers."""
    if not cfg.llm_prompt_cache_enabled:
        return False
    return "qwen" in model.lower() or "dashscope.aliyuncs.com" in base_url.lower()


def _build_system_message(content: str, *, prompt_cache_enabled: bool) -> dict:
    if not prompt_cache_enabled:
        return {"role": "system", "content": content}
    return {
        "role": "system",
        "content": [
            {
                "type": "text",
                "text": content,
                "cache_control": {"type": "ephemeral"},
            }
        ],
    }


def _build_source_translation_prompt(
    sources: list[Source], indexes: list[int] | None = None
) -> str:
    """为缺失翻译的 source 构造批量翻译提示词。"""
    payload: list[dict[str, str | int]] = []
    selected_indexes = indexes or _collect_pending_source_indexes(sources)
    for index in selected_indexes:
        source = sources[index]
        if source.translation.strip() or not source.original_text.strip():
            continue
        payload.append(
            {
                "index": index,
                "file": source.file,
                "section": source.section,
                "clause": source.clause,
                "original_text": source.original_text,
            }
        )

    if not payload:
        return ""

    return (
        "请把以下 Eurocode 来源原文翻译成可直接展示的中文解释。"
        "如果内容中存在表格、条列或层级结构，请优先转成适合前端渲染的 Markdown。"
        "返回严格 json，不要输出额外文字。\n"
        f"{json.dumps(payload, ensure_ascii=False)}"
    )


async def _call_source_translation_llm(
    prompt: str,
    config: ServerConfig | None = None,
) -> str:
    """调用 LLM 生成 source 中文翻译。"""
    cfg = config or ServerConfig()
    api_key = cfg.translation_llm_api_key or cfg.llm_api_key
    base_url = cfg.translation_llm_base_url or cfg.llm_base_url
    model = cfg.translation_llm_model or cfg.llm_model
    system_message = _build_system_message(
        _SOURCE_TRANSLATION_SYSTEM_PROMPT,
        prompt_cache_enabled=_should_enable_prompt_cache(
            cfg,
            base_url=base_url,
            model=model,
        ),
    )
    client = await get_async_openai_client(
        api_key=api_key,
        base_url=base_url,
        timeout=httpx.Timeout(timeout=30.0, connect=5.0),
        client_factory=_current_async_openai_factory(),
    )
    response = await client.chat.completions.create(
        model=model,
        messages=[system_message, {"role": "user", "content": prompt}],
        temperature=0.0,
        response_format={"type": "json_object"},
    )
    record_usage(
        model=model,
        vendor=vendor_from_base_url(base_url),
        payload=response,
    )
    return response.choices[0].message.content.strip()


def _parse_source_translation_map(raw: str) -> dict[int, str]:
    """解析 source 翻译响应，返回 index -> translation 映射。"""
    payload = json.loads(_extract_json_text(raw))
    translation_map: dict[int, str] = {}
    for item in payload.get("translations", []):
        if not isinstance(item, dict):
            continue
        index = item.get("index")
        translation = item.get("translation")
        if isinstance(index, int) and isinstance(translation, str):
            text = translation.strip()
            if text:
                translation_map[index] = text
    return translation_map


async def _translate_source_batch(
    sources: list[Source],
    indexes: list[int],
    config: ServerConfig | None = None,
) -> dict[int, str]:
    """对指定 source 子集执行一次翻译请求。"""
    prompt = _build_source_translation_prompt(sources, indexes)
    if not prompt:
        return {}

    from server.core import generation as generation_package

    translator = getattr(
        generation_package,
        "_call_source_translation_llm",
        _call_source_translation_llm,
    )
    raw = await translator(prompt, config)
    return _parse_source_translation_map(raw)


async def _fill_missing_source_translations(
    sources: list[Source],
    config: ServerConfig | None = None,
) -> list[Source]:
    """为缺失 translation 的 source 补齐中文解释。"""
    pending_indexes = _collect_pending_source_indexes(sources)
    if not pending_indexes:
        return sources

    translation_map: dict[int, str] = {}
    try:
        translation_map = await _translate_source_batch(
            sources, pending_indexes, config
        )
    except json.JSONDecodeError:
        logger.warning(
            "source_translation_fill_batch_parse_failed_retrying_individually",
            pending_count=len(pending_indexes),
            exc_info=True,
        )
        for index in pending_indexes:
            try:
                translation_map.update(
                    await _translate_source_batch(sources, [index], config)
                )
            except Exception:
                logger.warning(
                    "source_translation_single_fill_failed",
                    source_index=index,
                    exc_info=True,
                )
    except Exception:
        logger.warning("source_translation_fill_failed", exc_info=True)
        return sources

    return [
        source.model_copy(
            update={
                "translation": source.translation.strip()
                or translation_map.get(index, "")
            }
        )
        for index, source in enumerate(sources)
    ]
