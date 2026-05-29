"""Full-agent PageIndex retrieval sandbox."""

from __future__ import annotations

import json
import os
import re
import time
from typing import Any

import structlog

from server.config import ServerConfig

from experiments.retrieval_eval.pageindex_sandbox import (
    PageIndexSandboxResult,
    PageIndexSandboxTrace,
    PageIndexWorkspace,
)
from experiments.retrieval_eval.pageindex_sandbox_utils import (
    node_trace,
    shortlist_documents,
)

logger = structlog.get_logger()

_MAX_SUMMARY_CHARS = 120

PAGEINDEX_RETRIEVAL_PROMPT = """\
You are a Eurocode document retrieval specialist. Your task is to find precise
evidence pages or markdown line ranges for an engineering question.

You receive:
- target document IDs
- the original Chinese question
- English expanded queries
- optional question-mentioned objects such as clauses, tables, annexes, or figures

Tools:
- get_document(doc_id): metadata
- get_document_structure(doc_id): full section hierarchy with line_num and summaries
- get_page_content(doc_id, pages): text for a markdown line range, e.g. "1880-1945"

Process:
1. Inspect each target document's metadata and structure.
2. Identify 2-5 candidate sections by title and summary.
3. Retrieve page/line ranges and verify whether they directly answer the question.
4. If retrieved content references Table/Figure/Expression/Annex objects needed for the answer, retrieve those objects too.
5. If the question is broad or multi-part, return multiple primary page ranges.

Final output must be only valid JSON, no markdown:
{"answer_mode":"exact|open","selection_strategy":"brief_name","insufficient_evidence":false,"primary_pages":[{"doc_id":"xxx","pages":"X-Y","relevance":"why"}],"referenced_pages":[{"doc_id":"xxx","pages":"X","ref_label":"Table X.X"}],"resolved_refs":["Table X.X"],"unresolved_refs":[],"reasoning":"brief navigation path"}
"""


class PageIndexAgentSandboxRetriever:
    """Run the PageIndex-style tool-calling agent inside the eval sandbox."""

    def __init__(
        self,
        workspace: str,
        *,
        config: ServerConfig,
        max_docs: int = 3,
        max_turns: int = 8,
    ) -> None:
        self.workspace = PageIndexWorkspace(workspace)
        self.config = config
        self.max_docs = max_docs
        self.max_turns = max_turns

    async def retrieve_with_trace(
        self,
        *,
        queries: list[str],
        original_query: str | None = None,
        filters: dict | None = None,
        requested_objects: list[str] | None = None,
        **_: Any,
    ) -> tuple[PageIndexSandboxResult, PageIndexSandboxTrace]:
        filters = filters or {}
        requested_objects = requested_objects or []
        source_filter = filters.get("source")
        shortlist = shortlist_documents(
            meta=self.workspace.documents,
            source_filter=source_filter,
            expanded_queries=queries,
            original_query=original_query,
            max_docs=self.max_docs,
        )
        agent_output = await self._run_agent(
            doc_ids=shortlist.doc_ids,
            queries=queries,
            original_query=original_query,
            requested_objects=requested_objects,
            shortlist_strategy=shortlist.strategy,
        )
        result = self._adapt_agent_output(agent_output)
        result.shortlist_strategy = shortlist.strategy
        trace = PageIndexSandboxTrace(
            queries=list(queries),
            source_filter=source_filter,
            shortlisted_doc_ids=shortlist.doc_ids,
            shortlist_strategy=shortlist.strategy,
            ranked_nodes=[],
            selected_nodes=[
                {
                    "doc_id": item.get("doc_id"),
                    "pages": item.get("pages"),
                    "relevance": item.get("relevance") or item.get("ref_label"),
                }
                for item in [
                    *list(agent_output.get("primary_pages") or []),
                    *list(agent_output.get("referenced_pages") or []),
                ]
                if isinstance(item, dict)
            ],
        )
        return result, trace

    async def close(self) -> None:
        return None

    async def _run_agent(
        self,
        *,
        doc_ids: list[str],
        queries: list[str],
        original_query: str | None,
        requested_objects: list[str],
        shortlist_strategy: str,
    ) -> dict[str, Any]:
        user_input = "\n".join(
            [
                f"Target documents: {', '.join(doc_ids)}",
                f"Original question: {original_query or ''}",
                f"Expanded queries: {'; '.join(queries)}",
                f"Shortlist strategy: {shortlist_strategy}",
                f"Question-mentioned objects: {', '.join(requested_objects)}",
            ]
        )
        try:
            from agents import Agent, MaxTurnsExceeded, RunConfig, Runner, function_tool
            from agents.models.openai_provider import OpenAIProvider
            from openai import AsyncOpenAI
        except ImportError:
            return await self._run_openai_compatible_tool_loop(user_input)

        @function_tool
        def get_document(doc_id: str) -> str:
            return json.dumps(self._document_meta(doc_id), ensure_ascii=False)

        @function_tool
        def get_document_structure(doc_id: str) -> str:
            return _compact_structure_json(
                json.dumps(self.workspace.get_structure(doc_id), ensure_ascii=False)
            )

        @function_tool
        def get_page_content(doc_id: str, pages: str) -> str:
            return json.dumps(
                self.workspace.get_line_content(doc_id, pages),
                ensure_ascii=False,
            )

        provider = OpenAIProvider(
            openai_client=AsyncOpenAI(
                base_url=self._agent_base_url(),
                api_key=self._agent_api_key() or "not-set",
            ),
            use_responses=False,
        )
        agent = Agent(
            name="EurocodePageIndexRetriever",
            instructions=PAGEINDEX_RETRIEVAL_PROMPT,
            tools=[get_document, get_document_structure, get_page_content],
            model=self._agent_model(),
        )
        started = time.perf_counter()
        try:
            result = await Runner.run(
                agent,
                input=user_input,
                max_turns=self.max_turns,
                run_config=RunConfig(model_provider=provider),
            )
        except MaxTurnsExceeded:
            return _empty_agent_output("max_turns_exceeded")
        elapsed = time.perf_counter() - started
        raw_output = str(result.final_output or "")
        parsed = parse_agent_output(raw_output)
        if parsed.get("primary_pages"):
            logger.info("pageindex_agent_sandbox_done", elapsed=f"{elapsed:.2f}s")
            return parsed
        fallback = _extract_pages_from_history(result)
        logger.info(
            "pageindex_agent_sandbox_history_fallback",
            elapsed=f"{elapsed:.2f}s",
            pages=len(fallback.get("primary_pages") or []),
        )
        return fallback

    async def _run_openai_compatible_tool_loop(self, user_input: str) -> dict[str, Any]:
        from experiments.retrieval_eval.pageindex_openai_tool_loop import run_openai_tool_loop

        def tool_fn(name: str, raw_args: str | None) -> str:
            try:
                args = json.loads(raw_args or "{}")
            except (json.JSONDecodeError, TypeError):
                args = {}
            doc_id = str(args.get("doc_id") or "")
            if name == "get_document":
                return json.dumps(self._document_meta(doc_id), ensure_ascii=False)
            if name == "get_document_structure":
                return _compact_structure_json(
                    json.dumps(self.workspace.get_structure(doc_id), ensure_ascii=False)
                )
            if name == "get_page_content":
                return json.dumps(
                    self.workspace.get_line_content(doc_id, str(args.get("pages") or "")),
                    ensure_ascii=False,
                )
            return json.dumps({"error": f"unknown tool: {name}"}, ensure_ascii=False)

        return await run_openai_tool_loop(
            base_url=self._agent_base_url(),
            api_key=self._agent_api_key(),
            model=self._agent_model(),
            instructions=PAGEINDEX_RETRIEVAL_PROMPT,
            user_input=user_input,
            max_turns=self.max_turns,
            tool_fn=tool_fn,
            parse_output=parse_agent_output,
        )

    def _adapt_agent_output(self, agent_output: dict[str, Any]) -> PageIndexSandboxResult:
        chunks = []
        scores = []
        for item in agent_output.get("primary_pages") or []:
            if not isinstance(item, dict):
                continue
            chunk = self._build_chunk_from_pages(
                str(item.get("doc_id") or ""),
                str(item.get("pages") or ""),
                score=1.0,
            )
            if chunk is not None:
                chunks.append(chunk)
                scores.append(1.0)

        ref_chunks = []
        for item in agent_output.get("referenced_pages") or []:
            if not isinstance(item, dict):
                continue
            chunk = self._build_chunk_from_pages(
                str(item.get("doc_id") or ""),
                str(item.get("pages") or ""),
                score=0.8,
                ref_label=str(item.get("ref_label") or ""),
            )
            if chunk is not None:
                ref_chunks.append(chunk)

        answer_mode = str(agent_output.get("answer_mode") or "open").lower()
        if answer_mode != "exact":
            answer_mode = "open"
        return PageIndexSandboxResult(
            chunks=chunks,
            parent_chunks=[],
            scores=scores,
            ref_chunks=ref_chunks,
            answer_mode=answer_mode,
            groundedness="grounded" if chunks else "open",
            resolved_refs=list(agent_output.get("resolved_refs") or []),
            unresolved_refs=list(agent_output.get("unresolved_refs") or []),
            selection_strategy=str(agent_output.get("selection_strategy") or "agent_tool_loop"),
            shortlist_strategy="",
            insufficient_evidence=bool(agent_output.get("insufficient_evidence", False)),
        )

    def _build_chunk_from_pages(
        self,
        doc_id: str,
        pages: str,
        *,
        score: float,
        ref_label: str = "",
    ):
        from experiments.retrieval_eval.pageindex_sandbox import PageIndexSandboxRetriever

        proxy = PageIndexSandboxRetriever.__new__(PageIndexSandboxRetriever)
        proxy.workspace = self.workspace
        nodes = _nodes_for_pages(self.workspace, doc_id, pages)
        if nodes:
            node = nodes[0]
        else:
            return None
        chunk = PageIndexSandboxRetriever._build_chunk(proxy, doc_id, node, score)
        if chunk is not None and ref_label:
            chunk.metadata.object_label = ref_label
            if ref_label not in chunk.metadata.object_aliases:
                chunk.metadata.object_aliases.append(ref_label)
        return chunk

    def _document_meta(self, doc_id: str) -> dict[str, Any]:
        doc = self.workspace.get_document(doc_id)
        return {
            "doc_id": doc_id,
            "doc_name": doc.get("doc_name", ""),
            "doc_description": doc.get("doc_description", ""),
            "type": doc.get("type", ""),
            "line_count": doc.get("line_count"),
            "page_count": doc.get("page_count"),
        }

    def _agent_base_url(self) -> str | None:
        return (
            os.getenv("PAGEINDEX_RETRIEVE_BASE_URL")
            or self.config.query_expansion_llm_base_url
            or self.config.llm_base_url
            or None
        )

    def _agent_api_key(self) -> str:
        return (
            os.getenv("PAGEINDEX_RETRIEVE_API_KEY")
            or self.config.query_expansion_llm_api_key
            or self.config.llm_api_key
        )

    def _agent_model(self) -> str:
        return (
            os.getenv("PAGEINDEX_RETRIEVE_MODEL")
            or self.config.query_expansion_llm_model
            or self.config.llm_model
        )


def parse_agent_output(raw_output: str) -> dict[str, Any]:
    """Parse final agent output into the retrieval JSON contract."""
    if not raw_output.strip():
        return _empty_agent_output("empty_output")
    cleaned = re.sub(r"^```(?:json)?\s*", "", raw_output.strip())
    cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        data = json.loads(cleaned)
        if isinstance(data, dict) and "primary_pages" in data:
            return _normalize_agent_dict(data)
    except (json.JSONDecodeError, TypeError):
        pass
    match = re.search(r"\{.*\"primary_pages\"\s*:\s*\[.*\}", cleaned, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group(0))
            if isinstance(data, dict) and "primary_pages" in data:
                return _normalize_agent_dict(data)
        except (json.JSONDecodeError, TypeError):
            pass
    return _empty_agent_output("unparsed_output")


def _normalize_agent_dict(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "answer_mode": "exact" if str(data.get("answer_mode")).lower() == "exact" else "open",
        "selection_strategy": str(data.get("selection_strategy") or "direct_tree_search"),
        "insufficient_evidence": bool(data.get("insufficient_evidence", False)),
        "primary_pages": list(data.get("primary_pages") or []),
        "referenced_pages": list(data.get("referenced_pages") or []),
        "resolved_refs": list(data.get("resolved_refs") or []),
        "unresolved_refs": list(data.get("unresolved_refs") or []),
        "reasoning": str(data.get("reasoning") or ""),
    }


def _extract_pages_from_history(result: Any) -> dict[str, Any]:
    pages: list[dict[str, str]] = []
    try:
        items = result.to_input_list()
    except Exception:
        return _empty_agent_output("history_unavailable")
    for item in items:
        if item.get("type") != "function_call" or item.get("name") != "get_page_content":
            continue
        try:
            args = json.loads(item.get("arguments", "{}"))
        except (json.JSONDecodeError, TypeError):
            continue
        doc_id = args.get("doc_id", "")
        page_range = args.get("pages", "")
        if doc_id and page_range:
            pages.append(
                {
                    "doc_id": doc_id,
                    "pages": page_range,
                    "relevance": "extracted from agent tool history",
                }
            )
    if not pages:
        return _empty_agent_output("no_tool_pages")
    return {
        "answer_mode": "open",
        "selection_strategy": "tool_history_fallback",
        "insufficient_evidence": False,
        "primary_pages": pages,
        "referenced_pages": [],
        "resolved_refs": [],
        "unresolved_refs": [],
        "reasoning": "Extracted get_page_content calls from agent history.",
    }


def _empty_agent_output(reason: str) -> dict[str, Any]:
    return {
        "answer_mode": "open",
        "selection_strategy": reason,
        "insufficient_evidence": True,
        "primary_pages": [],
        "referenced_pages": [],
        "resolved_refs": [],
        "unresolved_refs": [],
        "reasoning": reason,
    }


def _compact_structure_json(raw_json: str) -> str:
    try:
        nodes = json.loads(raw_json)
    except (json.JSONDecodeError, TypeError):
        return raw_json
    if isinstance(nodes, list):
        nodes = _compact_nodes(nodes)
    return json.dumps(nodes, ensure_ascii=False)


def _compact_nodes(nodes: list[Any]) -> list[dict[str, Any]]:
    compacted: list[dict[str, Any]] = []
    for node in nodes:
        if not isinstance(node, dict):
            continue
        compacted_node: dict[str, Any] = {}
        for key in ("title", "node_id", "line_num", "start_index", "end_index"):
            if key in node:
                compacted_node[key] = node[key]
        summary = str(node.get("summary") or "")
        if summary:
            compacted_node["summary"] = (
                summary[:_MAX_SUMMARY_CHARS] + "..."
                if len(summary) > _MAX_SUMMARY_CHARS
                else summary
            )
        children = node.get("nodes")
        if isinstance(children, list):
            compacted_node["nodes"] = _compact_nodes(children)
        compacted.append(compacted_node)
    return compacted


def _nodes_for_pages(
    workspace: PageIndexWorkspace,
    doc_id: str,
    pages: str,
) -> list[dict[str, Any]]:
    from experiments.retrieval_eval.pageindex_sandbox_utils import attach_ranges, flatten_structure, parse_page_range

    page_nums = parse_page_range(pages)
    if not page_nums:
        return []
    start, end = min(page_nums), max(page_nums)
    matches = []
    for node in attach_ranges(flatten_structure(workspace.get_structure(doc_id))):
        node_start = node.get("range_start") or node.get("line_num")
        node_end = node.get("range_end") or node_start
        if isinstance(node_start, int) and isinstance(node_end, int) and node_start <= end and node_end >= start:
            matches.append(node)
    return matches
