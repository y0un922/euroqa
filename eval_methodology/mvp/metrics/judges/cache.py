"""Content-addressed judge cache.

Key = family + model id + prompt/schema version + question + answer
      + ordered context chunk content hash + citations.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from eval_methodology.mvp.paths import CACHE_DIR

PROMPT_SCHEMA_VERSION = "mvp-judge-v1"


def _stable_dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def context_content_hash(context_chunks: list[dict[str, Any]] | list[str]) -> str:
    if not context_chunks:
        payload = []
    elif isinstance(context_chunks[0], str):
        payload = list(context_chunks)
    else:
        payload = [
            {
                "chunk_id": c.get("chunk_id"),
                "content": c.get("content"),
            }
            for c in context_chunks  # type: ignore[union-attr]
        ]
    return hashlib.sha256(_stable_dumps(payload).encode("utf-8")).hexdigest()


def make_cache_key(
    *,
    family: str,
    model_id: str,
    question: str,
    answer: str,
    context_chunks: list[dict[str, Any]] | list[str],
    citations: Any,
    prompt_schema_version: str = PROMPT_SCHEMA_VERSION,
    kind: str = "judge",
) -> str:
    blob = {
        "kind": kind,
        "family": family,
        "model_id": model_id,
        "prompt_schema_version": prompt_schema_version,
        "question": question,
        "answer": answer,
        "context_hash": context_content_hash(context_chunks),
        "citations": citations,
    }
    return hashlib.sha256(_stable_dumps(blob).encode("utf-8")).hexdigest()


class JudgeCache:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or (CACHE_DIR / "judges")
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        return self.root / f"{key}.json"

    def get(self, key: str) -> dict[str, Any] | None:
        path = self._path(key)
        if not path.is_file():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def set(self, key: str, value: dict[str, Any]) -> None:
        path = self._path(key)
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
