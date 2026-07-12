"""Metric schemas for MVP + TODOs for deferred metrics.

Implemented: Faith, CitP, CRec, unresolved_ref_rate.
Deferred (schema/todo only): Match, Comp, Corr, CPrec, Noise, ECov, RDeg.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ClaimUnit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    unit_id: str
    text: str
    citation_ids: list[str] = Field(default_factory=list)


class CitationUnit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    citation_id: str
    ref_label: str = ""
    linked_claim_ids: list[str] = Field(default_factory=list)
    source_hint: str = ""


class ExtractedUnits(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claims: list[ClaimUnit]
    citations: list[CitationUnit] = Field(default_factory=list)


class ClaimVerdict(BaseModel):
    model_config = ConfigDict(extra="forbid")

    unit_id: str
    supported: bool
    note: str = ""


class CitationVerdict(BaseModel):
    model_config = ConfigDict(extra="forbid")

    citation_id: str
    valid: bool
    note: str = ""


class JudgeRawOutput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    claim_verdicts: list[ClaimVerdict]
    citation_verdicts: list[CitationVerdict] = Field(default_factory=list)


class PerQuestionMetrics(BaseModel):
    """Per-question scores used in bootstrap pairing."""

    question_id: str
    faith: float | None = None
    citp: float | None = None
    crec: float | None = None
    unresolved_ref_rate: float | None = None
    judge_dropped: bool = False
    crec_eligible: bool = False
    n_claims: int = 0
    n_citations: int = 0
    context_chunk_ids: list[str] = Field(default_factory=list)
    # Gold / retrieval state machine (audit C1).
    e_plus: list[str] = Field(default_factory=list)
    retrieval_gap_ids: list[str] = Field(default_factory=list)
    gold_claim_status: str = ""  # supported | corpus_gap | mixed | none
    notes: str = ""


class AggregateMetrics(BaseModel):
    faith_mean: float | None = None
    citp_mean: float | None = None
    crec_mean: float | None = None
    unresolved_ref_rate_mean: float | None = None
    effective_n_faith: int = 0
    effective_n_citp: int = 0
    crec_eligible_n: int = 0
    judge_drop_rate: float = 0.0
    degraded_to_trend: bool = False
    degradation_reason: str = ""


# --- Deferred metrics (not implemented in MVP) --------------------------------

DEFERRED_METRICS: dict[str, dict[str, Any]] = {
    "Match": {
        "status": "todo",
        "reason": "No fresh human answer snapshot; y only for stratification/holdout",
    },
    "Comp": {
        "status": "todo",
        "reason": "Gold-dependent + family conflict; needs third family or human gold",
    },
    "Corr": {
        "status": "todo",
        "reason": "Gold-dependent + family conflict; deferred with Comp",
    },
    "CPrec": {"status": "todo", "reason": "Diagnostic; needs E⁺ density labeling"},
    "Noise": {"status": "todo", "reason": "Diagnostic; needs non-relevant labeling"},
    "ECov": {"status": "todo", "reason": "Needs C_ev evidence subset annotation"},
    "RDeg": {
        "status": "todo",
        "reason": "Needs main-project degradation flag (forbidden in MVP isolation)",
    },
}


DecisionState = Literal["accept", "reject", "inconclusive"]
