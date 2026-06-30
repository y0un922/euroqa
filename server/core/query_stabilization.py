"""Deterministic query stabilization rules for recurring Eurocode QA failures."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from server.core.evidence_guard import EvidenceMatcher, EvidenceRequirement
from server.models.schemas import (
    EngineeringContext,
    GuideHint,
    QuestionType,
    RoutingDecision,
    RoutingTargetHint,
)

_PARTIAL_FACTOR_WORD_RE = re.compile(
    r"分项(?:安全)?系数|partial\s+(?:safety\s+)?factors?",
    re.IGNORECASE,
)
_ACTION_PARTIAL_FACTOR_CONTEXT_RE = re.compile(
    r"作用\s*(?:荷载|效应|组合)|荷载|\bloads?\b|\bactions?\b|"
    r"permanent\s+actions?|variable\s+actions?",
    re.IGNORECASE,
)
_MATERIAL_PARTIAL_FACTOR_CONTEXT_RE = re.compile(
    r"材料|钢筋|\bmaterials?\b|\breinforcement\b|\brebar\b|\bsteel\b|"
    r"混凝土\s*(?:材料)?分项(?:安全)?系数|"
    r"\bconcrete\s+(?:material\s+)?partial\s+(?:safety\s+)?factors?\b",
    re.IGNORECASE,
)
_CONCRETE_DESIGN_CONTEXT_RE = re.compile(
    r"混凝土|\bconcrete\b|\bstructural\s+concrete\b|EN\s*1992|EN1992|"
    r"Eurocode\s*2|\bEC2\b",
    re.IGNORECASE,
)
_ACTION_GAMMA_FACTOR_RE = re.compile(
    r"(?:γ|gamma)[_\s-]*(?:F|G|Q)(?![A-Za-z0-9])",
    re.IGNORECASE,
)
_MATERIAL_GAMMA_FACTOR_RE = re.compile(
    r"(?:γ|gamma)[_\s-]*(?:M|C|S)(?![A-Za-z0-9])",
    re.IGNORECASE,
)
_PARTIAL_FACTOR_STABLE_QUERIES = (
    "concrete structural design Eurocode partial factors for actions and materials",
    "EN 1990 EN 1992 EN 1992-1-1 actions materials loads load combination "
    "ultimate limit state safety factor partial factor concrete steel",
    "γF γG γQ γM γC γS γ_F γ_G γ_Q γ_M γ_C γ_S "
    "gammaF gammaG gammaQ gammaM gammaC gammaS "
    "gamma_F gamma_G gamma_Q gamma_M gamma_C gamma_S",
)
_PROCEDURE_CUE_RE = re.compile(
    r"步骤|流程|程序|如何计算|怎么计算|如何设计|怎么设计|"
    r"\bsteps?\b|\bprocedure\b|\bprocess\b|\bhow\s+to\b",
    re.IGNORECASE,
)
_FLEXURAL_RESISTANCE_CONTEXT_RE = re.compile(
    r"受弯|正截面|截面承载力|抗弯承载力|弯矩承载力|"
    r"\bflexur(?:al|e)\b|\bbending\b|\bmoment\s+resistance\b|"
    r"\bM[_\s{]*Rd\b",
    re.IGNORECASE,
)
_ONE_WAY_SLAB_CONTEXT_RE = re.compile(
    r"单向板|one[\s-]*way\s+(?:spanning\s+)?slabs?|one[\s-]*way\s+slab",
    re.IGNORECASE,
)
_FLEXURAL_RESISTANCE_STABLE_QUERIES = (
    "EN 1992-1-1 design sections for bending and axial force flexural resistance calculation steps",
    "EN 1992 6.1 3.1.7 Table 3.1 basic assumptions stress strain diagram rectangular stress block bending resistance",
    "M_Rd neutral axis x d rotation capacity redistribution concrete strain reinforcement f_yd A_s",
)
_ONE_WAY_SLAB_STABLE_QUERIES = (
    "EN 1992-1-1 one-way solid slab design steps structural idealisation analysis flexural reinforcement shear deflection",
    "EN 1992 5.3.1 one-way spanning slab 5.6.3 rotation capacity 9.3 solid slabs 7.4 deflection 6.2 shear",
    "one way slab bending moment shear coefficients Table 3.3 main reinforcement transverse reinforcement spacing",
)


@dataclass
class ExpansionResult:
    """Query expansion result returned by the LLM plus deterministic metadata."""

    queries: list[str]
    question_type: QuestionType | None = None
    engineering_context: EngineeringContext | None = None
    guide_hint: GuideHint | None = None
    routing: RoutingDecision | None = None
    rewritten_question: str | None = None
    required_evidence: list[EvidenceRequirement] = field(default_factory=list)


def stabilize_expansion(question: str, expansion: ExpansionResult) -> ExpansionResult:
    """Apply narrow deterministic stabilizers after LLM expansion."""
    for stabilizer in (
        _stabilize_partial_factor_expansion,
        _stabilize_flexural_resistance_expansion,
        _stabilize_one_way_slab_expansion,
    ):
        stabilized = stabilizer(question, expansion)
        if stabilized is not expansion:
            return stabilized
    return expansion


def _is_concrete_action_material_partial_factor_query(question: str) -> bool:
    has_action_symbol = bool(_ACTION_GAMMA_FACTOR_RE.search(question))
    has_material_symbol = bool(_MATERIAL_GAMMA_FACTOR_RE.search(question))
    has_partial_factor_cue = (
        bool(_PARTIAL_FACTOR_WORD_RE.search(question))
        or has_action_symbol
        or has_material_symbol
    )
    if not has_partial_factor_cue:
        return False

    has_concrete_design_context = bool(_CONCRETE_DESIGN_CONTEXT_RE.search(question))
    has_action_context = (
        bool(_ACTION_PARTIAL_FACTOR_CONTEXT_RE.search(question)) or has_action_symbol
    )
    has_material_context = (
        bool(_MATERIAL_PARTIAL_FACTOR_CONTEXT_RE.search(question))
        or has_material_symbol
    )

    return has_concrete_design_context and has_action_context and has_material_context


def _stabilize_partial_factor_expansion(
    question: str,
    expansion: ExpansionResult,
) -> ExpansionResult:
    if not _is_concrete_action_material_partial_factor_query(question):
        return expansion

    return ExpansionResult(
        queries=list(_PARTIAL_FACTOR_STABLE_QUERIES),
        question_type=QuestionType.PARAMETER,
        engineering_context=expansion.engineering_context,
        guide_hint=GuideHint(need_example=False),
        routing=RoutingDecision(
            intent_label="limit",
            target_hint=RoutingTargetHint(
                document="EN 1990 and EN 1992-1-1",
                clause=None,
                object="partial factors for actions and materials",
            ),
            reason_short="asks for Eurocode partial factor values",
        ),
        rewritten_question=expansion.rewritten_question,
        required_evidence=_partial_factor_required_evidence(),
    )


def _partial_factor_required_evidence() -> list[EvidenceRequirement]:
    return [
        EvidenceRequirement(
            id="material_concrete_partial_factor",
            label="EN 1992 混凝土材料分项系数（γC=1.5）",
            any_of=[
                EvidenceMatcher(
                    source_contains=["EN1992", "EN 1992"],
                    object_label_contains=["Table 2.1N", "Table 2.1"],
                    content_contains=["concrete", "1.5"],
                ),
                EvidenceMatcher(
                    source_contains=["EN1992", "EN 1992"],
                    content_contains=["Table 2.1N", "concrete", "1.5"],
                ),
                EvidenceMatcher(
                    source_contains=["EN1992", "EN 1992"],
                    content_contains=["Yc", "concrete", "1.5"],
                ),
            ],
        ),
        EvidenceRequirement(
            id="material_steel_partial_factor",
            label="EN 1992 钢筋材料分项系数（γS=1.15）",
            any_of=[
                EvidenceMatcher(
                    source_contains=["EN1992", "EN 1992"],
                    object_label_contains=["Table 2.1N", "Table 2.1"],
                    content_contains=["steel", "1.15"],
                ),
                EvidenceMatcher(
                    source_contains=["EN1992", "EN 1992"],
                    content_contains=["Table 2.1N", "steel", "1.15"],
                ),
                EvidenceMatcher(
                    source_contains=["EN1992", "EN 1992"],
                    content_contains=["Ys", "steel", "1.15"],
                ),
            ],
        ),
        EvidenceRequirement(
            id="permanent_action_partial_factor",
            label="EN 1990 永久作用分项系数（γG=1.35）",
            any_of=[
                EvidenceMatcher(
                    source_contains=["EN1990", "EN 1990"],
                    object_label_contains=[
                        "Table A1.2",
                        "Table A1.2(B)",
                        "Table A1.2(C)",
                    ],
                ),
                EvidenceMatcher(
                    source_contains=["EN1990", "EN 1990"],
                    object_label_contains=[
                        "Table A1.2",
                        "Table A1.2(B)",
                        "Table A1.2(C)",
                    ],
                    content_contains=["γG", "1.35"],
                ),
                EvidenceMatcher(
                    source_contains=["EN1990", "EN 1990"],
                    object_label_contains=[
                        "Table A1.2",
                        "Table A1.2(B)",
                        "Table A1.2(C)",
                    ],
                    content_contains=["gamma_G", "1.35"],
                ),
                EvidenceMatcher(
                    source_contains=["EN1990", "EN 1990"],
                    object_label_contains=[
                        "Table A1.2",
                        "Table A1.2(B)",
                        "Table A1.2(C)",
                    ],
                    content_contains=["permanent", "1.35"],
                ),
                EvidenceMatcher(
                    source_contains=["EN1990", "EN 1990"],
                    content_contains=["Table A1.2", "1.35"],
                ),
                EvidenceMatcher(
                    source_contains=["EN1990", "EN 1990"],
                    content_contains=["Table 7.2", "1.35"],
                ),
            ],
        ),
        EvidenceRequirement(
            id="variable_action_partial_factor",
            label="EN 1990 可变作用分项系数（γQ=1.5）",
            any_of=[
                EvidenceMatcher(
                    source_contains=["EN1990", "EN 1990"],
                    object_label_contains=[
                        "Table A1.2",
                        "Table A1.2(B)",
                        "Table A1.2(C)",
                    ],
                ),
                EvidenceMatcher(
                    source_contains=["EN1990", "EN 1990"],
                    object_label_contains=[
                        "Table A1.2",
                        "Table A1.2(B)",
                        "Table A1.2(C)",
                    ],
                    content_contains=["γQ", "1.5"],
                ),
                EvidenceMatcher(
                    source_contains=["EN1990", "EN 1990"],
                    object_label_contains=[
                        "Table A1.2",
                        "Table A1.2(B)",
                        "Table A1.2(C)",
                    ],
                    content_contains=["gamma_Q", "1.5"],
                ),
                EvidenceMatcher(
                    source_contains=["EN1990", "EN 1990"],
                    object_label_contains=[
                        "Table A1.2",
                        "Table A1.2(B)",
                        "Table A1.2(C)",
                    ],
                    content_contains=["variable", "1.5"],
                ),
                EvidenceMatcher(
                    source_contains=["EN1990", "EN 1990"],
                    content_contains=["Table A1.2", "1.5"],
                ),
                EvidenceMatcher(
                    source_contains=["EN1990", "EN 1990"],
                    content_contains=["Table 7.2", "1.5"],
                ),
            ],
        ),
    ]


def _is_flexural_resistance_procedure_query(question: str) -> bool:
    return bool(_PROCEDURE_CUE_RE.search(question)) and bool(
        _FLEXURAL_RESISTANCE_CONTEXT_RE.search(question)
    )


def _stabilize_flexural_resistance_expansion(
    question: str,
    expansion: ExpansionResult,
) -> ExpansionResult:
    if not _is_flexural_resistance_procedure_query(question):
        return expansion

    return ExpansionResult(
        queries=list(_FLEXURAL_RESISTANCE_STABLE_QUERIES),
        question_type=QuestionType.CALCULATION,
        engineering_context=expansion.engineering_context,
        guide_hint=GuideHint(
            need_example=False,
            example_query=None,
            example_kind=None,
        ),
        routing=RoutingDecision(
            intent_label="calculation",
            target_hint=RoutingTargetHint(
                document="EN 1992-1-1",
                clause="6.1",
                object="design sections for bending and axial force",
            ),
            reason_short="asks for flexural resistance calculation steps",
        ),
        rewritten_question=expansion.rewritten_question,
        required_evidence=_flexural_resistance_required_evidence(),
    )


def _flexural_resistance_required_evidence() -> list[EvidenceRequirement]:
    return [
        EvidenceRequirement(
            id="flexural_basic_assumptions",
            label="EN 1992 截面受弯承载力基本假定（6.1 / 平截面、忽略混凝土抗拉）",
            any_of=[
                EvidenceMatcher(
                    source_contains=["EN1992", "EN 1992"],
                    clause_ids_overlap=["6.1"],
                ),
                EvidenceMatcher(
                    source_contains=["EN1992", "EN 1992"],
                    content_contains=["plane sections", "remain plane"],
                ),
                EvidenceMatcher(
                    source_contains=["EN1992", "EN 1992"],
                    content_contains=["tensile strength", "concrete", "ignored"],
                ),
            ],
        ),
        EvidenceRequirement(
            id="concrete_stress_strain_design_model",
            label="EN 1992 混凝土设计应力-应变模型与极限应变（3.1.7 / Table 3.1）",
            any_of=[
                EvidenceMatcher(
                    source_contains=["EN1992", "EN 1992"],
                    clause_ids_overlap=["3.1.7"],
                ),
                EvidenceMatcher(
                    source_contains=["EN1992", "EN 1992"],
                    object_label_contains=["Table 3.1"],
                ),
                EvidenceMatcher(
                    source_contains=["EN1992", "EN 1992"],
                    content_contains=["rectangular", "stress block"],
                ),
                EvidenceMatcher(
                    source_contains=["EN1992", "EN 1992"],
                    content_contains=["εcu3", "εc3"],
                ),
            ],
        ),
        EvidenceRequirement(
            id="flexural_equilibrium_resistance",
            label="受弯截面内力平衡与抗弯承载力表达（MRd、As、fyd、中性轴）",
            any_of=[
                EvidenceMatcher(content_contains=["M_Rd", "A_s"]),
                EvidenceMatcher(content_contains=["MRd", "As"]),
                EvidenceMatcher(content_contains=["neutral axis", "moment"]),
                EvidenceMatcher(content_contains=["force equilibrium", "moment"]),
            ],
        ),
        EvidenceRequirement(
            id="neutral_axis_rotation_limit",
            label="中性轴深度/转动能力限制（5.6.2 或 5.6.3，xu/d 限值）",
            any_of=[
                EvidenceMatcher(
                    source_contains=["EN1992", "EN 1992"],
                    clause_ids_overlap=["5.6.2", "5.6.3", "5.5"],
                ),
                EvidenceMatcher(content_contains=["x_u", "d", "0.45"]),
                EvidenceMatcher(content_contains=["rotation capacity", "0.45"]),
                EvidenceMatcher(content_contains=["neutral axis", "redistribution"]),
            ],
        ),
    ]


def _is_one_way_slab_design_procedure_query(question: str) -> bool:
    return bool(_PROCEDURE_CUE_RE.search(question)) and bool(
        _ONE_WAY_SLAB_CONTEXT_RE.search(question)
    )


def _stabilize_one_way_slab_expansion(
    question: str,
    expansion: ExpansionResult,
) -> ExpansionResult:
    if not _is_one_way_slab_design_procedure_query(question):
        return expansion

    return ExpansionResult(
        queries=list(_ONE_WAY_SLAB_STABLE_QUERIES),
        question_type=QuestionType.CALCULATION,
        engineering_context=expansion.engineering_context,
        guide_hint=GuideHint(
            need_example=True,
            example_query="one way spanning slabs design procedure moment shear coefficients",
            example_kind="procedure",
        ),
        routing=RoutingDecision(
            intent_label="calculation",
            target_hint=RoutingTargetHint(
                document="EN 1992-1-1",
                clause="9.3",
                object="one-way solid slab design procedure",
            ),
            reason_short="asks for one-way slab design steps",
        ),
        rewritten_question=expansion.rewritten_question,
        required_evidence=_one_way_slab_required_evidence(),
    )


def _one_way_slab_required_evidence() -> list[EvidenceRequirement]:
    return [
        EvidenceRequirement(
            id="one_way_slab_definition",
            label="单向板判定与结构理想化（5.3.1，均布荷载/两自由边/长短跨比>2）",
            any_of=[
                EvidenceMatcher(
                    source_contains=["EN1992", "EN 1992"],
                    clause_ids_overlap=["5.3.1"],
                ),
                EvidenceMatcher(content_contains=["one-way spanning slab"]),
                EvidenceMatcher(content_contains=["longer", "shorter", "2"]),
                EvidenceMatcher(content_contains=["unsupported edges", "parallel"]),
            ],
        ),
        EvidenceRequirement(
            id="one_way_slab_analysis_method",
            label="单向板内力分析方法（5.6.3 或指南弯矩/剪力系数表）",
            any_of=[
                EvidenceMatcher(
                    source_contains=["EN1992", "EN 1992"],
                    clause_ids_overlap=["5.6.3"],
                ),
                EvidenceMatcher(content_contains=["continuous one way spanning slabs"]),
                EvidenceMatcher(content_contains=["rotation capacity"]),
                EvidenceMatcher(object_label_contains=["Table 3.3"]),
            ],
        ),
        EvidenceRequirement(
            id="solid_slab_flexural_reinforcement",
            label="实心板受弯配筋构造（9.3 / 9.3.1，主筋、横向分布筋、间距）",
            any_of=[
                EvidenceMatcher(
                    source_contains=["EN1992", "EN 1992"],
                    clause_ids_overlap=["9.3", "9.3.1", "9.3.1.1"],
                ),
                EvidenceMatcher(content_contains=["transverse reinforcement", "20%"]),
                EvidenceMatcher(content_contains=["3h", "400"]),
                EvidenceMatcher(content_contains=["3.5h", "450"]),
            ],
        ),
        EvidenceRequirement(
            id="slab_serviceability_deflection",
            label="单向板正常使用控制（7.4 挠度/跨高比）",
            any_of=[
                EvidenceMatcher(
                    source_contains=["EN1992", "EN 1992"],
                    clause_ids_overlap=["7.4", "7.4.2"],
                ),
                EvidenceMatcher(object_label_contains=["Table 7.4N"]),
                EvidenceMatcher(content_contains=["span", "effective depth"]),
            ],
        ),
        EvidenceRequirement(
            id="slab_shear_check",
            label="单向板剪切验算与抗剪筋豁免条件（6.2 / VEd 与 VRd,c）",
            any_of=[
                EvidenceMatcher(
                    source_contains=["EN1992", "EN 1992"],
                    clause_ids_overlap=["6.2", "6.2.1", "6.2.2"],
                ),
                EvidenceMatcher(content_contains=["V_Ed", "V_Rd,c"]),
                EvidenceMatcher(content_contains=["slabs", "shear reinforcement"]),
            ],
        ),
    ]
