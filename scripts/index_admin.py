"""CLI for Milvus/Elasticsearch index administration."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from server.services import index_admin  # noqa: E402


def _print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Manage Euro_QA search indexes.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("overview", help="Show Milvus/Elasticsearch overview.")

    inspect_parser = subparsers.add_parser("inspect", help="Inspect one document.")
    inspect_parser.add_argument("doc_id")
    inspect_parser.add_argument("--sample-size", type=int, default=5)

    delete_parser = subparsers.add_parser("delete", help="Delete one document index.")
    delete_parser.add_argument("doc_id")

    rebuild_parser = subparsers.add_parser(
        "rebuild",
        help="Rebuild one document from data/parsed without reparsing PDF.",
    )
    rebuild_parser.add_argument("doc_id")
    rebuild_parser.add_argument(
        "--no-delete-first",
        action="store_true",
        help="Do not delete existing indexed chunks before reindexing.",
    )

    return parser.parse_args()


async def main_async() -> None:
    args = parse_args()
    if args.command == "overview":
        _print_json(await index_admin.index_overview())
        return
    if args.command == "inspect":
        _print_json(
            await index_admin.inspect_document_index(
                args.doc_id,
                sample_size=args.sample_size,
            )
        )
        return
    if args.command == "delete":
        _print_json(await index_admin.delete_document_index(args.doc_id))
        return
    if args.command == "rebuild":
        _print_json(
            await index_admin.rebuild_document_index(
                args.doc_id,
                delete_first=not args.no_delete_first,
            )
        )
        return
    raise ValueError(f"Unknown command: {args.command}")


def main() -> None:
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
