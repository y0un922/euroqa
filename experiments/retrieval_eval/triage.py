"""Generate failure-mode triage markdown from a baseline result JSON."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from experiments.retrieval_eval.triage_rules import (  # noqa: E402
    FAILURE_MODES,
    classify_failure_modes,
)


def main() -> None:
    args = _parse_args()
    payload = json.loads(args.result_json.read_text(encoding="utf-8"))
    per_question = payload.get("per_question") or []
    rows, counts = _triage_rows(per_question)

    output = args.output or _default_output_path()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(_render_markdown(args.result_json, rows, counts), encoding="utf-8")
    print(f"Wrote {output}")
    print(_render_distribution(counts, len(per_question)))


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("result_json", type=Path)
    parser.add_argument("--output", type=Path, default=None)
    return parser.parse_args()


def _triage_rows(per_question: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], Counter[str]]:
    rows: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    for row in per_question:
        findings = classify_failure_modes(row)
        for finding in findings:
            counts[finding.code] += 1
        rows.append(
            {
                "id": row.get("id", ""),
                "question": row.get("question", ""),
                "category": row.get("category", ""),
                "review_bucket": row.get("review_bucket", ""),
                "findings": [finding.to_dict() for finding in findings],
                "error": row.get("error", ""),
            }
        )
    return rows, counts


def _render_markdown(
    source: Path,
    rows: list[dict[str, Any]],
    counts: Counter[str],
) -> str:
    total = len(rows)
    parts = [
        "# Retrieval Triage Report",
        "",
        f"- Source: `{source}`",
        f"- Generated: {datetime.now().isoformat(timespec='seconds')}",
        f"- Questions: {total}",
        "",
        "## Global Distribution",
        "",
        _render_distribution(counts, total),
        "",
        "## Per Question",
        "",
        "| ID | Category | Review | Failure Modes | Detail |",
        "|---|---|---|---|---|",
    ]
    for row in rows:
        findings = row["findings"]
        modes = ", ".join(finding["label"] for finding in findings) or "-"
        details = "<br>".join(finding["detail"] for finding in findings) or "-"
        if row.get("error"):
            details = f"ERROR: {row['error']}"
        parts.append(
            "| {id} | {category} | {review} | {modes} | {details} |".format(
                id=_md(row["id"]),
                category=_md(row["category"]),
                review=_md(row["review_bucket"]),
                modes=_md(modes),
                details=_md(details),
            )
        )
    parts.append("")
    return "\n".join(parts)


def _render_distribution(counts: Counter[str], total: int) -> str:
    lines = ["| 失败模式 | 题数 | 占比 |", "|---|---:|---:|"]
    denominator = total or 1
    for code, label in FAILURE_MODES.items():
        count = counts.get(code, 0)
        lines.append(f"| {label} | {count} | {count / denominator:.1%} |")
    return "\n".join(lines)


def _default_output_path() -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return Path(f"experiments/retrieval_eval/results/triage_{stamp}.md")


def _md(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


if __name__ == "__main__":
    main()
