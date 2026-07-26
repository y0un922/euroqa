"""Metric schemas for the MVP v2 straight-line evaluation flow."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class PerQuestionMetrics(BaseModel):
    """Per-question scores used in bootstrap pairing."""

    question_id: str
    faith: float | None = None
    citp: float | None = None
    crec: float | None = None
    unresolved_ref_rate: float | None = None
    judge_failed: bool = False
    crec_eligible: bool = False
    n_claims: int = 0
    n_citations: int = 0
    context_chunk_ids: list[str] = Field(default_factory=list)
    # Gold evidence locator IDs and those whose quotes are absent from C.
    e_plus: list[str] = Field(default_factory=list)
    retrieval_gap_ids: list[str] = Field(default_factory=list)
    gold_claim_status: str = ""  # supported | corpus_gap | mixed | none
    gold_confirmed: bool = False  # human_review.confirmed on the gold item
    elapsed_ms: int | None = None
    status: str = "ok"
    notes: str = ""


class AggregateMetrics(BaseModel):
    faith_mean: float | None = None
    citp_mean: float | None = None
    crec_mean: float | None = None
    unresolved_ref_rate_mean: float | None = None
    effective_n_faith: int = 0
    effective_n_citp: int = 0
    crec_eligible_n: int = 0
    crec_confirmed_n: int = 0
    judge_fail_rate: float = 0.0
    degraded_to_trend: bool = False
    degradation_reason: str = ""


DecisionState = Literal["accept", "reject", "inconclusive"]
