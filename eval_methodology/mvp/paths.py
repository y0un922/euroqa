"""Canonical paths for the eval methodology MVP (all under eval_methodology/)."""

from __future__ import annotations

from pathlib import Path

MVP_ROOT = Path(__file__).resolve().parent
EVAL_ROOT = MVP_ROOT.parent
PROJECT_ROOT = EVAL_ROOT.parent
PARSED_CORPUS_DIR = PROJECT_ROOT / "data" / "parsed"

DATA_DIR = MVP_ROOT / "data"
CACHE_DIR = MVP_ROOT / "cache"
ARTIFACTS_DIR = MVP_ROOT / "artifacts"
SCHEMAS_DIR = MVP_ROOT / "schemas"
REPORTS_DIR = MVP_ROOT / "reports"
REVIEW_DIR = EVAL_ROOT / "review"

DATASET_JSON = DATA_DIR / "dataset.json"
SPLIT_JSON = DATA_DIR / "split.json"
LABELS_JSON = DATA_DIR / "labels.json"
GOLD_JSON = DATA_DIR / "gold.json"

QUESTIONS_JSON = PROJECT_ROOT / "tests" / "eval" / "test_questions.json"
DEFAULT_EXCEL = PROJECT_ROOT / "outputs" / "评估结果_问题集_202606.xlsx"
ENV_FILE = PROJECT_ROOT / ".env"

# Sidecar default ports (baseline / candidate).
BASELINE_PORT = 18080
CANDIDATE_PORT = 18081

# Bootstrap / gate constants (main.tex + MVP_PLAN §E.2).
BOOTSTRAP_B = 1000
BOOTSTRAP_SEED = 20260613
MIN_EFFECTIVE_N = 15
MAX_JUDGE_DROP_RATE = 0.30
DEFAULT_EPSILON = 0.05
DEFAULT_DELTA = 0.05
CONTEXT_DIFF_MIN_QUESTIONS = 3

# Version tag bound to code + split.
MVP_DATASET_VERSION = "mvp-v1-20260613"
