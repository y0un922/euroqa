from __future__ import annotations

import pytest

from server.config import ServerConfig
from server.core.evidence_planner import SourceInventoryItem, plan_evidence
from server.core.query_understanding import QueryAnalysis
from server.models.schemas import QuestionType


@pytest.mark.asyncio
async def test_heuristic_planner_splits_compound_question_when_llm_fails(monkeypatch):
    async def _raise(*_args, **_kwargs):
        raise RuntimeError("planner unavailable")

    monkeypatch.setattr("server.core.evidence_planner._call_planner_llm", _raise)
    analysis = QueryAnalysis(
        original_question="请总结 ULS 和 SLS 的裂缝控制限值。",
        expanded_queries=["ULS SLS crack control limits"],
        filters={},
        question_type=QuestionType.PARAMETER,
    )

    plan = await plan_evidence(
        "请总结 ULS 和 SLS 的裂缝控制限值。",
        analysis,
        [SourceInventoryItem(source="EN 1992-1-1", title="Eurocode 2")],
        ServerConfig(agentic_search_enabled=True, agentic_search_max_slots=4),
    )

    assert plan.strategy == "slot"
    assert len(plan.slots) >= 2
    assert all(slot.normalized_queries() for slot in plan.slots)


def test_agentic_planner_model_config_falls_back_to_agent_model():
    cfg = ServerConfig(
        llm_model="main-model",
        llm_base_url="https://main.example/v1",
        agent_llm_model="agent-model",
        agent_llm_base_url="https://agent.example/v1",
    )

    assert cfg.resolved_agentic_search_planner_model == "agent-model"
    assert cfg.resolved_agentic_search_planner_base_url == "https://agent.example/v1"


def test_agentic_planner_model_can_be_configured_independently():
    cfg = ServerConfig(
        llm_model="main-model",
        agent_llm_model="agent-model",
        agentic_search_planner_model="planner-model",
        agentic_search_planner_base_url="https://planner.example/v1",
    )

    assert cfg.resolved_agentic_search_planner_model == "planner-model"
    assert (
        cfg.resolved_agentic_search_planner_base_url == "https://planner.example/v1"
    )
