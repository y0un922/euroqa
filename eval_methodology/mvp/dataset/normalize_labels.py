"""Normalize free-text client labels into structured tags + confidence.

MVP: rule-based heuristics (no LLM required for stratification). High/low
confidence flags support stratified splits; Match is NOT an A/B metric.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from eval_methodology.mvp.dataset.xlsx_io import load_excel_questions  # noqa: E402
from eval_methodology.mvp.paths import (  # noqa: E402
    DATA_DIR,
    DEFAULT_EXCEL,
    LABELS_JSON,
    QUESTIONS_JSON,
)


def _polarity(text: str | None, *, field: str = "generic") -> str:
    """Map free-text client labels to positive/negative/mixed/unknown.

    For hallucination column, short answers like「无」mean *no hallucination*
    (positive signal).
    """
    if not text:
        return "unknown"
    t = text.strip()
    tl = t.lower()

    # Hallucination column: 「无」/「无编造」= good.
    if field == "hallucination":
        if re.fullmatch(r"无|没有|无多余|无编造|无幻觉|none|no", t, re.I):
            return "positive"
        if any(k in t for k in ("编造", "幻觉", "多余", "捏造", "错误引用")):
            return "negative"

    neg = any(
        k in t
        for k in (
            "不正确",
            "错误",
            "不符",
            "不完整",
            "缺失",
            "有误",
            "未给出",
            "未涉及",
            "完全未",
        )
    )
    # 「基本正确」/「基本完整」count as mild positive, not pure negative.
    mild_pos = any(k in t for k in ("基本正确", "基本完整", "大体正确"))
    pos = any(
        k in t
        for k in (
            "正确",
            "完整",
            "符合",
            "通过",
            "合格",
        )
    ) or mild_pos
    # Bare English
    if re.fullmatch(r"ok|pass|yes|good", tl):
        pos = True
    if re.fullmatch(r"fail|wrong|no|bad", tl):
        neg = True

    if pos and neg:
        return "mixed"
    if neg:
        return "negative"
    if pos:
        return "positive"
    return "unknown"


def _verdict_bucket(text: str | None) -> str:
    if not text:
        return "unknown"
    t = text.strip()
    # Client scale often A/B/C.
    if re.match(r"^A\b", t) or "可直接使用" in t:
        return "pass"
    if re.match(r"^B\b", t):
        return "borderline"
    if re.match(r"^C\b", t) or re.search(r"不合格|不通过|失败|fail", t, re.I):
        return "fail"
    if re.search(r"合格|通过|优秀|良好|pass|ok", t, re.I):
        return "pass"
    if re.search(r"部分|边界|待|mixed", t, re.I):
        return "borderline"
    return "unknown"


def normalize_row(row_dict: dict[str, Any]) -> dict[str, Any]:
    corr = _polarity(row_dict.get("existing_correctness"), field="correctness")
    comp = _polarity(row_dict.get("existing_completeness"), field="completeness")
    hall = _polarity(row_dict.get("existing_hallucination"), field="hallucination")
    verdict = _verdict_bucket(row_dict.get("existing_verdict"))

    known = sum(1 for x in (corr, comp, hall, verdict) if x != "unknown")
    confidence = "high" if known >= 3 else ("medium" if known >= 1 else "low")

    # Stratification key for split.py
    stratum = f"v={verdict}|c={corr}"

    return {
        **row_dict,
        "labels": {
            "correctness": corr,
            "completeness": comp,
            "hallucination_signal": hall,
            "verdict": verdict,
            "confidence": confidence,
            "stratum": stratum,
        },
    }


def build_labels(
    excel_path: Path = DEFAULT_EXCEL,
    *,
    sheet: str = "questions",
    merge_test_questions: bool = True,
) -> dict[str, Any]:
    rows = load_excel_questions(excel_path, sheet_name=sheet)
    items = [
        normalize_row(
            {
                "id": r.id,
                "question": r.question,
                "existing_correctness": r.existing_correctness,
                "existing_completeness": r.existing_completeness,
                "existing_hallucination": r.existing_hallucination,
                "existing_verdict": r.existing_verdict,
                "question_type": r.question_type,
                "source": "excel",
            }
        )
        for r in rows
    ]

    # Optionally attach schema metadata from tests/eval/test_questions.json by
    # fuzzy question match (Excel is the authority for the 31-item set).
    if merge_test_questions and QUESTIONS_JSON.is_file():
        catalog = json.loads(QUESTIONS_JSON.read_text(encoding="utf-8"))
        by_q = {str(q["question"]).strip(): q for q in catalog}
        for item in items:
            hit = by_q.get(item["question"].strip())
            if hit:
                item["eval_catalog"] = {
                    "id": hit.get("id"),
                    "category": hit.get("category"),
                    "expected_type": hit.get("expected_type"),
                    "expected_sections": hit.get("expected_sections"),
                    "expected_keywords": hit.get("expected_keywords"),
                }
                if not item.get("question_type"):
                    item["question_type"] = hit.get("category")

    return {
        "source_excel": str(excel_path),
        "n": len(items),
        "items": items,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Normalize Excel free-text labels")
    parser.add_argument("--excel", type=Path, default=DEFAULT_EXCEL)
    parser.add_argument("--sheet", type=str, default="questions")
    parser.add_argument("--out", type=Path, default=LABELS_JSON)
    args = parser.parse_args(argv)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    payload = build_labels(args.excel, sheet=args.sheet)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {args.out} n={payload['n']}")
    high = sum(1 for i in payload["items"] if i["labels"]["confidence"] == "high")
    print(f"confidence high={high} low/med={payload['n'] - high}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
