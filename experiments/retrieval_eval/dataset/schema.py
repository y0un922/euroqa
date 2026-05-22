"""V2 question schema for the retrieval evaluation sandbox.

兼容 tests/eval/test_questions.json 的字段，扩展支持多文档的 expected_documents。
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ExpectedDoc:
    """跨文档检索的金标：每个文档下应命中的章节与对象。"""

    doc: str                       # 规范化文档标识，如 "EN1992", "EN1990", "DG_EN1992", "EN206-1"
    sections: list[str] = field(default_factory=list)  # 章节号，如 ["2.4.2.4", "5.3.1"]
    objects: list[str] = field(default_factory=list)   # Table/Annex/Figure/Eq/Ch 等，如 ["Table 2.1N", "Annex A1"]


@dataclass
class QuestionV2:
    """单题金标。每题对应 golden_dataset_reviewed.xlsx 的一行。"""

    id: str
    question: str
    category: str                  # broad / exact_ref / parameter_lookup / concept / reasoning
    review_bucket: str             # 通过 / 小幅修改 / 中等修改 / 重大修改
    expected_documents: list[ExpectedDoc]
    expected_sections: list[str]   # 所有 expected_documents.sections 的 flat union，旧脚本兼容
    expected_keywords: list[str]   # 用于关键词召回评测
    expected_concepts: list[str]   # 「应检索到的点-关键概念」列拆分
    expected_answer_points: list[str]    # 「应回答到的点-要点」
    expected_formulas: list[str]   # 「应回答到的点-关键公式/数值」
    must_not_include: list[str] = field(default_factory=list)
    notes: dict[str, Any] = field(default_factory=dict)


def is_multi_doc(q: QuestionV2) -> bool:
    return len(q.expected_documents) > 1


def to_jsonable(q: QuestionV2) -> dict:
    """Convert to a dict suitable for json.dump."""
    data = asdict(q)
    return data


def from_jsonable(data: dict) -> QuestionV2:
    """Inverse of to_jsonable; raises on missing required fields."""
    docs = [ExpectedDoc(**d) for d in data["expected_documents"]]
    fields_payload = {**data, "expected_documents": docs}
    return QuestionV2(**fields_payload)


def load_questions(path: str | Path) -> list[QuestionV2]:
    """Load and parse v2 test_questions json file."""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return [from_jsonable(d) for d in raw]


def save_questions(questions: list[QuestionV2], path: str | Path) -> None:
    """Serialize questions to a json file (utf-8, indented for readability)."""
    payload = [to_jsonable(q) for q in questions]
    Path(path).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
