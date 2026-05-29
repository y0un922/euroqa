"""Run the offline eval gate for retrieval baseline and generation snapshots."""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import structlog

logger = structlog.get_logger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _run_step(name: str, command: list[str]) -> bool:
    """Run one gate step and return whether it passed."""
    logger.info("eval_gate_step_start", name=name, command=command)
    print(f"\n=== {name} ===")
    result = subprocess.run(command, cwd=PROJECT_ROOT, check=False)
    passed = result.returncode == 0
    logger.info(
        "eval_gate_step_complete",
        name=name,
        returncode=result.returncode,
        status="PASS" if passed else "FAIL",
    )
    return passed


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run offline eval gate checks")
    parser.add_argument(
        "--skip-snapshots",
        action="store_true",
        help="跳过生成侧 characterization snapshot tests",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    retrieval_passed = _run_step(
        "检索基线",
        [
            sys.executable,
            "tests/eval/compare_baseline.py",
        ],
    )
    if args.skip_snapshots:
        snapshots_passed = True
        logger.info("eval_gate_snapshots_skipped")
    else:
        snapshots_passed = _run_step(
            "特征化快照",
            [
                sys.executable,
                "-m",
                "pytest",
                "tests/eval/test_characterization_generation.py",
            ],
        )

    print("\n=== Eval gate summary ===")
    print(f"检索基线: {'PASS' if retrieval_passed else 'FAIL'}")
    if args.skip_snapshots:
        print("特征化快照: SKIPPED")
    else:
        print(f"特征化快照: {'PASS' if snapshots_passed else 'FAIL'}")

    if not retrieval_passed or not snapshots_passed:
        logger.error(
            "eval_gate_failed",
            retrieval_passed=retrieval_passed,
            snapshots_passed=snapshots_passed,
        )
        sys.exit(1)
    logger.info("eval_gate_passed")


if __name__ == "__main__":
    main()
