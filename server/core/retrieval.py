"""混合检索层：向量检索 + BM25 + 重排序 + 父文档检索 + 交叉引用补充。"""
from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import structlog

from shared.elasticsearch_client import build_async_elasticsearch
from shared.model_clients import build_embedding_client, build_rerank_client
from shared.reference_graph import (
    build_object_id,
    classify_reference_label,
    extract_reference_labels,
    normalize_reference_label,
)
from shared.spot_check import record_spot_check
from shared.tokenizers import count_for_rerank
from server.config import ServerConfig
from server.models.schemas import Chunk, ChunkMetadata, GuideHint, QuestionType

if TYPE_CHECKING:
    from elasticsearch import AsyncElasticsearch
    from pymilvus import Collection

logger = structlog.get_logger(__name__)

# 匹配源文档代号（EN 1990, EN 1992-1-1 等）用于标识引用的标准来源
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
    "source_title.text^3",
    "source^2",
]
_DEFAULT_BM25_FIELDS = [
    "content^2",
    "embedding_text",
    "source_title.text^3",
    "section_path.text^2",
    "clause_ids.text^4",
    "object_aliases.text^5",
]
_RRF_K = 60

# 交叉引用补充检索最多发起的精确查询数。提升到 10 是因为：
# 一次 question 平均有 ~21 个 missing refs，其中大部分（Table/Figure/
# Expression/Section）走 ES term keyword lookup，单次 ~1ms，提高上限带来
# 可测量的 recall 增益（详见 .trellis/tasks/05-24-cross-ref-resolution/）。
_MAX_CROSS_REFS = 5

# 交叉引用类别优先级（数字越小越靠前）。结构化元素（Expression/Table/Figure
# /Section 编号）优先于纯文本的 Annex/EN 引用，因为前者更容易通过 ES 精确
# 查询命中，且承载具体计算/参数信息。
_CROSS_REF_PRIORITY = {
    "expression": 0,
    "table": 1,
    "figure": 2,
    "clause": 3,
    "annex": 4,
    "en_std": 5,
    None: 6,
}


@dataclass
class RetrievalResult:
    """检索结果，包含最终 chunk、父 chunk、交叉引用 chunk 和重排序分数。"""

    chunks: list[Chunk]
    parent_chunks: list[Chunk]
    scores: list[float]
    guide_chunks: list[Chunk] = field(default_factory=list)
    guide_example_chunks: list[Chunk] = field(default_factory=list)
    ref_chunks: list[Chunk] = field(default_factory=list)
    groundedness: str = "not_grounded"
    resolved_refs: list[str] = field(default_factory=list)
    unresolved_refs: list[str] = field(default_factory=list)


def _result_entries(results: list[dict]) -> list[dict[str, Any]]:
    """Serialize retrieval result dictionaries for spot-check logs."""
    entries: list[dict[str, Any]] = []
    for result in results:
        entries.append(
            {
                "chunk_id": result.get("chunk_id"),
                "source": result.get("source"),
                "score": result.get("score"),
            }
        )
    return entries


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
        self._en_sources_cache: set[str] | None = None

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

    async def initialize(self) -> None:
        """初始化 Milvus 连接并预加载 Collection。"""
        logger.info(
            "milvus_initialize_starting",
            host=self.config.milvus_host,
            port=self.config.milvus_port,
            collection=self.config.milvus_collection,
        )
        try:
            collection_cls, milvus_connections = self._import_milvus()
            await asyncio.to_thread(
                milvus_connections.connect,
                host=self.config.milvus_host,
                port=self.config.milvus_port,
            )
            collection = collection_cls(self.config.milvus_collection)
            await asyncio.to_thread(collection.load)
            self._collection = collection
            logger.info(
                "milvus_initialize_completed",
                collection=self.config.milvus_collection,
            )
        except Exception:
            logger.exception(
                "milvus_initialize_failed",
                collection=self.config.milvus_collection,
            )
            raise

    def _get_collection(self) -> Collection:
        """获取已加载的 Milvus Collection。"""
        if self._collection is None:
            logger.warning(
                "milvus_collection_lazy_initialization",
                collection=self.config.milvus_collection,
            )
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

    async def prefetch_vectors(
        self, query: str, filters: dict | None = None,
    ) -> list[dict]:
        """Run a vector search that can overlap with query expansion.

        Returns raw result dicts suitable for passing into
        ``retrieve(prefetched_original_results=...)``.
        """
        filters = filters or {}
        try:
            return await self._vector_search(
                query, self.config.vector_top_k, filters,
            )
        except Exception:
            logger.warning("prefetch_vectors_failed", query=query[:80])
            return []

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

        results = await asyncio.to_thread(
            collection.search,
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
        search_fields = fields or _DEFAULT_BM25_FIELDS

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
        """合并向量检索和 BM25 结果并去重，使用 RRF 保留两路排序信号。"""
        return self._rrf_fuse_results([vec_results, bm25_results])

    @staticmethod
    def _rrf_fuse_results(
        result_groups: list[list[dict]],
        *,
        rrf_k: int = _RRF_K,
    ) -> list[dict]:
        """Fuse ranked retrieval groups with Reciprocal Rank Fusion."""
        fused: dict[str, dict[str, Any]] = {}
        first_order = 0

        for group in result_groups:
            for rank, result in enumerate(group, start=1):
                chunk_id = result.get("chunk_id")
                if not chunk_id:
                    continue
                if chunk_id not in fused:
                    fused[chunk_id] = {
                        **result,
                        "score": 0.0,
                        "_first_order": first_order,
                    }
                    first_order += 1
                fused[chunk_id]["score"] += 1.0 / (rrf_k + rank)

        ranked = sorted(
            fused.values(),
            key=lambda item: (item["score"], -item["_first_order"]),
            reverse=True,
        )
        return [
            {key: value for key, value in item.items() if not key.startswith("_")}
            for item in ranked
        ]

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
    def _collect_guide_chunks(
        cls,
        chunks: list[Chunk],
    ) -> list[Chunk]:
        """Return guide-like chunks without removing them from citable evidence."""
        return [chunk for chunk in chunks if cls._is_guide_chunk(chunk)]

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

        async def _search_guide_query(query: str) -> list[dict]:
            query_results: list[dict] = []

            async def _vector() -> list[dict]:
                try:
                    return await self._vector_search(
                        query,
                        self._guide_search_top_k(),
                        guide_filters,
                    )
                except Exception:
                    logger.warning("guide_vector_search_failed", query=query[:80])
                    return []

            async def _bm25() -> list[dict]:
                try:
                    return await self._bm25_search(
                        query,
                        min(max(self.config.bm25_top_k * 3, 12), 30),
                        guide_filters,
                        fields=_GUIDE_SEARCH_FIELDS,
                    )
                except Exception:
                    logger.warning("guide_bm25_search_failed", query=query[:80])
                    return []

            vec, bm25 = await asyncio.gather(_vector(), _bm25())
            query_results = self._append_unique_results(query_results, vec)
            query_results = self._append_unique_results(query_results, bm25)
            return query_results

        per_query_results = await asyncio.gather(
            *(_search_guide_query(query) for query in guide_queries)
        )
        for query_results in per_query_results:
            candidate_results = self._append_unique_results(
                candidate_results,
                query_results,
            )

        if not candidate_results:
            return []

        guide_chunk_ids = [result["chunk_id"] for result in candidate_results]
        guide_candidates = self._filter_guide_candidates(
            await self._fetch_chunks(guide_chunk_ids)
        )
        if not guide_candidates:
            return []

        # 重排序优先使用 expanded query 的英文版本，对英文 chunks 更准
        primary_query = queries[0].strip() if queries else ""
        rerank_query = primary_query or (original_query or "").strip() or guide_queries[0]
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

        async def _search_guide_example_query(query: str) -> list[dict]:
            query_results: list[dict] = []

            async def _vector() -> list[dict]:
                try:
                    return await self._vector_search(
                        query,
                        self._guide_search_top_k(),
                        guide_filters,
                    )
                except Exception:
                    logger.warning("guide_example_vector_search_failed", query=query[:80])
                    return []

            async def _bm25() -> list[dict]:
                try:
                    return await self._bm25_search(
                        query,
                        min(max(self.config.bm25_top_k * 3, 12), 30),
                        guide_filters,
                        fields=_GUIDE_SEARCH_FIELDS,
                    )
                except Exception:
                    logger.warning("guide_example_bm25_search_failed", query=query[:80])
                    return []

            vec, bm25 = await asyncio.gather(_vector(), _bm25())
            query_results = self._append_unique_results(query_results, vec)
            query_results = self._append_unique_results(query_results, bm25)
            return query_results

        per_query_results = await asyncio.gather(
            *(_search_guide_example_query(query) for query in guide_queries)
        )
        for query_results in per_query_results:
            candidate_results = self._append_unique_results(
                candidate_results,
                query_results,
            )

        if not candidate_results:
            return []

        guide_chunk_ids = [result["chunk_id"] for result in candidate_results]
        guide_candidates = self._filter_guide_candidates(
            await self._fetch_chunks(guide_chunk_ids)
        )
        if not guide_candidates:
            return []

        # 优先用 example_query/英文 expanded query，对英文 chunks 更准
        primary_query = queries[0].strip() if queries else ""
        rerank_query = (
            normalized_hint.example_query
            or primary_query
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

    async def _run_metadata_probe(
        self,
        queries: list[str],
        original_query: str | None,
        filters: dict,
        target_hint: Any = None,
        intent_label: str | None = None,
    ) -> list[dict]:
        """Run metadata-weighted probe using structured target hints."""
        del intent_label
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
                    await self._run_clause_metadata_probe(clause, filters),
                )
            except Exception:
                logger.warning("metadata_probe_clause_metadata_failed", clause=clause[:40])

        metadata_fields = [
            "source^6",
            "clause_ids.text^8",
            "section_path.text^7",
            "source_title.text^4",
            "object_aliases.text^5",
            "content^2",
            "embedding_text",
        ]
        async def _search_metadata_query(query: str) -> list[dict]:
            try:
                return await self._bm25_search(
                    query,
                    self.config.bm25_top_k,
                    filters,
                    fields=metadata_fields,
                )
            except Exception:
                logger.warning("metadata_probe_bm25_failed", query=query[:80])
                return []

        per_query_results = await asyncio.gather(
            *(_search_metadata_query(query) for query in deduped_queries)
        )
        for query_results in per_query_results:
            results = self._append_unique_results(results, query_results)

        return results

    async def _run_clause_metadata_probe(
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
    def _infer_groundedness_from_scores(scores: list[float]) -> str:
        """Infer evidence groundedness from reranker scores."""
        if not scores:
            return "not_grounded"
        top = scores[0]
        if top >= 0.85:
            return "grounded"
        if top >= 0.5:
            return "partial"
        return "not_grounded"

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

        documents = [self._rerank_text(c) for c in chunks]
        token_records: list[dict[str, Any]] = []
        truncation_records: list[dict[str, Any]] = []
        rerank_max_length = max(int(self.config.rerank_max_length), 1)
        for chunk, document in zip(chunks, documents, strict=False):
            token_count, is_estimate = count_for_rerank(
                document,
                self.config.rerank_model,
            )
            truncated = token_count > rerank_max_length
            element_type = getattr(
                chunk.metadata.element_type,
                "value",
                chunk.metadata.element_type,
            )
            token_records.append(
                {
                    "chunk_id": chunk.chunk_id,
                    "tokens": token_count,
                    "is_estimate": is_estimate,
                    "source": chunk.metadata.source,
                    "element_type": element_type,
                }
            )
            truncation_records.append(
                {
                    "chunk_id": chunk.chunk_id,
                    "tokens": token_count,
                    "max_tokens": rerank_max_length,
                    "truncated": truncated,
                    "truncation_ratio": (
                        token_count / rerank_max_length if token_count else 0.0
                    ),
                    "source": chunk.metadata.source,
                    "element_type": element_type,
                }
            )
        record_spot_check("rerank_input_tokens", token_records)
        record_spot_check("rerank_truncated", truncation_records)

        ranked = await self._rerank_client.rerank(
            query=query,
            documents=documents,
            top_n=top_n,
        )
        return [(chunks[index], score) for index, score in ranked]

    # ------------------------------------------------------------------
    # 交叉引用补充检索
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_internal_refs(chunks: list[Chunk]) -> set[str]:
        """从已检索 chunk 的内容中提取内部交叉引用（Table/Figure/Expression/Annex/Clause/EN-std）。

        使用 shared.reference_graph.extract_reference_labels（与 ingest 阶段一致），
        自动剔除尾部标点（如 "Figure 3.8)" → "Figure 3.8"）以及大小写假阳性
        （如 "National Annex proposes …"），并产出 canonical 形式。
        """
        refs: set[str] = set()
        for chunk in chunks:
            for label in extract_reference_labels(chunk.content):
                normalized = normalize_reference_label(label)
                if normalized:
                    refs.add(normalized)
        return refs

    @staticmethod
    def _refs_covered_by_chunks(refs: set[str], chunks: list[Chunk]) -> set[str]:
        """识别已被当前 chunk 覆盖的引用。

        覆盖判定按优先级：
        1. chunk.metadata.object_label 与 ref 完全相等（最强信号）。
        2. table/formula/image 类型 chunk 内容包含 ref 的 canonical 字面（如
           "Table 3.1"），仍以词边界为准而非裸子串。
        3. clause 类（section 编号）ref 的 numeric token 与 chunk 的 clause_ids
           完全相等，或与 section_path 中以词边界匹配。

        之前的实现对编号做裸子串匹配（例如 "Figure 6.10" 的 "6.10" 会被
        clause_ids=["6.10"] 误判为覆盖），导致需要补检的引用被静默吞掉。
        """
        covered: set[str] = set()
        if not refs:
            return covered

        # 预编译每个 ref 的边界匹配 regex（在 section_path 拼接文本上使用）
        ref_token_patterns: dict[str, re.Pattern[str]] = {}
        for ref in refs:
            token = re.search(r"[A-Za-z]?\d+(?:\.\d+)*", ref)
            if token is None:
                continue
            ref_token_patterns[ref] = re.compile(
                rf"(?<![\w.]){re.escape(token.group(0))}(?![\w.])"
            )

        for chunk in chunks:
            object_label = chunk.metadata.object_label or ""
            # 1) 精确 object_label 命中
            if object_label:
                for ref in refs:
                    if ref == object_label:
                        covered.add(ref)

            # 2) 结构化 chunk（table/formula/image）的内容里完整 ref 字面
            if chunk.metadata.element_type in ("table", "formula", "image"):
                content = chunk.content or ""
                for ref in refs:
                    if not ref:
                        continue
                    pattern = re.compile(
                        rf"(?<!\w){re.escape(ref)}(?!\w)",
                        re.IGNORECASE,
                    )
                    if pattern.search(content):
                        covered.add(ref)

            # 3) clause 类 ref：clause_ids 精确相等，或 section_path 内词边界匹配
            clause_ids = {cid.strip() for cid in chunk.metadata.clause_ids if cid}
            section_text = " ".join(chunk.metadata.section_path).lower()
            for ref, pattern in ref_token_patterns.items():
                if ref in covered:
                    continue
                category = classify_reference_label(ref)
                # 仅当 ref 本身是 clause/section 编号时，才允许 clause_ids/
                # section_path 的数字覆盖。Figure/Table/Expression 不走此通道，
                # 避免编号巧合（如 "Figure 6.10" 被 clause_ids=["6.10"] 误覆盖）。
                if category != "clause":
                    continue
                if ref in clause_ids:
                    covered.add(ref)
                    continue
                if pattern.search(section_text):
                    covered.add(ref)
        return covered

    @classmethod
    def _categorize_cross_ref(cls, ref: str) -> str | None:
        """Classify a normalized ref into a cross-ref category.

        Extends `classify_reference_label` with an `en_std` bucket for
        external standard references like `EN 1992-1-1`.
        """
        cat = classify_reference_label(ref)
        if cat is not None:
            return cat
        if ref.upper().startswith("EN "):
            return "en_std"
        return None

    @classmethod
    def _prioritize_cross_refs(cls, refs: set[str]) -> list[str]:
        """Order missing refs by category priority then alphabetically.

        Replaces the previous `sorted(refs)` which alphabetically biased
        `Annex …` ahead of `Expression/Table/Figure/Section`, starving the
        `max_refs` budget for high-value structured refs.
        """
        return sorted(
            refs,
            key=lambda r: (
                _CROSS_REF_PRIORITY.get(cls._categorize_cross_ref(r), _CROSS_REF_PRIORITY[None]),
                r,
            ),
        )

    async def _known_en_sources(self) -> set[str]:
        """Lazy-load and cache the set of EN standard codes present as sources.

        Used to skip lookups for refs that point to standards not in the
        corpus (e.g., `EN 1997`, `EN 1996`), which currently waste lookup
        slots returning noise from BM25.
        """
        if self._en_sources_cache is not None:
            return self._en_sources_cache
        es = await self._get_es()
        body = {
            "size": 0,
            "aggs": {"sources": {"terms": {"field": "source", "size": 1000}}},
        }
        codes: set[str] = set()
        try:
            resp = await es.search(index=self.config.es_index, body=body)
        except Exception:
            # Do not cache on failure — let the next call retry. Returning an
            # empty set here would, combined with the `not known` safeguard
            # in `_en_std_ref_in_corpus`, permanently disable the EN-std skip
            # optimisation after a single transient ES error.
            logger.warning("known_en_sources_lookup_failed")
            return codes
        buckets = resp.get("aggregations", {}).get("sources", {}).get("buckets", [])
        for bucket in buckets:
            code, _ = self._parse_source_reference(str(bucket.get("key", "")))
            if code:
                codes.add(code)
                # Also register the leading part (`1992-1-1` → `1992`) so
                # a vague `EN 1992` ref doesn't get skipped when only
                # `EN 1992-1-1` is indexed.
                head = code.split("-", 1)[0]
                if head:
                    codes.add(head)
        self._en_sources_cache = codes
        return codes

    async def _en_std_ref_in_corpus(self, ref: str) -> bool:
        """Return True iff the EN-std ref's code matches at least one indexed source."""
        code, _ = self._parse_source_reference(ref)
        if not code:
            return False
        known = await self._known_en_sources()
        if not known:
            return True  # cache lookup failed — don't suppress
        if code in known:
            return True
        head = code.split("-", 1)[0]
        return head in known

    async def _exact_object_label_lookup(
        self,
        ref: str,
        category: str,
        filter_clauses: list[dict],
    ) -> Chunk | None:
        """Issue a deterministic `object_label` keyword lookup for a ref.

        Returns the first chunk whose `object_label` exactly equals `ref`
        within the source scope, preferring structured element types when
        appropriate. Falls back to `None` (caller will use BM25) on miss
        or any internal error so the BM25 path remains the safety net.
        """
        try:
            es = await self._get_es()
        except Exception:
            logger.warning("cross_ref_exact_lookup_es_unavailable", ref=ref)
            return None
        filters: list[dict] = [{"term": {"object_label": ref}}, *filter_clauses]
        if category in ("table", "figure", "expression"):
            element_types = {
                "table": ["table"],
                "figure": ["image"],
                "expression": ["formula"],
            }[category]
            filters.append({"terms": {"element_type": element_types}})
        body = {"size": 1, "query": {"bool": {"filter": filters}}}
        try:
            resp = await es.search(index=self.config.es_index, body=body)
        except Exception:
            logger.warning("cross_ref_exact_lookup_failed", ref=ref)
            return None
        hits = resp.get("hits", {}).get("hits", [])
        if not hits:
            return None
        chunk_id = hits[0]["_id"]
        fetched = await self._fetch_chunks([chunk_id])
        return fetched[0] if fetched else None

    async def _fetch_cross_ref_chunks(
        self,
        refs: set[str],
        existing_ids: set[str],
        filters: dict | None = None,
        max_refs: int = _MAX_CROSS_REFS,
    ) -> list[Chunk]:
        """针对未覆盖的交叉引用补充检索，每个引用取最佳匹配。

        策略（按优先级）：
        1. **Deterministic `object_label` keyword 查询**（Table/Figure/
           Expression/Clause-section）：ES 的 `object_label` 是 keyword 字段，
           精确等值查询比 BM25 `multi_match` 更稳定，尤其是数字密集的
           clause/expression 编号。
        2. **BM25 兜底**：精确查询无命中时退回原有 `_bm25_search` 路径。
        3. **EN-std 预过滤**：对不在 corpus 内的外部标准（如 EN 1996/1997）
           直接跳过，避免浪费 max_refs 名额。

        优先顺序：Expression > Table > Figure > Clause > Annex > EN-std，
        并将 max_refs 从历史上的 5 提升到 10。
        """
        if not refs:
            return []

        filters = filters or {}
        ref_chunks: list[Chunk] = []
        seen = set(existing_ids)
        filter_clauses = self._build_source_filter_clauses(filters)

        # 识别引用类型前缀以确定 BM25 兜底时优先选哪类 element_type
        _TABLE_PREFIX = re.compile(r"^table\b", re.IGNORECASE)
        _FIGURE_PREFIX = re.compile(r"^figure\b", re.IGNORECASE)
        _EXPR_PREFIX = re.compile(r"^expression\b", re.IGNORECASE)

        ordered_refs = self._prioritize_cross_refs(refs)[:max_refs]

        for ref in ordered_refs:
            try:
                category = self._categorize_cross_ref(ref)

                # Change E: skip EN-std refs that aren't in the corpus
                if category == "en_std" and not await self._en_std_ref_in_corpus(ref):
                    continue

                # Change C: deterministic object_label lookup first
                chosen: Chunk | None = None
                if category in ("table", "figure", "expression", "clause"):
                    candidate = await self._exact_object_label_lookup(
                        ref, category, filter_clauses
                    )
                    if candidate is not None and candidate.chunk_id not in seen:
                        chosen = candidate

                # BM25 fallback (unchanged path)
                if chosen is None:
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

                    preferred_types: set[str] = set()
                    if _TABLE_PREFIX.match(ref):
                        preferred_types = {"table"}
                    elif _FIGURE_PREFIX.match(ref):
                        preferred_types = {"image"}
                    elif _EXPR_PREFIX.match(ref):
                        preferred_types = {"formula"}

                    if preferred_types:
                        for c in fetched_candidates:
                            if c.metadata.element_type in preferred_types:
                                chosen = c
                                break
                    if chosen is None:
                        chosen = fetched_candidates[0]

                if chosen is None or chosen.chunk_id in seen:
                    continue
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
        intent_label: str | None = None,
        question_type: str | QuestionType | None = None,
        guide_hint: GuideHint | dict[str, Any] | None = None,
        target_hint: Any = None,
        requested_objects: list[str] | None = None,
        preferred_element_type: str | None = None,
        prefetched_original_results: list[dict] | None = None,
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
        result_groups: list[list[dict]] = []
        normalized_hint = self._normalize_target_hint(target_hint)
        has_metadata_probe_input = bool(
            normalized_hint.get("document")
            or normalized_hint.get("clause")
            or normalized_hint.get("object")
            or intent_label
            or requested_objects
        )

        if has_metadata_probe_input:
            try:
                probe_results = await self._run_metadata_probe(
                    queries=queries,
                    original_query=original_query,
                    filters=filters,
                    target_hint=target_hint,
                    intent_label=intent_label,
                )
                if probe_results:
                    result_groups.append(probe_results)
            except Exception:
                logger.warning("metadata_probe_failed", exc_info=True)

        # 多角度检索：每条查询并发跑向量 + BM25
        async def _vec_and_bm25(q: str) -> list[list[dict]]:
            groups: list[list[dict]] = []

            async def _vector() -> list[dict]:
                try:
                    return await self._vector_search(q, cfg.vector_top_k, filters)
                except Exception:
                    logger.warning("vector_search_failed", query=q[:80])
                    return []

            async def _bm25() -> list[dict]:
                try:
                    return await self._bm25_search(
                        q,
                        cfg.bm25_top_k,
                        filters,
                        preferred_element_type=preferred_element_type,
                    )
                except Exception:
                    logger.warning("bm25_search_failed", query=q[:80])
                    return []

            vec, bm25 = await asyncio.gather(_vector(), _bm25())
            if vec:
                groups.append(vec)
            if bm25:
                groups.append(bm25)

            return groups

        per_query_groups = await asyncio.gather(
            *(_vec_and_bm25(q) for q in queries)
        )
        for groups in per_query_groups:
            result_groups.extend(groups)

        normalized_original = (original_query or "").strip()
        primary_query = queries[0] if queries else ""

        # 原始中文问题仅作为向量补召回信号；避免中文 BM25 给英文索引引入噪音。
        if prefetched_original_results is not None:
            if prefetched_original_results:
                result_groups.append(prefetched_original_results)
        elif normalized_original and normalized_original != primary_query.strip():
            try:
                orig_vec = await self._vector_search(
                    normalized_original, cfg.vector_top_k, filters,
                )
                if orig_vec:
                    result_groups.append(orig_vec)
            except Exception:
                logger.warning("original_query_vector_search_failed")

        all_results = self._rrf_fuse_results(result_groups)
        record_spot_check("rrf_top_10", _result_entries(all_results[:10]))

        # 跨文档聚合
        aggregated = self._cross_doc_aggregate(all_results, filters=filters)
        record_spot_check("aggregated_top_10", _result_entries(aggregated[:10]))

        # 获取完整 chunk 数据
        chunk_ids = [r["chunk_id"] for r in aggregated]
        chunks = await self._fetch_chunks(chunk_ids)

        # 重排序（使用 expanded query 的英文版本，对英文 chunks 更准）
        rerank_query = primary_query or normalized_original
        try:
            reranked = await self._rerank(rerank_query, chunks, cfg.rerank_top_n)
            final_chunks = [c for c, _ in reranked]
            scores = [s for _, s in reranked]
            record_spot_check(
                "rerank_top_10",
                [
                    {"chunk_id": chunk.chunk_id, "score": score}
                    for chunk, score in reranked[:10]
                ],
            )
        except Exception:
            logger.warning(
                "rerank_failed_falling_back_to_unranked_chunks",
                exc_info=True,
            )
            final_chunks = chunks[: cfg.rerank_top_n]
            scores = [0.0] * len(final_chunks)

        guide_chunks_from_main = self._collect_guide_chunks(final_chunks)
        groundedness = self._infer_groundedness_from_scores(scores)

        # Start guide retrieval early — independent of parent/cross-ref.
        guide_task: asyncio.Task[list[Chunk]] | None = None
        if self._should_fetch_guide_chunks(question_type, guide_hint):
            guide_task = asyncio.create_task(
                self._retrieve_guide_chunks(queries, original_query)
            )
        guide_example_task = asyncio.create_task(
            self._retrieve_guide_example_chunks(queries, original_query, guide_hint)
        )

        # 获取父 chunk
        parent_chunks = await self._fetch_parent_chunks(final_chunks)
        record_spot_check(
            "parent_chunks_injected",
            [
                {
                    "chunk_id": chunk.chunk_id,
                    "tokens": count_for_rerank(
                        chunk.embedding_text or chunk.content,
                        self.config.rerank_model,
                    )[0],
                    "source": chunk.metadata.source,
                    "clause_ids": list(chunk.metadata.clause_ids),
                }
                for chunk in parent_chunks
            ],
        )

        # deterministic object lookup：显式请求对象 + 主条款直接引用对象
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
        closure_seed_chunks = final_chunks[:1]
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
        record_spot_check(
            "ref_chunks",
            [
                {
                    "chunk_id": chunk.chunk_id,
                    "source": chunk.metadata.source,
                    "clause_ids": list(chunk.metadata.clause_ids),
                    "object_label": chunk.metadata.object_label,
                }
                for chunk in ref_chunks
            ],
        )
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
        groundedness = self._infer_groundedness_from_scores(scores)
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
        if unresolved_required_keys and groundedness == "grounded":
            groundedness = "partial"

        guide_chunks: list[Chunk] = list(guide_chunks_from_main)
        if guide_task is not None:
            retrieved_guide_chunks = await guide_task
            guide_chunks = self._append_unique_chunks(
                guide_chunks_from_main,
                retrieved_guide_chunks,
            )
        guide_example_chunks = await guide_example_task

        return RetrievalResult(
            chunks=final_chunks,
            parent_chunks=parent_chunks,
            scores=scores,
            guide_chunks=guide_chunks,
            guide_example_chunks=guide_example_chunks,
            ref_chunks=ref_chunks,
            groundedness=groundedness,
            resolved_refs=resolved_refs,
            unresolved_refs=unresolved_refs,
        )

    async def close(self) -> None:
        """清理 ES 连接资源。"""
        if self._es is not None:
            await self._es.close()
        await self._embedding_client.close()
        await self._rerank_client.close()
