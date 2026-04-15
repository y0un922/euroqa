#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

MODE=""

usage() {
  cat <<'EOF'
Usage:
  ./scripts/rebuild-indexes.sh
EOF
}

choose_mode() {
  echo "Select rebuild mode:"
  echo "1) with LLM summaries"
  echo "2) without LLM summaries"
  printf "> "
  read -r choice
  case "${choice}" in
    1) MODE="with-llm" ;;
    2) MODE="without-llm" ;;
    *) echo "Invalid choice: ${choice}" >&2; exit 1 ;;
  esac
}

if [[ $# -gt 1 ]]; then
  usage
  exit 1
fi

if [[ $# -eq 1 ]]; then
  case "${1}" in
    -h|--help) usage; exit 0 ;;
    *) usage; exit 1 ;;
  esac
fi

choose_mode

curl -sS -X DELETE "http://localhost:9200/eurocode_chunks" >/dev/null || true

./.venv/bin/python - <<'PY'
from pymilvus import connections, utility

connections.connect(host="localhost", port=19530)
if utility.has_collection("eurocode_chunks"):
    utility.drop_collection("eurocode_chunks")
print("dropped existing Milvus collection if present")
PY

if [[ "${MODE}" == "with-llm" ]]; then
  echo "rebuilding with LLM summaries via pipeline.run --start-stage 3"
  LLM_CONCURRENCY="${LLM_CONCURRENCY:-1}" uv run python -m pipeline.run --start-stage 3
  exit 0
fi

echo "rebuilding without LLM summaries from parsed markdown"

uv run python -X utf8 - <<'PY'
import asyncio
import json
from pathlib import Path

from pipeline.chunk import create_chunks, validate_unique_chunk_ids
from pipeline.config import PipelineConfig
from pipeline.index import index_to_elasticsearch, index_to_milvus
from pipeline.structure import (
    TreePruningConfig,
    parse_markdown_to_tree,
    prune_document_tree,
)


async def main() -> None:
    cfg = PipelineConfig()
    prune_cfg = TreePruningConfig.from_pipeline_settings(
        enabled=cfg.tree_pruning_enabled,
        body_start_titles=cfg.tree_pruning_body_start_titles,
    )

    all_chunks = []
    unresolved_ref_count = 0
    documents_with_unresolved_refs = 0
    for md_path in sorted(Path(cfg.parsed_dir).glob("*/*.md")):
        doc_id = md_path.stem
        source = doc_id.replace("_", " ")
        meta_path = md_path.parent / f"{doc_id}_meta.json"
        meta = (
            json.loads(meta_path.read_text(encoding="utf-8"))
            if meta_path.exists()
            else {}
        )
        content_list_path = md_path.parent / f"{doc_id}_content_list.json"
        content_list = (
            json.loads(content_list_path.read_text(encoding="utf-8"))
            if content_list_path.exists()
            else None
        )

        tree = prune_document_tree(
            parse_markdown_to_tree(
                md_path.read_text(encoding="utf-8"),
                source=source,
                content_list=content_list,
            ),
            prune_cfg,
        )
        chunks = create_chunks(tree, source_title=meta.get("title", source))
        validate_unique_chunk_ids(chunks)
        all_chunks.extend(chunks)
        doc_unresolved = sum(
            1
            for chunk in chunks
            if chunk.metadata.ref_labels
            and len(chunk.metadata.ref_labels) != len(chunk.metadata.ref_object_ids)
        )
        unresolved_ref_count += doc_unresolved
        if doc_unresolved:
            documents_with_unresolved_refs += 1

    milvus_count = await index_to_milvus(all_chunks, cfg)
    es_count = await index_to_elasticsearch(all_chunks, cfg)
    print(
        {
            "total_chunks": len(all_chunks),
            "milvus": milvus_count,
            "es": es_count,
            "documents_with_unresolved_refs": documents_with_unresolved_refs,
            "chunks_with_unresolved_refs": unresolved_ref_count,
        }
    )


asyncio.run(main())
PY
