"""CandidateConfig validation + isolation snapshot unit tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from eval_methodology.mvp.candidate import (  # noqa: E402
    CandidateConfig,
    baseline_candidate,
    candidate_to_env,
    describe_candidate,
    treatment_candidate,
    validate_against_server_config,
)
from eval_methodology.mvp.isolation import (  # noqa: E402
    IsolationSnapshot,
    compare_snapshots,
)
from eval_methodology.mvp.metrics.diagnostics import crec_score  # noqa: E402
from eval_methodology.mvp.metrics.bootstrap import paired_bootstrap_ci  # noqa: E402


def test_candidate_forbids_unknown_fields():
    with pytest.raises(ValidationError):
        CandidateConfig(vector_top_k=50)  # type: ignore[call-arg]


def test_candidate_to_env_and_server_config():
    c = CandidateConfig(retrieval_auto_cross_ref_closure=True)
    env = candidate_to_env(c)
    assert env["RETRIEVAL_AUTO_CROSS_REF_CLOSURE"] == "true"
    cfg = validate_against_server_config(c)
    assert cfg.retrieval_auto_cross_ref_closure is True


def test_baseline_pins_thinking_off_and_treatment_flips_single_knob():
    base_env = candidate_to_env(baseline_candidate())
    assert base_env["LLM_ENABLE_THINKING"] == "false"
    assert base_env["RETRIEVAL_AUTO_CROSS_REF_CLOSURE"] == "false"

    treatment = treatment_candidate({"llm_enable_thinking": True})
    env = candidate_to_env(treatment)
    assert env["LLM_ENABLE_THINKING"] == "true"
    assert env["RETRIEVAL_AUTO_CROSS_REF_CLOSURE"] == "false"
    cfg = validate_against_server_config(treatment)
    assert cfg.llm_enable_thinking is True
    assert describe_candidate(treatment)["name"] == "llm_enable_thinking=True"
    assert describe_candidate(baseline_candidate())["name"] == "baseline"


def test_isolation_allows_eval_methodology_new_dirty():
    before = IsolationSnapshot(
        git_status_lines=(" M server/foo.py",),
        dirty_paths=frozenset({"server/foo.py"}),
        env_sha256="abc",
        env_exists=True,
    )
    after = IsolationSnapshot(
        git_status_lines=(
            " M server/foo.py",
            "?? eval_methodology/mvp/data/x.json",
        ),
        dirty_paths=frozenset({"server/foo.py", "eval_methodology/mvp/data/x.json"}),
        env_sha256="abc",
        env_exists=True,
    )
    report = compare_snapshots(before, after)
    assert report.ok
    assert "eval_methodology/mvp/data/x.json" in report.new_dirty_paths


def test_isolation_rejects_server_new_dirty_and_env_change():
    before = IsolationSnapshot(
        git_status_lines=(),
        dirty_paths=frozenset(),
        env_sha256="abc",
        env_exists=True,
    )
    after = IsolationSnapshot(
        git_status_lines=(" M server/config.py",),
        dirty_paths=frozenset({"server/config.py"}),
        env_sha256="def",
        env_exists=True,
    )
    report = compare_snapshots(before, after)
    assert not report.ok
    assert "server/config.py" in report.disallowed_new_dirty
    assert report.env_changed


def test_crec_corpus_gap_ineligible():
    score, eligible = crec_score([], [{"content": "anything"}])
    assert score is None
    assert eligible is False
    score2, eligible2 = crec_score(
        [
            {
                "evidence_id": "e1",
                "quote": "a sufficiently long required evidence quotation",
            },
            {
                "evidence_id": "e2",
                "quote": "a sufficiently long missing evidence quotation",
            },
        ],
        [{"content": "prefix a sufficiently long required evidence quotation suffix"}],
    )
    assert eligible2 is True
    assert abs(score2 - 0.5) < 1e-9


def test_bootstrap_fixed_seed_reproducible():
    a = [0.1 * i for i in range(16)]
    b = [x + 0.05 for x in a]
    c1 = paired_bootstrap_ci(a, b)
    c2 = paired_bootstrap_ci(a, b)
    assert c1.mean == c2.mean
    assert c1.low == c2.low
    assert c1.high == c2.high


def test_claude_cli_includes_no_session_persistence():
    import inspect
    from eval_methodology.mvp.metrics.judges import cli_backend as cb

    src = inspect.getsource(cb.run_claude_json)
    assert "--no-session-persistence" in src
    assert "--bare" not in src
