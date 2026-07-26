"""Human confirmation workflow for supported gold items (CRec sign-off).

The 15 `gold_claim_status == "supported"` items carry model-cross-reviewed
evidence locators. CRec stays "diagnostic only" until a named human reviewer
confirms each item's minimal sufficient evidence set. This CLI keeps that step
cheap: quote existence in the parsed corpus is checked deterministically, so
the reviewer only judges whether the quotes actually support the claims.

Usage:
    uv run python -m eval_methodology.mvp.dataset.confirm_gold status
    uv run python -m eval_methodology.mvp.dataset.confirm_gold packet
    uv run python -m eval_methodology.mvp.dataset.confirm_gold confirm \
        --ids all --reviewer <name> [--note "..."]
    uv run python -m eval_methodology.mvp.dataset.confirm_gold reject \
        --ids Q14 --reviewer <name> --note "evidence not minimal"
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from eval_methodology.mvp.metrics.diagnostics import _normalize_text  # noqa: E402
from eval_methodology.mvp.paths import (  # noqa: E402
    DATASET_JSON,
    PARSED_CORPUS_DIR,
    REVIEW_DIR,
)

QUOTE_PREVIEW_CHARS = 260


def supported_items(data: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        item
        for item in data["items"]
        if (item.get("gold") or {}).get("gold_claim_status") == "supported"
    ]


def _corpus_file(parsed_dir: Path, document_path: str) -> Path | None:
    candidate = (parsed_dir / document_path).resolve()
    if not str(candidate).startswith(str(parsed_dir.resolve())):
        return None
    return candidate if candidate.is_file() else None


def verify_evidence(
    item: dict[str, Any], parsed_dir: Path
) -> list[dict[str, Any]]:
    """Deterministically check each evidence quote against the parsed corpus."""
    results = []
    for locator in (item.get("gold") or {}).get("evidence") or []:
        document_path = str(locator.get("document_path") or "")
        quote = _normalize_text(str(locator.get("quote") or ""))
        source = _corpus_file(parsed_dir, document_path)
        found = False
        if source is not None and quote:
            found = quote in _normalize_text(source.read_text(encoding="utf-8"))
        results.append(
            {
                "evidence_id": str(locator.get("evidence_id") or ""),
                "document_path": document_path,
                "section": str(locator.get("section") or ""),
                "quote": str(locator.get("quote") or ""),
                "file_exists": source is not None,
                "quote_found": found,
            }
        )
    return results


def review_state(item: dict[str, Any]) -> str:
    review = (item.get("gold") or {}).get("human_review")
    if not isinstance(review, dict):
        return "unreviewed"
    return "confirmed" if review.get("confirmed") else "rejected"


def apply_review(
    data: dict[str, Any],
    ids: list[str],
    *,
    reviewer: str,
    confirmed: bool,
    note: str = "",
) -> list[str]:
    """Set human_review on supported items; returns the ids actually updated."""
    if not reviewer.strip():
        raise ValueError("reviewer must not be empty")
    eligible = {item["id"]: item for item in supported_items(data)}
    targets = list(eligible) if ids == ["all"] else ids
    unknown = [qid for qid in targets if qid not in eligible]
    if unknown:
        raise ValueError(
            f"not supported gold items: {', '.join(unknown)} "
            f"(eligible: {', '.join(sorted(eligible))})"
        )
    stamp = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    for qid in targets:
        eligible[qid]["gold"]["human_review"] = {
            "confirmed": confirmed,
            "reviewer": reviewer.strip(),
            "reviewed_at": stamp,
            "note": note,
        }
    return targets


def build_packet(data: dict[str, Any], parsed_dir: Path) -> str:
    lines = [
        "# Gold 人工确认包（CRec sign-off）",
        "",
        "复核目标：判断每题的证据集是否**最小且充分**地支持 gold claims。",
        "引用是否逐字存在于语料已由脚本确定性校验（下表 quote_found 列），",
        "✗ 的条目必须驳回或修正后再确认。",
        "",
        "确认命令：",
        "```bash",
        "uv run python -m eval_methodology.mvp.dataset.confirm_gold confirm \\",
        "    --ids Q01,Q04 --reviewer <你的名字>",
        "```",
        "",
    ]
    for item in supported_items(data):
        gold = item["gold"]
        checks = verify_evidence(item, parsed_dir)
        all_found = all(c["quote_found"] for c in checks) if checks else False
        lines.extend(
            [
                f"## {item['id']} — {review_state(item)}"
                + ("" if all_found else " ⚠️ 有引用未通过语料校验"),
                "",
                f"**问题**：{item.get('question', '')}",
                "",
                "**Gold claims**：",
                "",
            ]
        )
        for claim in gold.get("claims") or []:
            lines.append(f"- [{claim.get('status', '')}] {claim.get('text', '')}")
        lines.extend(["", "**证据（最小充分性由你判断）**：", ""])
        for check in checks:
            mark = "✓" if check["quote_found"] else "✗"
            quote = check["quote"][:QUOTE_PREVIEW_CHARS]
            if len(check["quote"]) > QUOTE_PREVIEW_CHARS:
                quote += "…"
            lines.extend(
                [
                    f"- `{check['evidence_id']}` {mark} "
                    f"`{check['document_path']}` — {check['section']}",
                    f"  > {quote}",
                ]
            )
        lines.append("")
    return "\n".join(lines)


def _load(dataset_path: Path) -> dict[str, Any]:
    return json.loads(dataset_path.read_text(encoding="utf-8"))


def _save(dataset_path: Path, data: dict[str, Any]) -> None:
    dataset_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Confirm supported gold items")
    parser.add_argument("--dataset", type=Path, default=DATASET_JSON)
    parser.add_argument("--parsed-dir", type=Path, default=PARSED_CORPUS_DIR)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status")
    packet = sub.add_parser("packet")
    packet.add_argument("--out", type=Path, default=REVIEW_DIR / "gold_confirmation_packet.md")
    for name in ("confirm", "reject"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--ids", required=True, help="comma-separated ids or 'all'")
        cmd.add_argument("--reviewer", required=True)
        cmd.add_argument("--note", default="")
    args = parser.parse_args(argv)

    data = _load(args.dataset)
    if args.command == "status":
        for item in supported_items(data):
            review = (item.get("gold") or {}).get("human_review") or {}
            print(
                f"{item['id']}: {review_state(item)}"
                + (f" ({review.get('reviewer')} @ {review.get('reviewed_at')})" if review else "")
            )
        return 0
    if args.command == "packet":
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(build_packet(data, args.parsed_dir), encoding="utf-8")
        print(f"wrote {args.out}")
        return 0

    ids = [part.strip() for part in args.ids.split(",") if part.strip()]
    updated = apply_review(
        data,
        ids,
        reviewer=args.reviewer,
        confirmed=(args.command == "confirm"),
        note=args.note,
    )
    _save(args.dataset, data)
    print(f"{args.command}ed {len(updated)} items: {', '.join(updated)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
