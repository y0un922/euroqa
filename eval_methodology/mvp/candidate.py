"""Whitelist candidate config → full ServerConfig validation → env injection.

Isolation rule: never write .env; only inject env into the sidecar subprocess.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

from server.config import ServerConfig


class CandidateConfig(BaseModel):
    """Whitelist of knobs allowed in the MVP A/B candidate.

    Only fields proven to flow into the agent retrieval path may be listed.
    `retrieval_auto_cross_ref_closure` is verified at retrieval.py:1887 and is
    not overwritten by `_config_for_top_k` model_copy.
    """

    model_config = ConfigDict(extra="forbid")

    retrieval_auto_cross_ref_closure: bool = False
    # Optional timeouts kept for future single-var actions; unused in A plan.
    agent_timeout_seconds: int | None = None
    request_deadline_seconds: int | None = None


def validate_against_server_config(candidate: CandidateConfig) -> ServerConfig:
    """Construct a full ServerConfig with candidate overrides applied.

    Loads ambient .env (read-only) then overlays whitelist fields so pydantic
    type-checks the merged config. Does not write any files.
    """
    base = ServerConfig()
    data = base.model_dump()
    for key, value in candidate.model_dump(exclude_none=True).items():
        data[key] = value
    return ServerConfig(**data)


def candidate_to_env(candidate: CandidateConfig) -> dict[str, str]:
    """Translate whitelist fields to uppercase env vars for the sidecar.

    pydantic-settings with env_prefix='' maps field names to UPPER_SNAKE.
    """
    env: dict[str, str] = {}
    for key, value in candidate.model_dump(exclude_none=True).items():
        env_key = key.upper()
        if isinstance(value, bool):
            env[env_key] = "true" if value else "false"
        else:
            env[env_key] = str(value)
    return env


def baseline_candidate() -> CandidateConfig:
    """MVP baseline: auto cross-ref closure OFF (default production posture)."""
    return CandidateConfig(retrieval_auto_cross_ref_closure=False)


def treatment_candidate() -> CandidateConfig:
    """MVP treatment: auto cross-ref closure ON."""
    return CandidateConfig(retrieval_auto_cross_ref_closure=True)


def describe_candidate(candidate: CandidateConfig) -> dict[str, Any]:
    return {
        "name": (
            "auto_cross_ref_on"
            if candidate.retrieval_auto_cross_ref_closure
            else "auto_cross_ref_off"
        ),
        "fields": candidate.model_dump(exclude_none=True),
    }
