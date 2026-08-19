"""Shared embedding and rerank model clients."""

from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Any, ClassVar
from urllib.parse import urlsplit, urlunsplit

import httpx
import structlog

from shared.usage import record_usage, vendor_from_base_url

logger = structlog.get_logger()


def _build_headers(api_key: str) -> dict[str, str]:
    """Build standard JSON headers for remote model APIs."""
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def _require_remote_url(kind: str, api_url: str) -> None:
    """Validate required remote endpoint configuration."""
    if not api_url:
        raise RuntimeError(f"{kind} api_url is required when provider=remote")


def _resolve_remote_endpoint(api_url: str, endpoint_suffix: str) -> str:
    """Resolve a remote API URL to a concrete endpoint path."""
    parsed = urlsplit(api_url)
    path = parsed.path.rstrip("/")
    tail = path.rsplit("/", 1)[-1] if path else ""

    if path.endswith(endpoint_suffix):
        resolved_path = path
    elif not path or tail == "v1":
        resolved_path = f"{path}{endpoint_suffix}" if path else endpoint_suffix
    else:
        resolved_path = path

    return urlunsplit(parsed._replace(path=resolved_path))


@dataclass(slots=True)
class EmbeddingClient:
    """Embedding client supporting local FlagEmbedding and remote HTTP APIs."""

    provider: str
    model: str
    api_url: str = ""
    api_key: str = ""
    request_timeout_seconds: float = 120.0
    batch_size: int = 8
    max_connections: int = 100
    max_keepalive_connections: int = 20

    _local_models: ClassVar[dict[str, Any]] = {}
    _client: httpx.AsyncClient | None = None

    @classmethod
    def _get_local_model(cls, model_name: str) -> Any:
        if model_name not in cls._local_models:
            from FlagEmbedding import BGEM3FlagModel

            cls._local_models[model_name] = BGEM3FlagModel(
                model_name,
                use_fp16=True,
            )
        return cls._local_models[model_name]

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Return dense vectors for input texts."""
        if not texts:
            return []
        if self.provider.lower() == "remote":
            if self.batch_size <= 0 or len(texts) <= self.batch_size:
                return await self._embed_remote(texts)

            embeddings: list[list[float]] = []
            for start in range(0, len(texts), self.batch_size):
                batch = texts[start : start + self.batch_size]
                embeddings.extend(await self._embed_remote(batch))
            return embeddings
        return self._embed_local(texts)

    def _embed_local(self, texts: list[str]) -> list[list[float]]:
        model = self._get_local_model(self.model)
        result = model.encode(
            texts,
            return_dense=True,
            return_sparse=False,
            return_colbert_vecs=False,
        )
        return result["dense_vecs"].tolist()

    async def _embed_remote(self, texts: list[str]) -> list[list[float]]:
        _require_remote_url("embedding", self.api_url)
        endpoint = _resolve_remote_endpoint(self.api_url, "/embeddings")
        response = await self._get_client().post(
            endpoint,
            headers=_build_headers(self.api_key),
            json={"model": self.model, "input": texts},
        )
        response.raise_for_status()
        payload = response.json()
        record_usage(
            model=self.model,
            vendor=vendor_from_base_url(self.api_url),
            payload=payload,
        )
        data = payload.get("data")
        if not isinstance(data, list):
            raise RuntimeError("Remote embedding API response missing data list")
        ordered = sorted(data, key=lambda item: item.get("index", 0))
        return [item["embedding"] for item in ordered]

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=self.request_timeout_seconds,
                limits=httpx.Limits(
                    max_connections=self.max_connections,
                    max_keepalive_connections=self.max_keepalive_connections,
                ),
            )
        return self._client

    async def close(self) -> None:
        """Close the remote HTTP client if it was created."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None


@dataclass(slots=True)
class RerankClient:
    """Rerank client supporting local FlagEmbedding and remote HTTP APIs."""

    provider: str
    model: str
    api_url: str = ""
    api_key: str = ""
    request_timeout_seconds: float = 120.0
    max_length: int = 8192
    supports_max_length: bool = True
    max_connections: int = 100
    max_keepalive_connections: int = 20

    _local_models: ClassVar[dict[str, Any]] = {}
    _client: httpx.AsyncClient | None = None

    @classmethod
    def _get_local_model(cls, model_name: str) -> Any:
        if model_name not in cls._local_models:
            from FlagEmbedding import FlagReranker

            cls._local_models[model_name] = FlagReranker(
                model_name,
                use_fp16=True,
            )
        return cls._local_models[model_name]

    async def rerank(
        self,
        query: str,
        documents: list[str],
        top_n: int,
    ) -> list[tuple[int, float]]:
        """Return ranked document indexes and scores."""
        if not documents:
            return []
        if self.provider.lower() == "remote":
            return await self._rerank_remote(query, documents, top_n)
        return self._rerank_local(query, documents, top_n)

    def _rerank_local(
        self,
        query: str,
        documents: list[str],
        top_n: int,
    ) -> list[tuple[int, float]]:
        model = self._get_local_model(self.model)
        scores = model.compute_score([(query, document) for document in documents])
        if isinstance(scores, float):
            scores = [scores]
        ranked = sorted(
            enumerate(scores),
            key=lambda item: item[1],
            reverse=True,
        )
        return [(index, float(score)) for index, score in ranked[:top_n]]

    async def _rerank_remote(
        self,
        query: str,
        documents: list[str],
        top_n: int,
    ) -> list[tuple[int, float]]:
        _require_remote_url("rerank", self.api_url)
        endpoint = _resolve_remote_endpoint(self.api_url, "/rerank")
        body = {
            "model": self.model,
            "query": query,
            "documents": documents,
            "top_n": top_n,
        }
        if self.supports_max_length and self.max_length > 0:
            body["max_length"] = self.max_length

        response = await self._post_rerank(endpoint, body)
        if response.status_code == 400 and "max_length" in body:
            logger.warning(
                "remote_rerank_max_length_unsupported",
                status_code=response.status_code,
                model=self.model,
                endpoint=endpoint,
                max_length=self.max_length,
            )
            self.supports_max_length = False
            fallback_body = dict(body)
            fallback_body.pop("max_length", None)
            response = await self._post_rerank(endpoint, fallback_body)
        response.raise_for_status()
        payload = response.json()
        record_usage(
            model=self.model,
            vendor=vendor_from_base_url(self.api_url),
            payload=payload,
        )
        results = payload.get("results") or payload.get("data")
        if not isinstance(results, list):
            raise RuntimeError("Remote rerank API response missing results list")

        ranked: list[tuple[int, float]] = []
        for item in results:
            index = item.get("index")
            score = item.get("relevance_score", item.get("score"))
            if index is None or score is None:
                raise RuntimeError("Remote rerank API returned invalid result item")
            ranked.append((int(index), float(score)))
        ranked.sort(key=lambda item: item[1], reverse=True)
        return ranked[:top_n]

    async def _post_rerank(
        self,
        endpoint: str,
        body: dict[str, Any],
    ) -> httpx.Response:
        started = time.perf_counter()
        response = await self._get_client().post(
            endpoint,
            headers=_build_headers(self.api_key),
            json=body,
        )
        logger.info(
            "remote_rerank_request",
            status_code=response.status_code,
            elapsed_ms=round((time.perf_counter() - started) * 1000, 2),
            model=self.model,
            document_count=len(body.get("documents", [])),
            top_n=body.get("top_n"),
            max_length=body.get("max_length"),
            sent_max_length="max_length" in body,
            supports_max_length=self.supports_max_length,
        )
        return response

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=self.request_timeout_seconds,
                limits=httpx.Limits(
                    max_connections=self.max_connections,
                    max_keepalive_connections=self.max_keepalive_connections,
                ),
            )
        return self._client

    async def close(self) -> None:
        """Close the remote HTTP client if it was created."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None


def build_embedding_client(config: Any) -> EmbeddingClient:
    """Build an embedding client from pipeline or server config."""
    return EmbeddingClient(
        provider=config.embedding_provider,
        model=config.embedding_model,
        api_url=config.embedding_api_url,
        api_key=config.embedding_api_key,
        request_timeout_seconds=config.embedding_request_timeout_seconds,
        batch_size=getattr(config, "embedding_batch_size", 8),
        max_connections=getattr(config, "httpx_max_connections", 100),
        max_keepalive_connections=getattr(
            config, "httpx_max_keepalive_connections", 20
        ),
    )


def build_rerank_client(config: Any) -> RerankClient:
    """Build a rerank client from pipeline or server config."""
    return RerankClient(
        provider=config.rerank_provider,
        model=config.rerank_model,
        api_url=config.rerank_api_url,
        api_key=config.rerank_api_key,
        request_timeout_seconds=config.rerank_request_timeout_seconds,
        max_length=getattr(config, "rerank_max_length", 8192),
        max_connections=getattr(config, "httpx_max_connections", 100),
        max_keepalive_connections=getattr(
            config, "httpx_max_keepalive_connections", 20
        ),
    )
