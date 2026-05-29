"""OpenAI-compatible tool loop for the PageIndex sandbox agent mode."""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from typing import Any

import structlog
from openai import AsyncOpenAI

logger = structlog.get_logger()

ToolFn = Callable[[str, str | None], str]


async def run_openai_tool_loop(
    *,
    base_url: str | None,
    api_key: str,
    model: str,
    instructions: str,
    user_input: str,
    max_turns: int,
    tool_fn: ToolFn,
    parse_output: Callable[[str], dict[str, Any]],
) -> dict[str, Any]:
    """Run a minimal OpenAI-compatible chat tool loop."""
    client = AsyncOpenAI(base_url=base_url, api_key=api_key or "not-set")
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": instructions},
        {"role": "user", "content": user_input},
    ]
    called_pages: list[dict[str, str]] = []
    started = time.perf_counter()
    for _ in range(max_turns):
        response = await client.chat.completions.create(
            model=model,
            messages=messages,
            tools=_tool_schemas(),
            tool_choice="auto",
            temperature=0,
        )
        message = response.choices[0].message
        messages.append(message.model_dump(exclude_none=True))
        tool_calls = message.tool_calls or []
        if not tool_calls:
            parsed = parse_output(message.content or "")
            if parsed.get("primary_pages"):
                logger.info(
                    "pageindex_openai_tool_loop_done",
                    elapsed=f"{time.perf_counter() - started:.2f}s",
                )
                return parsed
            fallback = _fallback_from_called_pages(called_pages, "openai_tool_history_fallback")
            return fallback if fallback.get("primary_pages") else parsed
        for call in tool_calls:
            args = _load_args(call.function.arguments)
            name = call.function.name
            doc_id = str(args.get("doc_id") or "")
            pages = str(args.get("pages") or "") if name == "get_page_content" else None
            content = tool_fn(name, json.dumps(args, ensure_ascii=False))
            if name == "get_page_content" and doc_id and pages:
                called_pages.append(
                    {
                        "doc_id": doc_id,
                        "pages": pages,
                        "relevance": "extracted from OpenAI-compatible tool history",
                    }
                )
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": content,
                }
            )
    return _fallback_from_called_pages(called_pages, "openai_tool_loop_max_turns")


def _load_args(raw_args: str | None) -> dict[str, Any]:
    try:
        data = json.loads(raw_args or "{}")
    except (json.JSONDecodeError, TypeError):
        return {}
    return data if isinstance(data, dict) else {}


def _fallback_from_called_pages(pages: list[dict[str, str]], reason: str) -> dict[str, Any]:
    return {
        "answer_mode": "open",
        "selection_strategy": reason,
        "insufficient_evidence": not bool(pages),
        "primary_pages": pages,
        "referenced_pages": [],
        "resolved_refs": [],
        "unresolved_refs": [],
        "reasoning": "Extracted get_page_content calls from OpenAI-compatible tool history.",
    }


def _tool_schemas() -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": "get_document",
                "description": "Return metadata for a PageIndex document.",
                "parameters": {
                    "type": "object",
                    "properties": {"doc_id": {"type": "string"}},
                    "required": ["doc_id"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_document_structure",
                "description": "Return compact structure tree for a PageIndex document.",
                "parameters": {
                    "type": "object",
                    "properties": {"doc_id": {"type": "string"}},
                    "required": ["doc_id"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_page_content",
                "description": "Return text for a document line range.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "doc_id": {"type": "string"},
                        "pages": {"type": "string"},
                    },
                    "required": ["doc_id", "pages"],
                    "additionalProperties": False,
                },
            },
        },
    ]
