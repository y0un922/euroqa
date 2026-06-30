"""Deterministic checks for generated answer quality."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from server.core.evidence_guard import EvidenceRequirement


@dataclass(frozen=True)
class AnswerGuardFinding:
    """One deterministic answer quality finding."""

    code: str
    severity: str
    message: str


@dataclass(frozen=True)
class AnswerGuardResult:
    """Answer guard diagnostics attached to generation outputs."""

    passed: bool
    findings: list[AnswerGuardFinding] = field(default_factory=list)

    @property
    def severity(self) -> str:
        order = {"ok": 0, "minor": 1, "major": 2, "blocker": 3}
        if not self.findings:
            return "ok"
        return max(self.findings, key=lambda item: order.get(item.severity, 0)).severity

    def to_trace(self) -> dict[str, object]:
        return {
            "passed": self.passed,
            "severity": self.severity,
            "findings": [
                {
                    "code": finding.code,
                    "severity": finding.severity,
                    "message": finding.message,
                }
                for finding in self.findings
            ],
        }


def evaluate_answer_guard(
    answer: str,
    *,
    question: str,
    required_evidence: list[EvidenceRequirement] | None = None,
) -> AnswerGuardResult:
    """Check deterministic answer defects without interpreting source semantics."""
    findings: list[AnswerGuardFinding] = []
    normalized_answer = _normalize_text(answer)
    normalized_question = _normalize_text(question)

    if _has_latex_numeric_duplication(answer):
        findings.append(
            AnswerGuardFinding(
                code="latex_numeric_duplication",
                severity="major",
                message="答案疑似包含 LaTeX 数值重复残片，例如公式后紧跟重复数字。",
            )
        )

    if _is_partial_factor_answer(normalized_question, required_evidence):
        findings.extend(_partial_factor_findings(normalized_answer))

    return AnswerGuardResult(passed=not findings, findings=findings)


def _partial_factor_findings(answer: str) -> list[AnswerGuardFinding]:
    findings: list[AnswerGuardFinding] = []
    if _claims_all_accidental_material_factors_are_one(answer) and (
        _mentions_non_fire_accidental_concrete_factor(answer)
        or _mentions_non_fire_accidental(answer)
    ):
        findings.append(
            AnswerGuardFinding(
                code="partial_factor_accidental_summary_conflict",
                severity="major",
                message=(
                    "答案把偶然/火灾材料分项系数概括为均取 1.0，"
                    "但正文又提到非火灾偶然混凝土系数 1.2，存在前后矛盾。"
                ),
            )
        )
    return findings


def _is_partial_factor_answer(
    normalized_question: str,
    required_evidence: list[EvidenceRequirement] | None,
) -> bool:
    if required_evidence and any(
        "partial_factor" in requirement.id for requirement in required_evidence
    ):
        return True
    return (
        "partial factor" in normalized_question
        or "分项系数" in normalized_question
        or "γ" in normalized_question
        or "gamma" in normalized_question
    )


def _has_latex_numeric_duplication(answer: str) -> bool:
    return bool(re.search(r"\$[^$\n]*\d+(?:[.,]\d+)?\$\s*\d+(?:[.,]\d+)?\$", answer))


def _claims_all_accidental_material_factors_are_one(answer: str) -> bool:
    compact = answer.replace(" ", "")
    accidental_fire = (
        "偶然组合（含火灾）" in compact
        or "偶然组合(含火灾)" in compact
        or "偶然/火灾" in compact
        or "偶然和火灾" in compact
        or "偶然及火灾" in compact
    )
    all_one = (
        "均取1.0" in compact
        or "均为1.0" in compact
        or "统一取1.0" in compact
        or "统一为1.0" in compact
    )
    return accidental_fire and all_one


def _mentions_non_fire_accidental_concrete_factor(answer: str) -> bool:
    compact = answer.replace(" ", "")
    return bool(
        re.search(
            r"非火灾[^。\n；;]{0,40}(?:γc|gamma_c|混凝土)[^。\n；;]{0,40}1[.,]2",
            compact,
            re.I,
        )
    )


def _mentions_non_fire_accidental(answer: str) -> bool:
    compact = answer.replace(" ", "")
    return "非火灾偶然" in compact or "非火灾的偶然" in compact


def _normalize_text(text: str) -> str:
    return text.strip().lower()
