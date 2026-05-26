"""Repair indexed document display titles from parse_options.json.

Run from the server project root. The script reads
``data/parsed/<doc_id>/parse_options.json`` and uses the persisted
``file_name`` as the readable display title while keeping ``source`` as the
stable backend document id.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib import error, parse, request


DEFAULT_ES_URL = "http://localhost:9200"
DEFAULT_ES_INDEX = "eurocode_chunks"
DEFAULT_PARSED_DIR = "data/parsed"
DEFAULT_MILVUS_HOST = "localhost"
DEFAULT_MILVUS_PORT = "19530"
DEFAULT_MILVUS_COLLECTION = "eurocode_chunks"

DISPLAY_FIELDS = ("source_title", "display_title")


@dataclass(frozen=True)
class RepairTarget:
    doc_id: str
    file_name: str
    source_aliases: tuple[str, ...]


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"[skip] {path}: cannot read json: {exc}", file=sys.stderr)
        return None
    return payload if isinstance(payload, dict) else None


def _parse_file_name(payload: dict[str, Any]) -> str:
    for key in ("file_name", "filename", "fileName"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _source_aliases(doc_id: str, include_legacy_space_alias: bool) -> tuple[str, ...]:
    aliases = [doc_id]
    legacy = doc_id.replace("_", " ")
    if include_legacy_space_alias and legacy != doc_id:
        aliases.append(legacy)
    return tuple(dict.fromkeys(aliases))


def load_targets(
    parsed_dir: Path,
    *,
    include_legacy_space_alias: bool,
) -> list[RepairTarget]:
    targets: list[RepairTarget] = []
    for options_path in sorted(parsed_dir.glob("*/parse_options.json")):
        payload = _read_json(options_path)
        if payload is None:
            continue
        file_name = _parse_file_name(payload)
        doc_id = options_path.parent.name
        if not file_name:
            print(f"[skip] {doc_id}: missing file_name", file=sys.stderr)
            continue
        targets.append(
            RepairTarget(
                doc_id=doc_id,
                file_name=file_name,
                source_aliases=_source_aliases(doc_id, include_legacy_space_alias),
            )
        )
    return targets


def _es_request(
    es_url: str,
    method: str,
    path: str,
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    data = None
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = request.Request(
        f"{es_url.rstrip('/')}{path}",
        data=data,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    try:
        with request.urlopen(req, timeout=120) as response:
            raw = response.read().decode("utf-8")
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"ES {method} {path} failed: {exc.code} {detail}") from exc
    return json.loads(raw) if raw else {}


def _es_terms_query(target: RepairTarget) -> dict[str, Any]:
    return {"terms": {"source": list(target.source_aliases)}}


def inspect_es_target(es_url: str, es_index: str, target: RepairTarget) -> tuple[int, str]:
    response = _es_request(
        es_url,
        "POST",
        f"/{parse.quote(es_index)}/_search",
        {
            "size": 1,
            "_source": ["source", "source_title", "display_title"],
            "query": _es_terms_query(target),
        },
    )
    total = response.get("hits", {}).get("total", {})
    count = total.get("value", 0) if isinstance(total, dict) else int(total or 0)
    hits = response.get("hits", {}).get("hits", [])
    current_title = ""
    if hits:
        source = hits[0].get("_source", {})
        current_title = str(source.get("source_title") or source.get("display_title") or "")
    return int(count), current_title


def update_es_target(es_url: str, es_index: str, target: RepairTarget) -> int:
    response = _es_request(
        es_url,
        "POST",
        f"/{parse.quote(es_index)}/_update_by_query?refresh=true&conflicts=proceed",
        {
            "script": {
                "lang": "painless",
                "source": """
                    ctx._source.source_title = params.file_name;
                    ctx._source.display_title = params.file_name;
                """,
                "params": {"file_name": target.file_name},
            },
            "query": _es_terms_query(target),
        },
    )
    return int(response.get("updated", 0) or 0)


def _escape_milvus_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _milvus_expr(target: RepairTarget) -> str:
    aliases = ", ".join(f'"{_escape_milvus_string(alias)}"' for alias in target.source_aliases)
    return f"source in [{aliases}]"


def _schema_field_names(collection: Any) -> list[str]:
    return [field.name for field in collection.schema.fields]


def _query_milvus_rows(
    collection: Any,
    expr: str,
    output_fields: list[str],
    *,
    batch_size: int,
):
    offset = 0
    while True:
        rows = collection.query(
            expr=expr,
            output_fields=output_fields,
            offset=offset,
            limit=batch_size,
        )
        if not rows:
            break
        yield rows
        offset += len(rows)


def repair_milvus_targets(
    *,
    host: str,
    port: str,
    collection_name: str,
    targets: list[RepairTarget],
    apply: bool,
    batch_size: int,
) -> None:
    try:
        from pymilvus import Collection, connections, utility
    except Exception as exc:
        print(f"[milvus] skip: pymilvus unavailable: {exc}")
        return

    connections.connect(host=host, port=port)
    if not utility.has_collection(collection_name):
        print(f"[milvus] skip: collection not found: {collection_name}")
        return

    collection = Collection(collection_name)
    collection.load()
    field_names = _schema_field_names(collection)
    writable_display_fields = [field for field in DISPLAY_FIELDS if field in field_names]
    print(
        "[milvus] collection="
        f"{collection_name} fields={field_names} display_fields={writable_display_fields}"
    )

    if not writable_display_fields:
        print("[milvus] no source_title/display_title fields; source identity left unchanged")
        for target in targets:
            rows = collection.query(
                expr=_milvus_expr(target),
                output_fields=["source"],
                limit=1,
            )
            print(f"[milvus] {target.doc_id}: {'found' if rows else 'not_found'}")
        return

    total_updated = 0
    for target in targets:
        expr = _milvus_expr(target)
        target_count = 0
        for rows in _query_milvus_rows(
            collection,
            expr,
            field_names,
            batch_size=batch_size,
        ):
            target_count += len(rows)
            if apply:
                repaired_rows = []
                for row in rows:
                    repaired = dict(row)
                    for field in writable_display_fields:
                        repaired[field] = target.file_name
                    repaired_rows.append(repaired)
                collection.upsert(repaired_rows)
                total_updated += len(repaired_rows)
        print(
            f"[milvus] {target.doc_id}: rows={target_count} "
            f"target={target.file_name!r} updated={target_count if apply else 0}"
        )

    if apply and total_updated:
        collection.flush()
        print(f"[milvus] flushed updated rows={total_updated}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="write changes")
    parser.add_argument(
        "--parsed-dir",
        default=os.getenv("PARSED_DIR", DEFAULT_PARSED_DIR),
        help="parsed document directory",
    )
    parser.add_argument(
        "--es-url",
        default=os.getenv("ES_URL", DEFAULT_ES_URL),
        help="Elasticsearch URL",
    )
    parser.add_argument(
        "--es-index",
        default=os.getenv("ES_INDEX", DEFAULT_ES_INDEX),
        help="Elasticsearch index",
    )
    parser.add_argument(
        "--milvus-host",
        default=os.getenv("MILVUS_HOST", DEFAULT_MILVUS_HOST),
        help="Milvus host",
    )
    parser.add_argument(
        "--milvus-port",
        default=os.getenv("MILVUS_PORT", DEFAULT_MILVUS_PORT),
        help="Milvus port",
    )
    parser.add_argument(
        "--milvus-collection",
        default=os.getenv("MILVUS_COLLECTION", DEFAULT_MILVUS_COLLECTION),
        help="Milvus collection",
    )
    parser.add_argument(
        "--skip-es",
        action="store_true",
        help="skip Elasticsearch repair",
    )
    parser.add_argument(
        "--skip-milvus",
        action="store_true",
        help="skip Milvus inspection/repair",
    )
    parser.add_argument(
        "--no-legacy-space-alias",
        action="store_true",
        help="do not also match doc_id with underscores replaced by spaces",
    )
    parser.add_argument("--batch-size", type=int, default=500)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    parsed_dir = Path(args.parsed_dir)
    targets = load_targets(
        parsed_dir,
        include_legacy_space_alias=not args.no_legacy_space_alias,
    )
    print(f"mode={'APPLY' if args.apply else 'DRY-RUN'}")
    print(f"parsed_dir={parsed_dir}")
    print(f"targets={len(targets)}")
    if not targets:
        print("No parse_options.json files with file_name found.")
        return 1

    if not args.skip_es:
        print(f"[es] url={args.es_url} index={args.es_index}")
        for target in targets:
            count, current_title = inspect_es_target(args.es_url, args.es_index, target)
            print(
                f"[es] {target.doc_id}: aliases={list(target.source_aliases)} "
                f"chunks={count} current={current_title!r} target={target.file_name!r}"
            )
            if args.apply and count:
                updated = update_es_target(args.es_url, args.es_index, target)
                print(f"[es] {target.doc_id}: updated={updated}")

    if not args.skip_milvus:
        repair_milvus_targets(
            host=args.milvus_host,
            port=args.milvus_port,
            collection_name=args.milvus_collection,
            targets=targets,
            apply=args.apply,
            batch_size=args.batch_size,
        )

    print("done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
