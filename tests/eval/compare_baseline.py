"""Compare retrieval evaluation results against a stored baseline."""
from __future__ import annotations

import argparse
import json
import sys
from numbers import Real
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger()

EVAL_DIR = Path(__file__).parent
DEFAULT_RESULTS_PATH = EVAL_DIR / "eval_results.json"
DEFAULT_BASELINE_PATH = EVAL_DIR / "baselines" / "retrieval_baseline.json"
DEFAULT_TOLERANCE = 0.02
LOWER_IS_BETTER_METRICS = {"noise_intrusion_rate"}


def _load_json(path: Path) -> dict[str, Any]:
    """Load a JSON object from disk."""
    logger.info("baseline_compare_load_json", path=str(path))
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object at {path}")
    return data


def _is_number(value: Any) -> bool:
    return isinstance(value, Real) and not isinstance(value, bool)


def _status_for_metric(metric: str, baseline_value: float, current_value: float, tolerance: float) -> bool:
    if metric in LOWER_IS_BETTER_METRICS:
        return current_value <= baseline_value + tolerance
    return current_value >= baseline_value - tolerance


def _format_value(value: Any) -> str:
    if value is None:
        return "null"
    if _is_number(value):
        return f"{float(value):.4f}"
    return str(value)


def _print_comparison_table(rows: list[dict[str, Any]]) -> None:
    headers = ["metric", "baseline", "current", "diff", "status"]
    table_rows = [
        [
            row["metric"],
            _format_value(row["baseline"]),
            _format_value(row["current"]),
            _format_value(row["diff"]),
            row["status"],
        ]
        for row in rows
    ]
    widths = [
        max(len(headers[index]), *(len(row[index]) for row in table_rows))
        if table_rows else len(header)
        for index, header in enumerate(headers)
    ]

    print(" | ".join(header.ljust(widths[index]) for index, header in enumerate(headers)))
    print("-+-".join("-" * width for width in widths))
    for row in table_rows:
        print(" | ".join(value.ljust(widths[index]) for index, value in enumerate(row)))


def compare_metrics(baseline: dict[str, Any], results: dict[str, Any]) -> bool:
    """Compare numeric metrics and return True when all checked metrics pass."""
    baseline_metrics = baseline.get("metrics")
    current_metrics = results.get("metrics")
    if not isinstance(baseline_metrics, dict):
        raise ValueError("Baseline JSON is missing a metrics object")
    if not isinstance(current_metrics, dict):
        raise ValueError("Results JSON is missing a metrics object")

    tolerance = baseline.get("metadata", {}).get("tolerance", DEFAULT_TOLERANCE)
    if not _is_number(tolerance):
        raise ValueError("Baseline metadata.tolerance must be numeric when present")
    tolerance = float(tolerance)

    rows: list[dict[str, Any]] = []
    all_passed = True

    for metric, baseline_value in baseline_metrics.items():
        current_value = current_metrics.get(metric)
        if baseline_value is None or current_value is None:
            logger.info("baseline_compare_metric_skipped_null", metric=metric)
            continue
        if not _is_number(baseline_value):
            logger.info("baseline_compare_metric_skipped_non_numeric", metric=metric)
            continue
        if not _is_number(current_value):
            passed = False
            diff = None
            logger.warning(
                "baseline_compare_metric_current_non_numeric",
                metric=metric,
                current_value=current_value,
            )
        else:
            baseline_float = float(baseline_value)
            current_float = float(current_value)
            diff = current_float - baseline_float
            passed = _status_for_metric(metric, baseline_float, current_float, tolerance)

        status = "PASS" if passed else "FAIL"
        rows.append(
            {
                "metric": metric,
                "baseline": baseline_value,
                "current": current_value,
                "diff": diff,
                "status": status,
            }
        )
        all_passed = all_passed and passed
        logger.info(
            "baseline_compare_metric",
            metric=metric,
            baseline_value=baseline_value,
            current_value=current_value,
            diff=diff,
            status=status,
        )

    _print_comparison_table(rows)
    return all_passed


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare retrieval eval results against baseline")
    parser.add_argument(
        "--baseline-path",
        type=Path,
        default=DEFAULT_BASELINE_PATH,
        help=f"Baseline JSON path (default: {DEFAULT_BASELINE_PATH})",
    )
    parser.add_argument(
        "--results-path",
        type=Path,
        default=DEFAULT_RESULTS_PATH,
        help=f"Current eval results JSON path (default: {DEFAULT_RESULTS_PATH})",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    baseline = _load_json(args.baseline_path)
    results = _load_json(args.results_path)

    if compare_metrics(baseline, results):
        logger.info("baseline_compare_passed")
        return

    logger.error("baseline_compare_failed")
    sys.exit(1)


if __name__ == "__main__":
    main()
