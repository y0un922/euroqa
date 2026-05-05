"""混合检索层：向量检索 + BM25 + 重排序 + 父文档检索 + 交叉引用补充。"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import structlog

from shared.elasticsearch_client import build_async_elasticsearch
from shared.model_clients import build_embedding_client, build_rerank_client
from shared.reference_graph import build_object_id, classify_reference_label, normalize_reference_label
from server.config import ServerConfig
from server.models.schemas import Chunk, ChunkMetadata, GuideHint, QuestionType

if TYPE_CHECKING:
    from elasticsearch import AsyncElasticsearch
    from pymilvus import Collection

logger = structlog.get_logger()

# 匹配规范内部交叉引用：Table 3.1, Figure 5.7, Expression (3.14), Annex B 等
_INTERNAL_REF_RE = re.compile(
    r"\b(?:Table|Figure|Expression)\s*[\(\[]?\d+[\.\d]*[\)\]]?"
    r"|\bAnnex\s+[A-Z]\d*",
    re.IGNORECASE,
)
_LOW_VALUE_EXACT_SIGNALS = (
    "foreword",
    "additional information",
    "national annex",
)
_CLAUSE_TOKEN_RE = re.compile(
    r"(?:[a-z]\.)?\d+(?:\.\d+)*(?:[a-z])?(?:\(\d+\))?(?:[a-z])?",
    re.IGNORECASE,
)
_SOURCE_DOC_RE = re.compile(
    r"(?<![A-Za-z0-9])en\s*([0-9]{4}(?:-[0-9]+(?:-[0-9]+)?)?)"
    r"(?:[\s:_-]*([0-9]{4}))?(?![A-Za-z0-9])",
    re.IGNORECASE,
)
_GUIDE_EXAMPLE_MARKERS = (
    "worked example",
    "illustrative example",
    "design example",
    "calculation example",
    "算例",
)
_GUIDE_PROCEDURE_MARKERS = (
    "procedure",
    "calculation procedure",
    "calculation process",
    "step",
    "steps",
    "演算",
    "步骤",
)
_GUIDE_COMMENTARY_MARKERS = (
    "commentary",
    "explanation",
    "commentary to clause",
)
_GUIDE_DOCUMENT_MARKERS = (
    "designer's guide",
    "designers guide",
    "designers' guide",
    "design guide",
    "guide",
    "guidance",
    "commentary",
    "handbook",
    "manual",
    "指南",
)
_GUIDE_SEARCH_FIELDS = [
    "content",
    "embedding_text",
    "source_title^3",
    "source^2",
]


@dataclass
class RetrievalResult:
    """检索结果，包含最终 chunk、父 chunk、交叉引用 chunk 和重排序分数。"""

    chunks: list[Chunk]
    parent_chunks: list[Chunk]
    scores: list[float]
    guide_chunks: list[Chunk] = field(default_factory=list)
    guide_example_chunks: list[Chunk] = field(default_factory=list)
    ref_chunks: list[Chunk] = field(default_factory=list)
    groundedness: str = "open"
    anchor_chunk_ids: list[str] = field(default_factory=list)
    exact_probe_used: bool = False
    resolved_refs: list[str] = field(default_factory=list)
    unresolved_refs: list[str] = field(default_factory=list)


class HybridRetriever:
    """混合检索器：结合向量检索与 BM25，经重排序后返回结果。

    各外部依赖（嵌入模型、重排序器、ES、Milvus）均采用懒初始化，
    避免在构建时即加载大型模型或建立网络连接。
    """

    def __init__(self, config: ServerConfig) -> None:
        self.config = config
        self._embedding_client = build_embedding_client(config)
        self._rerank_client = build_rerank_client(config)
        self._es: AsyncElasticsearch | None = None
        self._collection: Collection | None = None

    # ------------------------------------------------------------------
    # 运行时延迟导入辅助
    # ------------------------------------------------------------------

    @staticmethod
    def _import_milvus() -> tuple[type, Any]:
        """延迟导入 pymilvus。"""
        from pymilvus import Collection, connections

        return Collection, connections

    # ------------------------------------------------------------------
    # 懒初始化属性
    # ------------------------------------------------------------------

    async def _get_es(self) -> AsyncElasticsearch:
        """获取或创建 ES 异步客户端。"""
        if self._es is None:
            self._es = build_async_elasticsearch(self.config.es_url)
        return self._es

    def _get_collection(self) -> Collection:
        """获取或创建 Milvus Collection（同时建立连接并加载数据）。"""
        if self._collection is None:
            collection_cls, milvus_connections = self._import_milvus()
            milvus_connections.connect(
                host=self.config.milvus_host,
                port=self.config.milvus_port,
            )
            self._collection = collection_cls(self.config.milvus_collection)
            self._collection.load()
        return self._collection

    # ------------------------------------------------------------------
    # 检索子步骤
    # ------------------------------------------------------------------

    async def _vector_search(
        self, query: str, top_k: int, filters: dict
    ) -> list[dict]:
        """使用 BGE-M3 编码查询，在 Milvus 中进行向量近似搜索。"""
        embedding = (await self._embedding_client.embed_texts([query]))[0]
        collection = self._get_collection()

        # 构造 Milvus 布尔过滤表达式（不含 element_type，已改为 boost）
        expr_parts: list[str] = []
        if "source" in filters:
            source_expr = self._build_milvus_source_expr(filters["source"])
            if source_expr:
                expr_parts.append(source_expr)
        expr = " and ".join(expr_parts) if expr_parts else None

        results = collection.search(
            data=[embedding],
            anns_field="embedding",
            param={"metric_type": "COSINE", "params": {"ef": 128}},
            limit=top_k,
            expr=expr,
            output_fields=["chunk_id", "source", "element_type"],
        )

        results = [
            {
                "chunk_id": hit.entity.get("chunk_id"),
                "source": hit.entity.get("source"),
                "score": hit.score,
            }
            for hit in results[0]
        ]
        return self._filter_results_by_source(results, filters)

    async def _bm25_search(
        self,
        query: str,
        top_k: int,
        filters: dict,
        fields: list[str] | None = None,
        preferred_element_type: str | None = None,
    ) -> list[dict]:
        """在 Elasticsearch 中使用 multi_match 进行 BM25 全文检索。"""
        es = await self._get_es()
        search_fields = fields or ["content", "embedding_text"]

        must_clauses = [
            {
                "multi_match": {
                    "query": query,
                    "fields": search_fields,
                }
            }
        ]
        filter_clauses = self._build_source_filter_clauses(filters)

        # element_type 作为 should boost 而非 filter，
        # 偏好匹配类型的 chunk 但不排除其他类型
        should_clauses: list[dict] = []
        if preferred_element_type:
            should_clauses.append(
                {"term": {"element_type": {"value": preferred_element_type, "boost": 2.0}}}
            )

        body = {
            "query": {
                "bool": {
                    "must": must_clauses,
                    "filter": filter_clauses,
                    "should": should_clauses,
                }
            },
            "size": top_k,
        }
        resp = await es.search(index=self.config.es_index, body=body)

        return [
            {
                "chunk_id": hit["_id"],
                "source": hit["_source"].get("source", ""),
                "score": hit["_score"],
            }
            for hit in resp["hits"]["hits"]
        ]

    # ------------------------------------------------------------------
    # 合并、聚合、重排序
    # ------------------------------------------------------------------

    def _merge_results(
        self,
        vec_results: list[dict],
        bm25_results: list[dict],
    ) -> list[dict]:
        """合并向量检索和 BM25 结果并去重，向量结果优先。"""
        seen: set[str] = set()
        merged: list[dict] = []

        primary, secondary = vec_results, bm25_results

        for result in primary:
            cid = result["chunk_id"]
            if cid not in seen:
                seen.add(cid)
                merged.append(result)

        for result in secondary:
            cid = result["chunk_id"]
            if cid not in seen:
                seen.add(cid)
                merged.append(result)

        return merged

    def _cross_doc_aggregate(
        self,
        results: list[dict],
        max_per_source: int = 5,
        filters: dict | None = None,
    ) -> list[dict]:
        """跨文档聚合：限制每个来源文档的最大 chunk 数量，确保结果多样性。"""
        filters = filters or {}
        unique_sources = {result.get("source", "") for result in results}
        if "source" in filters or len(unique_sources) <= 1:
            return results

        source_counts: dict[str, int] = {}
        aggregated: list[dict] = []

        for result in results:
            src = result.get("source", "")
            count = source_counts.get(src, 0)
            if count < max_per_source:
                aggregated.append(result)
                source_counts[src] = count + 1

        return aggregated

    @staticmethod
    def _append_unique_results(
        primary_results: list[dict],
        supplemental_results: list[dict],
    ) -> list[dict]:
        """Append supplemental candidates without disturbing primary ordering."""
        seen = {result["chunk_id"] for result in primary_results}
        merged = list(primary_results)
        for result in supplemental_results:
            chunk_id = result["chunk_id"]
            if chunk_id not in seen:
                seen.add(chunk_id)
                merged.append(result)
        return merged

    @staticmethod
    def _normalize_target_hint(target_hint: Any) -> dict[str, str]:
        """将 target_hint 归一化为纯字符串字典。"""
        if target_hint is None:
            return {}

        if isinstance(target_hint, dict):
            raw_items = target_hint.items()
        else:
            raw_items = (
                (key, getattr(target_hint, key, None))
                for key in ("document", "clause", "object")
            )

        normalized: dict[str, str] = {}
        for key, value in raw_items:
            if isinstance(value, str):
                stripped = value.strip()
                if stripped:
                    normalized[key] = stripped
        return normalized

    @staticmethod
    def _object_reference_key(object_id: str) -> str:
        return object_id.split("#", 1)[-1].strip().lower() if object_id else ""

    @staticmethod
    def _collect_object_ids(chunks: list[Chunk]) -> set[str]:
        return {
            chunk.metadata.object_id
            for chunk in chunks
            if chunk.metadata.object_id
        }

    @staticmethod
    def _collect_ref_object_ids(chunks: list[Chunk]) -> set[str]:
        object_ids: set[str] = set()
        for chunk in chunks:
            object_ids.update(
                object_id
                for object_id in chunk.metadata.ref_object_ids
                if object_id
            )
        return object_ids

    @classmethod
    def _collect_object_keys(cls, chunks: list[Chunk]) -> set[str]:
        return {
            cls._object_reference_key(chunk.metadata.object_id)
            for chunk in chunks
            if chunk.metadata.object_id
        }

    @staticmethod
    def _build_object_id_label_map(
        chunks: list[Chunk],
        requested_objects: list[str],
        lookup_source: str,
    ) -> dict[str, str]:
        labels_by_id: dict[str, str] = {}

        for chunk in chunks:
            if chunk.metadata.object_id and chunk.metadata.object_label:
                labels_by_id.setdefault(chunk.metadata.object_id, chunk.metadata.object_label)

        for chunk in chunks:
            for label, object_id in zip(
                chunk.metadata.ref_labels,
                chunk.metadata.ref_object_ids,
                strict=False,
            ):
                if object_id and label and object_id not in labels_by_id:
                    labels_by_id[object_id] = label

        for label in requested_objects:
            ref_type = classify_reference_label(label)
            if ref_type is None or not lookup_source:
                continue
            object_id = build_object_id(lookup_source, ref_type, label)
            labels_by_id.setdefault(object_id, label)

        return labels_by_id

    @staticmethod
    def _should_require_reference_closure(object_key: str, requested_object_keys: set[str]) -> bool:
        if object_key in requested_object_keys:
            return True
        return object_key.startswith(("table:", "expression:", "annex:"))

    @classmethod
    def _should_promote_exact_ref_chunk(
        cls,
        chunk: Chunk,
        required_object_keys: set[str],
        requested_object_keys: set[str],
    ) -> bool:
        object_key = cls._object_reference_key(chunk.metadata.object_id)
        if not object_key or object_key not in required_object_keys:
            return False
        if object_key in requested_object_keys:
            return True
        return (chunk.metadata.object_type or "").lower() in {"table", "expression", "annex"}

    @classmethod
    def _promote_exact_ref_chunks(
        cls,
        chunks: list[Chunk],
        scores: list[float],
        ref_chunks: list[Chunk],
        required_object_keys: set[str],
        requested_object_keys: set[str],
    ) -> tuple[list[Chunk], list[float], list[Chunk]]:
        if not chunks or not ref_chunks:
            return chunks, scores, ref_chunks

        seen_ids = {chunk.chunk_id for chunk in chunks}
        promoted: list[Chunk] = []
        remaining: list[Chunk] = []
        for chunk in ref_chunks:
            if chunk.chunk_id in seen_ids:
                continue
            if cls._should_promote_exact_ref_chunk(
                chunk,
                required_object_keys,
                requested_object_keys,
            ):
                seen_ids.add(chunk.chunk_id)
                promoted.append(chunk)
            else:
                remaining.append(chunk)

        if not promoted:
            return chunks, scores, ref_chunks

        insert_at = 1 if (chunks[0].metadata.object_type or "").lower() == "clause" else 0
        base_score = scores[0] if scores else 0.0
        promoted_scores = [max(base_score - (index + 1) * 0.001, 0.0) for index, _ in enumerate(promoted)]
        merged_chunks = chunks[:insert_at] + promoted + chunks[insert_at:]
        merged_scores = scores[:insert_at] + promoted_scores + scores[insert_at:]
        return merged_chunks, merged_scores, remaining

    @classmethod
    def _prune_shadowed_requested_object_ids(cls, object_ids: set[str]) -> set[str]:
        explicit_object_keys = {
            object_key.split(":", 1)[1]
            for object_id in object_ids
            if (object_key := cls._object_reference_key(object_id))
            and not object_key.startswith("clause:")
            and ":" in object_key
        }
        return {
            object_id
            for object_id in object_ids
            if not (
                (object_key := cls._object_reference_key(object_id)).startswith("clause:")
                and object_key.split(":", 1)[1] in explicit_object_keys
            )
        }

    @staticmethod
    def _display_label_for_object_id(object_id: str) -> str:
        suffix = object_id.split("#", 1)[-1]
        if ":" not in suffix:
            return object_id
        object_type, key = suffix.split(":", 1)
        if object_type == "table":
            return f"Table {key}"
        if object_type == "figure":
            return f"Figure {key}"
        if object_type == "expression":
            return f"Expression ({key})"
        if object_type == "annex":
            return f"Annex {key.upper()}"
        if object_type == "clause":
            return key
        return object_id

    @staticmethod
    def _parse_source_reference(value: str) -> tuple[str, str]:
        match = _SOURCE_DOC_RE.search(value or "")
        if not match:
            return "", ""
        return match.group(1), match.group(2) or ""

    @classmethod
    def _source_aliases(cls, value: str) -> list[str]:
        candidate = (value or "").strip()
        if not candidate:
            return []

        aliases: list[str] = [candidate]
        code, year = cls._parse_source_reference(candidate)
        if not code:
            return aliases

        base_forms = [f"EN {code}", f"EN{code}"]
        if year:
            for base in base_forms:
                aliases.extend(
                    [
                        f"{base}:{year}",
                        f"{base} {year}",
                        f"{base}_{year}",
                    ]
                )
        else:
            aliases.extend(base_forms)

        deduped: list[str] = []
        seen: set[str] = set()
        for alias in aliases:
            normalized = alias.strip()
            if normalized and normalized not in seen:
                seen.add(normalized)
                deduped.append(normalized)
        return deduped

    @classmethod
    def _build_source_filter_clauses(cls, filters: dict | None) -> list[dict]:
        filters = filters or {}
        filter_clauses: list[dict] = []

        if "source" in filters:
            aliases = cls._source_aliases(filters["source"])
            code, year = cls._parse_source_reference(filters["source"])
            should_clauses = [{"term": {"source": alias}} for alias in aliases]
            if code and not year:
                should_clauses.append({"wildcard": {"source": f"*{code}*"}})
            filter_clauses.append(
                {
                    "bool": {
                        "should": should_clauses,
                        "minimum_should_match": 1,
                    }
                }
            )

        if "sources" in filters:
            filter_clauses.append({"terms": {"source": filters["sources"]}})

        return filter_clauses

    @classmethod
    def _build_milvus_source_expr(cls, source: str) -> str | None:
        aliases = cls._source_aliases(source)
        code, year = cls._parse_source_reference(source)
        if not aliases:
            return None
        if not code:
            return f'source == "{source}"'
        if not year:
            return None
        if len(aliases) == 1:
            return f'source == "{aliases[0]}"'
        quoted = ", ".join(f'"{alias}"' for alias in aliases)
        return f"source in [{quoted}]"

    @classmethod
    def _source_matches_filter(cls, source: str, expected: str) -> bool:
        """Return whether an indexed source satisfies a user-facing source filter."""

        normalized_source = source.strip()
        aliases = cls._source_aliases(expected)
        code, year = cls._parse_source_reference(expected)
        if normalized_source in aliases:
            return True
        if code and not year:
            source_code, _ = cls._parse_source_reference(normalized_source)
            return source_code == code or source_code.startswith(f"{code}-")
        return False

    @classmethod
    def _filter_results_by_source(
        cls,
        results: list[dict],
        filters: dict | None,
    ) -> list[dict]:
        """Apply source filters to result rows that were not filtered by backend expr."""

        filters = filters or {}
        if "source" in filters:
            return [
                result
                for result in results
                if cls._source_matches_filter(str(result.get("source") or ""), filters["source"])
            ]
        if "sources" in filters:
            allowed = set(filters["sources"])
            return [
                result
                for result in results
                if result.get("source") in allowed
            ]
        return results

    @classmethod
    def _is_object_like_clause_metadata(cls, value: str) -> bool:
        normalized = normalize_reference_label(value)
        ref_type = classify_reference_label(normalized)
        return ref_type in {"table", "figure", "expression", "annex"}

    @staticmethod
    def _is_plain_numeric_clause_token(value: str) -> bool:
        return bool(re.fullmatch(r"\d+(?:\.\d+)+", value))

    @classmethod
    def _build_clause_token_candidates(
        cls,
        chunk: Chunk,
        expected_tokens: set[str],
    ) -> set[str]:
        allow_object_like_values = any(
            not cls._is_plain_numeric_clause_token(token)
            for token in expected_tokens
        )
        clause_tokens: set[str] = set()
        for value in (
            chunk.metadata.source_title,
            *chunk.metadata.section_path,
            *chunk.metadata.clause_ids,
        ):
            if not allow_object_like_values and cls._is_object_like_clause_metadata(value):
                continue
            clause_tokens.update(cls._extract_clause_tokens(value))
        return clause_tokens

    @classmethod
    def _lookup_aliases_for_object_id(cls, object_id: str) -> tuple[str, list[str]]:
        suffix = object_id.split("#", 1)[-1]
        if ":" not in suffix:
            return "", []
        object_type, key = suffix.split(":", 1)
        if object_type == "table":
            return object_type, [f"Table {key}"]
        if object_type == "figure":
            return object_type, [f"Figure {key}"]
        if object_type == "expression":
            return object_type, [f"Expression ({key})"]
        if object_type == "annex":
            return object_type, [f"Annex {key.upper()}"]
        if object_type == "clause":
            return object_type, [key, f"Clause {key}", f"Section {key}"]
        return object_type, []

    def _build_requested_object_ids(
        self,
        requested_objects: list[str],
        filters: dict,
        target_hint: Any,
    ) -> tuple[set[str], str]:
        normalized_hint = self._normalize_target_hint(target_hint)
        lookup_source = filters.get("source") or normalized_hint.get("document", "")
        if not lookup_source:
            return set(), ""

        object_ids: set[str] = set()
        for label in requested_objects:
            ref_type = classify_reference_label(label)
            if ref_type is None:
                continue
            object_ids.add(build_object_id(lookup_source, ref_type, label))
        return self._prune_shadowed_requested_object_ids(object_ids), lookup_source

    @staticmethod
    def _is_exact_mode(answer_mode: str | None) -> bool:
        return isinstance(answer_mode, str) and answer_mode.strip().lower() == "exact"

    @staticmethod
    def _normalize_question_type(question_type: str | QuestionType | None) -> str | None:
        if isinstance(question_type, QuestionType):
            return question_type.value
        if isinstance(question_type, str):
            normalized = question_type.strip().lower()
            return normalized or None
        return None

    @staticmethod
    def _normalize_guide_hint(
        guide_hint: GuideHint | dict[str, Any] | None,
    ) -> GuideHint | None:
        if isinstance(guide_hint, GuideHint):
            return guide_hint
        if isinstance(guide_hint, dict):
            try:
                return GuideHint.model_validate(guide_hint)
            except Exception:
                logger.warning("guide_hint_validation_failed", exc_info=True)
        return None

    @classmethod
    def _should_fetch_guide_chunks(
        cls,
        question_type: str | QuestionType | None,
        guide_hint: GuideHint | dict[str, Any] | None = None,
    ) -> bool:
        normalized_qt = cls._normalize_question_type(question_type)
        normalized_hint = cls._normalize_guide_hint(guide_hint)
        return normalized_qt in {"calculation", "parameter"} or bool(
            normalized_hint and normalized_hint.need_example
        )

    @staticmethod
    def _build_guide_queries(
        queries: list[str],
        original_query: str | None,
        extra_queries: list[str] | None = None,
    ) -> list[str]:
        deduped: list[str] = []
        for query in [*(extra_queries or []), original_query, *queries[:2]]:
            normalized = (query or "").strip()
            if normalized and normalized not in deduped:
                deduped.append(normalized)
        return deduped

    @classmethod
    def _is_guide_chunk(cls, chunk: Chunk) -> bool:
        meta = chunk.metadata
        haystacks = (
            meta.source.lower(),
            meta.source_title.lower(),
            " ".join(meta.section_path).lower(),
            " ".join(meta.clause_ids).lower(),
        )
        return any(
            marker in haystack
            for marker in _GUIDE_DOCUMENT_MARKERS
            for haystack in haystacks
        )

    @classmethod
    def _filter_guide_candidates(cls, chunks: list[Chunk]) -> list[Chunk]:
        return [chunk for chunk in chunks if cls._is_guide_chunk(chunk)]

    @classmethod
    def _split_normative_and_guide_chunks(
        cls,
        chunks: list[Chunk],
        scores: list[float],
    ) -> tuple[list[Chunk], list[float], list[Chunk]]:
        normative_chunks: list[Chunk] = []
        normative_scores: list[float] = []
        guide_chunks: list[Chunk] = []
        for index, chunk in enumerate(chunks):
            if cls._is_guide_chunk(chunk):
                guide_chunks.append(chunk)
                continue
            normative_chunks.append(chunk)
            normative_scores.append(scores[index] if index < len(scores) else 0.0)

        return normative_chunks, normative_scores, guide_chunks

    @staticmethod
    def _append_unique_chunks(
        existing_chunks: list[Chunk],
        new_chunks: list[Chunk],
    ) -> list[Chunk]:
        seen = {chunk.chunk_id for chunk in existing_chunks}
        merged = list(existing_chunks)
        for chunk in new_chunks:
            if chunk.chunk_id in seen:
                continue
            seen.add(chunk.chunk_id)
            merged.append(chunk)
        return merged

    def _guide_search_top_k(self, minimum: int = 12, maximum: int = 30) -> int:
        return min(max(self.config.vector_top_k * 3, minimum), maximum)

    @classmethod
    def _score_guide_example_chunk(
        cls,
        chunk: Chunk,
        guide_hint: GuideHint | None = None,
    ) -> int:
        meta = chunk.metadata
        section_text = " ".join(meta.section_path).lower()
        clause_text = " ".join(meta.clause_ids).lower()
        title_text = meta.source_title.lower()
        content_text = chunk.content[:1200].lower()

        strong_haystacks = (section_text, clause_text, title_text)
        all_haystacks = (*strong_haystacks, content_text)
        score = 0

        if any(marker in hay for marker in _GUIDE_EXAMPLE_MARKERS for hay in strong_haystacks):
            score += 8
        elif any(marker in hay for marker in _GUIDE_EXAMPLE_MARKERS for hay in all_haystacks):
            score += 5

        if any(marker in hay for marker in _GUIDE_PROCEDURE_MARKERS for hay in strong_haystacks):
            score += 4
        elif any(marker in hay for marker in _GUIDE_PROCEDURE_MARKERS for hay in all_haystacks):
            score += 2

        if guide_hint and guide_hint.example_kind:
            preferred_kind = guide_hint.example_kind.lower()
            if preferred_kind == "worked_example" and score >= 5:
                score += 2
            elif preferred_kind == "procedure" and any(
                marker in hay
                for marker in _GUIDE_PROCEDURE_MARKERS
                for hay in all_haystacks
            ):
                score += 2
            elif preferred_kind == "commentary" and any(
                marker in hay
                for marker in _GUIDE_COMMENTARY_MARKERS
                for hay in all_haystacks
            ):
                score += 1

        return score

    async def _retrieve_guide_chunks(
        self,
        queries: list[str],
        original_query: str | None,
    ) -> list[Chunk]:
        guide_filters: dict[str, Any] = {}
        candidate_results: list[dict] = []
        guide_queries = self._build_guide_queries(queries, original_query)

        if not guide_queries:
            return []

        for query in guide_queries:
            try:
                vec = await self._vector_search(
                    query,
                    self._guide_search_top_k(),
                    guide_filters,
                )
                candidate_results = self._append_unique_results(candidate_results, vec)
            except Exception:
                logger.warning("guide_vector_search_failed", query=query[:80])

            try:
                bm25 = await self._bm25_search(
                    query,
                    min(max(self.config.bm25_top_k * 3, 12), 30),
                    guide_filters,
                    fields=_GUIDE_SEARCH_FIELDS,
                )
                candidate_results = self._append_unique_results(candidate_results, bm25)
            except Exception:
                logger.warning("guide_bm25_search_failed", query=query[:80])

        if not candidate_results:
            return []

        guide_chunk_ids = [result["chunk_id"] for result in candidate_results]
        guide_candidates = self._filter_guide_candidates(
            await self._fetch_chunks(guide_chunk_ids)
        )
        if not guide_candidates:
            return []

        rerank_query = (original_query or guide_queries[0]).strip()
        try:
            reranked = await self._rerank(rerank_query, guide_candidates, min(3, len(guide_candidates)))
            return [chunk for chunk, _ in reranked]
        except Exception:
            logger.warning("guide_rerank_failed", exc_info=True)
            return guide_candidates[:3]

    async def _retrieve_guide_example_chunks(
        self,
        queries: list[str],
        original_query: str | None,
        guide_hint: GuideHint | dict[str, Any] | None,
    ) -> list[Chunk]:
        normalized_hint = self._normalize_guide_hint(guide_hint)
        if not normalized_hint or not normalized_hint.need_example:
            return []

        guide_filters: dict[str, Any] = {}
        candidate_results: list[dict] = []
        guide_queries = self._build_guide_queries(
            queries,
            original_query,
            extra_queries=[normalized_hint.example_query] if normalized_hint.example_query else None,
        )
        if not guide_queries:
            return []

        for query in guide_queries:
            try:
                vec = await self._vector_search(
                    query,
                    self._guide_search_top_k(),
                    guide_filters,
                )
                candidate_results = self._append_unique_results(candidate_results, vec)
            except Exception:
                logger.warning("guide_example_vector_search_failed", query=query[:80])

            try:
                bm25 = await self._bm25_search(
                    query,
                    min(max(self.config.bm25_top_k * 3, 12), 30),
                    guide_filters,
                    fields=_GUIDE_SEARCH_FIELDS,
                )
                candidate_results = self._append_unique_results(candidate_results, bm25)
            except Exception:
                logger.warning("guide_example_bm25_search_failed", query=query[:80])

        if not candidate_results:
            return []

        guide_chunk_ids = [result["chunk_id"] for result in candidate_results]
        guide_candidates = self._filter_guide_candidates(
            await self._fetch_chunks(guide_chunk_ids)
        )
        if not guide_candidates:
            return []

        rerank_query = (
            normalized_hint.example_query
            or (original_query or "").strip()
            or guide_queries[0]
        )
        rerank_scores: dict[str, float] = {}
        try:
            reranked = await self._rerank(rerank_query, guide_candidates, len(guide_candidates))
            rerank_scores = {chunk.chunk_id: score for chunk, score in reranked}
        except Exception:
            logger.warning("guide_example_rerank_failed", exc_info=True)

        ranked_candidates = sorted(
            guide_candidates,
            key=lambda chunk: (
                self._score_guide_example_chunk(chunk, normalized_hint),
                rerank_scores.get(chunk.chunk_id, 0.0),
            ),
            reverse=True,
        )
        filtered_candidates = [
            chunk
            for chunk in ranked_candidates
            if self._score_guide_example_chunk(chunk, normalized_hint) > 0
        ]
        return filtered_candidates[:3]

    async def _run_exact_probe(
        self,
        queries: list[str],
        original_query: str | None,
        filters: dict,
        target_hint: Any = None,
        intent_label: str | None = None,
    ) -> list[dict]:
        """对 exact 问题执行高精度 probe，优先 clause/title/object 信号。"""
        normalized_hint = self._normalize_target_hint(target_hint)
        probe_queries: list[str] = []

        document = normalized_hint.get("document")
        clause = normalized_hint.get("clause")
        obj = normalized_hint.get("object")
        if document and clause and obj:
            probe_queries.append(f"{document} {clause} {obj}")
        if clause and obj:
            probe_queries.append(f"{clause} {obj}")
        if document and clause:
            probe_queries.append(f"{document} {clause}")
        if obj:
            probe_queries.append(obj)
        if clause:
            probe_queries.append(clause)
        if not document and not clause:
            probe_queries.extend(self._probe_anchor_queries_for_intent(intent_label))
        if original_query:
            probe_queries.append(original_query.strip())
        if queries:
            probe_queries.append(queries[0])

        deduped_queries: list[str] = []
        seen: set[str] = set()
        for query in probe_queries:
            normalized = query.strip()
            if normalized and normalized not in seen:
                seen.add(normalized)
                deduped_queries.append(normalized)

        results: list[dict] = []
        if clause:
            try:
                results = self._append_unique_results(
                    results,
                    await self._run_exact_clause_metadata_probe(clause, filters),
                )
            except Exception:
                logger.warning("exact_probe_clause_metadata_failed", clause=clause[:40])

        exact_fields = [
            "source^6",
            "clause_ids^8",
            "section_path^7",
            "source_title^4",
            "content^2",
            "embedding_text",
        ]
        for query in deduped_queries:
            try:
                matches = await self._bm25_search(
                    query,
                    self.config.bm25_top_k,
                    filters,
                    fields=exact_fields,
                )
                results = self._append_unique_results(results, matches)
            except Exception:
                logger.warning("exact_probe_bm25_failed", query=query[:80])

        return results

    async def _run_exact_clause_metadata_probe(
        self,
        clause: str,
        filters: dict,
    ) -> list[dict]:
        """针对 keyword 元数据字段执行条款号定向检索。"""
        es = await self._get_es()
        filter_clauses = self._build_source_filter_clauses(filters)

        should_clauses = [
            {"term": {"clause_ids": clause}},
            {"wildcard": {"clause_ids": f"{clause}*"}},
            {"wildcard": {"section_path": f"{clause}*"}},
            {"wildcard": {"section_path": f"*{clause}*"}},
        ]
        body = {
            "query": {
                "bool": {
                    "should": should_clauses,
                    "minimum_should_match": 1,
                    "filter": filter_clauses,
                }
            },
            "size": self.config.bm25_top_k,
        }
        resp = await es.search(index=self.config.es_index, body=body)
        return [
            {
                "chunk_id": hit["_id"],
                "source": hit["_source"].get("source", ""),
                "score": hit["_score"],
            }
            for hit in resp["hits"]["hits"]
        ]

    @staticmethod
    def _anchor_patterns_for_intent(intent_label: str | None) -> tuple[str, ...]:
        mapping = {
            "definition": (
                " is defined as ",
                " is the ",
                " means ",
                " refers to ",
                "for the purpose of this standard",
            ),
            "assumption": (
                "the following assumptions are made",
                "plane sections remain plane",
                "is ignored",
            ),
            "applicability": (
                "this section applies to",
                "this clause applies to",
                "shall apply to",
                "is applicable to",
            ),
            "formula": ("expression (", "equation", "formula"),
            "limit": ("shall be limited to", "shall not exceed", "may be taken as"),
            "clause_lookup": (),
        }
        key = (intent_label or "").strip().lower()
        return mapping.get(key, ())

    @staticmethod
    def _probe_anchor_queries_for_intent(intent_label: str | None) -> tuple[str, ...]:
        mapping = {
            "assumption": (
                "the following assumptions are made",
                "plane sections remain plane",
                "tensile strength of the concrete is ignored",
            ),
            "definition": (
                "is defined as",
                "for the purpose of this standard",
            ),
            "applicability": (
                "this section applies to",
                "this clause applies to",
            ),
            "limit": (
                "shall be limited to",
                "shall not exceed",
            ),
        }
        key = (intent_label or "").strip().lower()
        return mapping.get(key, ())

    @staticmethod
    def _normalize_document_token(value: str) -> str:
        """归一化规范文档名，消除空格、冒号、下划线等格式差异。"""
        return re.sub(r"[^a-z0-9]+", "", value.lower())

    @staticmethod
    def _extract_clause_tokens(*values: str) -> set[str]:
        """从标题、section_path、clause_ids 中提取规范条款编号。"""
        tokens: set[str] = set()
        for value in values:
            tokens.update(_CLAUSE_TOKEN_RE.findall(value.lower()))
        return tokens

    @staticmethod
    def _clause_token_matches(token: str, expected: str) -> bool:
        if token == expected:
            return True
        if token.startswith(f"{expected}.") or token.startswith(f"{expected}("):
            return True
        if token.startswith(expected):
            suffix = token[len(expected):]
            return len(suffix) == 1 and suffix.isalpha()
        return False

    @classmethod
    def _document_matches_hint(cls, chunk: Chunk, document: str) -> bool:
        """宽松匹配 target hint 的规范文档名。"""
        if not document:
            return False

        expected = cls._normalize_document_token(document)
        if not expected:
            return False

        candidates = (
            chunk.metadata.source,
            chunk.metadata.source_title,
        )
        for candidate in candidates:
            normalized = cls._normalize_document_token(candidate)
            if normalized and (
                normalized.startswith(expected) or expected.startswith(normalized)
            ):
                return True
        return False

    @classmethod
    def _clause_matches_hint(cls, chunk: Chunk, clause: str) -> bool:
        """匹配目标条款编号，允许父条款命中子条款。"""
        if not clause:
            return False

        expected = clause.strip().lower()
        if not expected:
            return False

        expected_tokens = cls._extract_clause_tokens(expected) or {expected}
        clause_tokens = cls._build_clause_token_candidates(chunk, expected_tokens)
        return any(
            cls._clause_token_matches(token, expected_token)
            for token in clause_tokens
            for expected_token in expected_tokens
        )

    @staticmethod
    def _count_object_hits(chunk: Chunk, obj: str) -> int:
        """统计目标对象术语在 chunk 元数据与正文中的命中数。"""
        if not obj:
            return 0

        combined = " ".join(
            [
                chunk.content,
                chunk.embedding_text,
                chunk.metadata.source_title,
                " ".join(chunk.metadata.section_path),
                " ".join(chunk.metadata.clause_ids),
            ]
        ).lower()
        terms = {
            term
            for term in re.findall(r"[a-z0-9]+", obj.lower())
            if len(term) >= 3
        }
        return sum(1 for term in terms if term in combined)

    def _exact_match_features(
        self,
        chunk: Chunk,
        target_hint: Any,
    ) -> tuple[bool, bool, int]:
        """返回 exact 检索使用的结构化命中特征。"""
        normalized_hint = self._normalize_target_hint(target_hint)
        return (
            self._document_matches_hint(chunk, normalized_hint.get("document", "")),
            self._clause_matches_hint(chunk, normalized_hint.get("clause", "")),
            self._count_object_hits(chunk, normalized_hint.get("object", "")),
        )

    @staticmethod
    def _is_low_value_exact_chunk(chunk: Chunk) -> bool:
        title = chunk.metadata.source_title.lower()
        section_text = " ".join(chunk.metadata.section_path).lower()
        return any(
            signal in title or signal in section_text
            for signal in _LOW_VALUE_EXACT_SIGNALS
        )

    def _score_exact_chunk(
        self,
        chunk: Chunk,
        intent_label: str | None,
        target_hint: Any,
    ) -> tuple[int, bool]:
        """返回 exact 候选得分以及是否命中 direct anchor。"""
        normalized_hint = self._normalize_target_hint(target_hint)
        content = chunk.content.lower()

        score = 0
        direct_anchor = False

        raw_anchor_hit = any(
            pattern in content for pattern in self._anchor_patterns_for_intent(intent_label)
        )
        has_structured_hint = any(
            normalized_hint.get(key, "")
            for key in ("document", "clause", "object")
        )

        document = normalized_hint.get("document", "")

        document_match, clause_match, object_hits = self._exact_match_features(
            chunk,
            normalized_hint,
        )

        if document_match:
            score += 30
        if clause_match:
            score += 40
        if object_hits:
            score += min(object_hits, 3) * 10

        if raw_anchor_hit and (
            (
                document_match
                and (
                    clause_match
                    or object_hits >= 1
                )
            )
            or (
                not document
                and (
                    clause_match
                    or object_hits >= 2
                )
            )
        ):
            score += 100
            direct_anchor = True
        elif raw_anchor_hit and not has_structured_hint and not self._is_low_value_exact_chunk(chunk):
            score += 80
            direct_anchor = True

        if self._is_low_value_exact_chunk(chunk):
            score -= 80

        return score, direct_anchor

    def _apply_exact_groundedness(
        self,
        chunks: list[Chunk],
        scores: list[float],
        intent_label: str | None,
        target_hint: Any,
    ) -> tuple[list[Chunk], list[float], str, list[str]]:
        """依据 anchor/title/clause/object 命中，对 exact 检索结果重排并判定 groundedness。"""
        if not chunks:
            return chunks, scores, "exact_not_grounded", []

        ranked_candidates: list[tuple[int, bool, bool, bool, int, float, int, Chunk]] = []
        anchor_chunk_ids: list[str] = []
        for index, chunk in enumerate(chunks):
            document_match, clause_match, object_hits = self._exact_match_features(
                chunk,
                target_hint,
            )
            exact_score, direct_anchor = self._score_exact_chunk(chunk, intent_label, target_hint)
            if direct_anchor:
                anchor_chunk_ids.append(chunk.chunk_id)
            rerank_score = scores[index] if index < len(scores) else 0.0
            ranked_candidates.append(
                (
                    exact_score,
                    direct_anchor,
                    document_match,
                    clause_match,
                    object_hits,
                    rerank_score,
                    index,
                    chunk,
                )
            )

        if any(item[2] for item in ranked_candidates):
            ranked_candidates = [item for item in ranked_candidates if item[2]]

        if any(item[2] and item[3] for item in ranked_candidates):
            ranked_candidates = [item for item in ranked_candidates if item[2] and item[3]]
        elif any(item[2] and item[4] > 0 for item in ranked_candidates):
            ranked_candidates = [
                item for item in ranked_candidates if item[2] and item[4] > 0
            ]
        elif any(item[3] for item in ranked_candidates):
            ranked_candidates = [item for item in ranked_candidates if item[3]]

        if any(
            direct_anchor or exact_score >= 80
            for exact_score, direct_anchor, *_ in ranked_candidates
        ):
            ranked_candidates = [
                item for item in ranked_candidates
                if item[0] >= 30 or item[1]
            ]

        ranked_candidates.sort(
            key=lambda item: (item[1], item[0], item[5], -item[6]),
            reverse=True,
        )

        reordered_chunks = [item[7] for item in ranked_candidates]
        reordered_scores = [item[5] for item in ranked_candidates]

        if anchor_chunk_ids:
            groundedness = "grounded"
        elif any(score > 0 for score, *_ in ranked_candidates):
            groundedness = "exact_not_grounded"
        else:
            groundedness = "exact_not_grounded"

        return reordered_chunks, reordered_scores, groundedness, anchor_chunk_ids

    @staticmethod
    def _rerank_text(chunk: Chunk) -> str:
        """选择用于 reranker 的文本：table/formula 用 content 以保留完整数据。"""
        if chunk.metadata.element_type in ("table", "formula"):
            # 对于表格和公式，embedding_text 是压缩后的摘要，
            # 用原始 content 做重排序能保留具体数值，提高匹配精度。
            # 截断到 2000 字符避免超出 reranker 输入限制。
            text = chunk.content or ""
            if chunk.metadata.object_label:
                text = f"{chunk.metadata.object_label}\n{text}"
            return text[:2000]
        return chunk.embedding_text or chunk.content

    async def _rerank(
        self, query: str, chunks: list[Chunk], top_n: int
    ) -> list[tuple[Chunk, float]]:
        """使用 FlagReranker 对候选 chunk 进行重排序，返回 top_n 结果。"""
        if not chunks:
            return []

        ranked = await self._rerank_client.rerank(
            query=query,
            documents=[self._rerank_text(c) for c in chunks],
            top_n=top_n,
        )
        return [(chunks[index], score) for index, score in ranked]

    # ------------------------------------------------------------------
    # 交叉引用补充检索
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_internal_refs(chunks: list[Chunk]) -> set[str]:
        """从已检索 chunk 的内容中提取内部交叉引用（Table/Figure/Expression/Annex）。"""
        refs: set[str] = set()
        for chunk in chunks:
            refs.update(_INTERNAL_REF_RE.findall(chunk.content))
        return {r.strip() for r in refs}

    @staticmethod
    def _refs_covered_by_chunks(refs: set[str], chunks: list[Chunk]) -> set[str]:
        """识别已被当前 chunk 覆盖的引用（即该 chunk 本身就是该 Table/Figure 的内容）。"""
        covered: set[str] = set()
        for chunk in chunks:
            # 表格/公式/图片类型的 chunk 本身就是被引用的内容
            if chunk.metadata.element_type in ("table", "formula", "image"):
                content_lower = chunk.content.lower()
                for ref in refs:
                    if ref.lower() in content_lower:
                        covered.add(ref)
            # section_path 或 clause_ids 包含引用编号的也算覆盖
            meta_text = " ".join(chunk.metadata.section_path + chunk.metadata.clause_ids).lower()
            for ref in refs:
                # 提取引用中的编号部分（如 "Table 3.1" → "3.1"）
                num_match = re.search(r"[\d]+[\.\d]*", ref)
                if num_match and num_match.group() in meta_text:
                    covered.add(ref)
        return covered

    async def _fetch_cross_ref_chunks(
        self,
        refs: set[str],
        existing_ids: set[str],
        filters: dict | None = None,
        max_refs: int = 5,
    ) -> list[Chunk]:
        """针对未覆盖的交叉引用做定向 BM25 检索，每个引用取最佳匹配。

        优先选择 TABLE/FORMULA/IMAGE 类型的 chunk（交叉引用通常指向这些元素），
        只有在没有结构化元素匹配时才退回到 TEXT 类型。
        """
        if not refs:
            return []

        filters = filters or {}
        ref_chunks: list[Chunk] = []
        seen = set(existing_ids)

        # 识别引用类型前缀以确定优先 element_type
        _TABLE_PREFIX = re.compile(r"^table\b", re.IGNORECASE)
        _FIGURE_PREFIX = re.compile(r"^figure\b", re.IGNORECASE)
        _EXPR_PREFIX = re.compile(r"^expression\b", re.IGNORECASE)

        for ref in sorted(refs)[:max_refs]:
            try:
                results = await self._bm25_search(ref, top_k=6, filters=filters)
                if not results:
                    continue

                fetched_candidates: list[Chunk] = []
                for r in results:
                    cid = r["chunk_id"]
                    if cid in seen:
                        continue
                    fetched = await self._fetch_chunks([cid])
                    if fetched:
                        fetched_candidates.append(fetched[0])
                    if len(fetched_candidates) >= 3:
                        break

                if not fetched_candidates:
                    continue

                # 优先选择与引用类型匹配的结构化 chunk
                preferred_types: set[str] = set()
                if _TABLE_PREFIX.match(ref):
                    preferred_types = {"table"}
                elif _FIGURE_PREFIX.match(ref):
                    preferred_types = {"image"}
                elif _EXPR_PREFIX.match(ref):
                    preferred_types = {"formula"}

                chosen = None
                if preferred_types:
                    for c in fetched_candidates:
                        if c.metadata.element_type in preferred_types:
                            chosen = c
                            break
                if chosen is None:
                    chosen = fetched_candidates[0]

                seen.add(chosen.chunk_id)
                ref_chunks.append(chosen)
            except Exception:
                logger.warning("cross_ref_search_failed", ref=ref)

        return ref_chunks

    async def _fetch_object_chunks_by_object_ids(
        self,
        object_ids: set[str],
        existing_ids: set[str],
        filters: dict | None = None,
        max_refs: int = 5,
    ) -> list[Chunk]:
        """通过 object_id 做 deterministic keyword lookup。"""
        if not object_ids:
            return []

        filters = filters or {}
        es = await self._get_es()
        ordered_ids = sorted(object_ids)
        filter_clauses = self._build_source_filter_clauses(filters)
        should_clauses: list[dict] = [{"terms": {"object_id": ordered_ids}}]
        for object_id in ordered_ids:
            object_type, aliases = self._lookup_aliases_for_object_id(object_id)
            if not object_type or not aliases:
                continue
            should_clauses.append(
                {
                    "bool": {
                        "must": [
                            {"term": {"object_type": object_type}},
                            {"terms": {"object_aliases": aliases}},
                        ]
                    }
                }
            )

        body = {
            "query": {
                "bool": {
                    "should": should_clauses,
                    "minimum_should_match": 1,
                    "filter": filter_clauses,
                }
            },
            "size": min(max_refs, max(len(ordered_ids), 1)),
        }
        resp = await es.search(index=self.config.es_index, body=body)

        chunk_ids = [
            hit["_id"]
            for hit in resp["hits"]["hits"]
            if hit["_id"] not in existing_ids
        ]
        fetched_chunks = await self._fetch_chunks(chunk_ids)

        by_object_id = {
            chunk.metadata.object_id: chunk
            for chunk in fetched_chunks
            if chunk.metadata.object_id
        }
        by_object_key = {
            self._object_reference_key(chunk.metadata.object_id): chunk
            for chunk in fetched_chunks
            if chunk.metadata.object_id
        }
        ordered_chunks: list[Chunk] = []
        seen_chunk_ids: set[str] = set()
        for object_id in ordered_ids:
            chunk = by_object_id.get(object_id) or by_object_key.get(
                self._object_reference_key(object_id)
            )
            if chunk is None or chunk.chunk_id in seen_chunk_ids:
                continue
            seen_chunk_ids.add(chunk.chunk_id)
            ordered_chunks.append(chunk)
        return ordered_chunks

    @staticmethod
    def _build_cross_ref_filters(
        final_chunks: list[Chunk],
        filters: dict,
    ) -> dict:
        """Constrain cross-reference retrieval to the current retrieval scope."""
        if "source" in filters:
            return {"source": filters["source"]}

        allowed_sources = sorted(
            {
                chunk.metadata.source
                for chunk in final_chunks
                if chunk.metadata.source
            }
        )
        if not allowed_sources:
            return {}
        if len(allowed_sources) == 1:
            return {"source": allowed_sources[0]}
        return {"sources": allowed_sources}

    # ------------------------------------------------------------------
    # 数据获取
    # ------------------------------------------------------------------

    async def _fetch_chunks(self, chunk_ids: list[str]) -> list[Chunk]:
        """根据 chunk_id 列表从 ES 获取完整 Chunk 数据。"""
        if not chunk_ids:
            return []

        es = await self._get_es()
        chunks: list[Chunk] = []

        for cid in chunk_ids:
            try:
                doc = await es.get(index=self.config.es_index, id=cid)
                src = doc["_source"]
                meta_fields = {
                    k: src[k] for k in ChunkMetadata.model_fields if k in src
                }
                chunks.append(
                    Chunk(
                        chunk_id=cid,
                        content=src.get("content", ""),
                        embedding_text=src.get("embedding_text", ""),
                        metadata=ChunkMetadata(**meta_fields),
                    )
                )
            except Exception:
                logger.warning("chunk_fetch_failed", chunk_id=cid)

        return chunks

    async def _fetch_parent_chunks(self, chunks: list[Chunk]) -> list[Chunk]:
        """根据子 chunk 的 parent_chunk_id 获取对应的父 chunk。"""
        parent_ids: set[str] = set()
        for chunk in chunks:
            if chunk.metadata.parent_chunk_id:
                parent_ids.add(chunk.metadata.parent_chunk_id)
        return await self._fetch_chunks(list(parent_ids))

    # ------------------------------------------------------------------
    # 主检索流程
    # ------------------------------------------------------------------

    async def retrieve(
        self,
        queries: list[str],
        original_query: str | None = None,
        filters: dict | None = None,
        answer_mode: str | None = None,
        intent_label: str | None = None,
        question_type: str | QuestionType | None = None,
        guide_hint: GuideHint | dict[str, Any] | None = None,
        target_hint: Any = None,
        requested_objects: list[str] | None = None,
        preferred_element_type: str | None = None,
    ) -> RetrievalResult:
        """执行多角度混合检索流程。

        流程：多路向量检索 + 多路 BM25 → 合并去重 → 跨文档聚合
              → 获取完整 chunk → 重排序(原始中文) → 获取父 chunk。

        Args:
            queries: 多角度英文检索查询列表（语义/概念/术语）
            original_query: 用户原始中文问题（用于补充检索和 rerank）
            filters: 过滤条件
        """
        filters = filters or {}
        requested_objects = [
            normalize_reference_label(label)
            for label in (requested_objects or [])
            if normalize_reference_label(label)
        ]
        cfg = self.config
        all_results: list[dict] = []
        exact_probe_used = self._is_exact_mode(answer_mode)

        if exact_probe_used:
            probe_results = await self._run_exact_probe(
                queries=queries,
                original_query=original_query,
                filters=filters,
                target_hint=target_hint,
                intent_label=intent_label,
            )
            all_results = self._append_unique_results(all_results, probe_results)

        # 多角度检索：每条查询分别跑向量 + BM25
        for q in queries:
            try:
                vec = await self._vector_search(q, cfg.vector_top_k, filters)
                all_results = self._append_unique_results(all_results, vec)
            except Exception:
                logger.warning("vector_search_failed", query=q[:80])

            try:
                bm25 = await self._bm25_search(
                    q, cfg.bm25_top_k, filters,
                    preferred_element_type=preferred_element_type,
                )
                all_results = self._append_unique_results(all_results, bm25)
            except Exception:
                logger.warning("bm25_search_failed", query=q[:80])

        # 原始中文问题补充检索（向量 + BM25）
        normalized_original = (original_query or "").strip()
        primary_query = queries[0] if queries else ""
        if normalized_original and normalized_original != primary_query.strip():
            try:
                orig_vec = await self._vector_search(
                    normalized_original, cfg.vector_top_k, filters,
                )
                all_results = self._append_unique_results(all_results, orig_vec)
            except Exception:
                logger.warning("original_query_vector_search_failed")
            try:
                orig_bm25 = await self._bm25_search(
                    normalized_original, cfg.bm25_top_k, filters,
                    preferred_element_type=preferred_element_type,
                )
                all_results = self._append_unique_results(all_results, orig_bm25)
            except Exception:
                logger.warning("original_query_bm25_search_failed")

        # 跨文档聚合
        # exact 问题需要保留同一 source 内的深层候选，避免条款锚点在聚合阶段被过早裁掉。
        aggregated = (
            all_results
            if exact_probe_used
            else self._cross_doc_aggregate(all_results, filters=filters)
        )

        # 获取完整 chunk 数据
        chunk_ids = [r["chunk_id"] for r in aggregated]
        chunks = await self._fetch_chunks(chunk_ids)

        # 重排序（使用原始中文问题，bge-reranker 支持跨语言）
        rerank_query = normalized_original or primary_query
        try:
            rerank_top_n = len(chunks) if exact_probe_used else cfg.rerank_top_n
            reranked = await self._rerank(rerank_query, chunks, rerank_top_n)
            final_chunks = [c for c, _ in reranked]
            scores = [s for _, s in reranked]
        except Exception:
            logger.warning(
                "rerank_failed_falling_back_to_unranked_chunks",
                exc_info=True,
            )
            final_chunks = chunks[: cfg.rerank_top_n]
            scores = [0.0] * len(final_chunks)

        groundedness = "open"
        anchor_chunk_ids: list[str] = []
        if exact_probe_used:
            final_chunks, scores, groundedness, anchor_chunk_ids = self._apply_exact_groundedness(
                final_chunks,
                scores,
                intent_label,
                target_hint,
            )
            final_chunks = final_chunks[: cfg.rerank_top_n]
            scores = scores[: cfg.rerank_top_n]

        final_chunks, scores, guide_chunks_from_main = self._split_normative_and_guide_chunks(
            final_chunks,
            scores,
        )

        # 获取父 chunk
        parent_chunks = await self._fetch_parent_chunks(final_chunks)

        # deterministic object lookup：显式请求对象 + 主条款直接引用对象
        # 对所有 answer_mode 生效（不再限于 exact 模式），
        # 确保用户明确提到的 Table/Figure 始终能被检索到
        lookup_source = ""
        requested_object_ids: set[str] = set()
        if requested_objects:
            requested_object_ids, lookup_source = self._build_requested_object_ids(
                requested_objects,
                filters,
                target_hint,
            )
        existing_chunks = final_chunks + parent_chunks
        existing_ids = {chunk.chunk_id for chunk in existing_chunks}
        resolved_object_ids = self._collect_object_ids(existing_chunks)
        resolved_object_keys = self._collect_object_keys(existing_chunks)
        exact_anchor_chunks: list[Chunk] = []
        if exact_probe_used and anchor_chunk_ids:
            anchor_id_set = set(anchor_chunk_ids)
            exact_anchor_chunks = [
                chunk for chunk in final_chunks if chunk.chunk_id in anchor_id_set
            ]
        closure_seed_chunks = exact_anchor_chunks or final_chunks[:1]
        direct_ref_object_ids = self._collect_ref_object_ids(closure_seed_chunks)
        requested_object_keys = {
            self._object_reference_key(object_id)
            for object_id in requested_object_ids
            if object_id
        }
        object_labels_by_id = self._build_object_id_label_map(
            final_chunks,
            requested_objects,
            lookup_source,
        )

        missing_object_ids = {
            object_id
            for object_id in direct_ref_object_ids | requested_object_ids
            if self._object_reference_key(object_id) not in resolved_object_keys
        }
        deterministic_ref_chunks: list[Chunk] = []
        if missing_object_ids:
            deterministic_ref_chunks = await self._fetch_object_chunks_by_object_ids(
                missing_object_ids,
                existing_ids,
                filters=self._build_cross_ref_filters(final_chunks, filters),
            )
        resolved_object_ids.update(self._collect_object_ids(deterministic_ref_chunks))
        resolved_object_keys.update(self._collect_object_keys(deterministic_ref_chunks))
        existing_ids.update(chunk.chunk_id for chunk in deterministic_ref_chunks)

        # 交叉引用补充检索：提取 chunk 中提到的 Table/Figure/Expression，
        # 过滤已覆盖的，针对缺失的做定向 BM25 检索
        all_existing = final_chunks + parent_chunks + deterministic_ref_chunks
        all_refs = self._extract_internal_refs(final_chunks)
        for chunk in final_chunks:
            all_refs.update(chunk.metadata.ref_labels)
        covered = self._refs_covered_by_chunks(all_refs, all_existing)
        missing_refs = all_refs - covered
        cross_ref_filters = self._build_cross_ref_filters(final_chunks, filters)
        fallback_ref_chunks = await self._fetch_cross_ref_chunks(
            missing_refs,
            existing_ids,
            filters=cross_ref_filters,
        )
        ref_chunks = deterministic_ref_chunks + fallback_ref_chunks
        if ref_chunks:
            logger.info(
                "cross_ref_supplemental",
                missing=sorted(missing_refs),
                fetched=len(ref_chunks),
            )

        resolved_object_ids.update(self._collect_object_ids(ref_chunks))
        resolved_object_keys.update(self._collect_object_keys(ref_chunks))
        object_labels_by_id = self._build_object_id_label_map(
            final_chunks + deterministic_ref_chunks + ref_chunks,
            requested_objects,
            lookup_source,
        )
        required_object_ids = {
            object_id
            for object_id in direct_ref_object_ids | requested_object_ids
            if self._should_require_reference_closure(
                self._object_reference_key(object_id),
                requested_object_keys,
            )
        }
        required_object_keys = {
            self._object_reference_key(object_id)
            for object_id in required_object_ids
            if object_id
        }
        final_chunks, scores, ref_chunks = self._promote_exact_ref_chunks(
            final_chunks,
            scores,
            ref_chunks,
            required_object_keys,
            requested_object_keys,
        )
        unresolved_required_keys = sorted(required_object_keys - resolved_object_keys)
        labels_by_key = {
            self._object_reference_key(object_id): label
            for object_id, label in object_labels_by_id.items()
            if object_id and label
        }
        resolved_refs = sorted(
            labels_by_key[object_key]
            for object_key in required_object_keys
            if object_key in resolved_object_keys and object_key in labels_by_key
        )
        unresolved_refs = sorted(
            labels_by_key.get(
                object_key,
                self._display_label_for_object_id(object_key),
            )
            for object_key in unresolved_required_keys
        )
        if (
            exact_probe_used
            and groundedness != "grounded"
            and not unresolved_required_keys
            and final_chunks
        ):
            _, clause_match, object_hits = self._exact_match_features(final_chunks[0], target_hint)
            if required_object_ids and (clause_match or object_hits > 0):
                groundedness = "grounded"
        if exact_probe_used and unresolved_required_keys:
            groundedness = "exact_not_grounded"

        guide_chunks: list[Chunk] = []
        if self._should_fetch_guide_chunks(question_type, guide_hint):
            retrieved_guide_chunks = await self._retrieve_guide_chunks(
                queries,
                original_query,
            )
            guide_chunks = self._append_unique_chunks(
                guide_chunks_from_main,
                retrieved_guide_chunks,
            )
        guide_example_chunks = await self._retrieve_guide_example_chunks(
            queries,
            original_query,
            guide_hint,
        )

        return RetrievalResult(
            chunks=final_chunks,
            parent_chunks=parent_chunks,
            scores=scores,
            guide_chunks=guide_chunks,
            guide_example_chunks=guide_example_chunks,
            ref_chunks=ref_chunks,
            groundedness=groundedness,
            anchor_chunk_ids=anchor_chunk_ids,
            exact_probe_used=exact_probe_used,
            resolved_refs=resolved_refs,
            unresolved_refs=unresolved_refs,
        )

    async def close(self) -> None:
        """清理 ES 连接资源。"""
        if self._es is not None:
            await self._es.close()
