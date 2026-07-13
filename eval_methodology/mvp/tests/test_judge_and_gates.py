"""Judge drop semantics, CLI parse, retrieval_gap wiring."""

from __future__ import annotations

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from eval_methodology.mvp.metrics.e2e import aggregate, per_question_from_parts  # noqa: E402
from eval_methodology.mvp.metrics.judges.cli_backend import (  # noqa: E402
    _extract_json_object,
)
from eval_methodology.mvp.metrics.judges.cache import (  # noqa: E402
    make_cache_key,
)


def test_regex_fallback_is_not_ok():
    # Trailing garbage forces non-pure JSON; regex might salvage but ok=False.
    text = 'here is noise {"claim_verdicts": [], "citation_verdicts": []} trailing'
    parsed = _extract_json_object(text, allow_regex_fallback=True)
    assert parsed.source == "regex_fallback"
    assert parsed.ok is False


def test_pure_json_ok():
    text = '{"claim_verdicts": [], "citation_verdicts": []}'
    parsed = _extract_json_object(text, allow_regex_fallback=False)
    assert parsed.ok is True
    assert parsed.source == "json"


def test_citation_disagreement_full_drop_nulls_faith_in_aggregate():
    """Audit D2: citation-only disagreement must not keep Faith in means."""
    # Simulate dual_judge full drop after citation disagreement.
    pq = per_question_from_parts(
        question_id="Q01",
        faith=0.9,  # would-be faith
        citp=None,
        judge_dropped=True,
        evidence_locators=[{"evidence_id": "e1", "quote": "supported text"}],
        context_chunk_ids=["c1"],
        context_chunks=[{"chunk_id": "c1", "content": "supported text"}],
        unresolved_refs=[],
        resolved_refs=[],
    )
    assert pq.faith is None
    assert pq.citp is None
    assert pq.judge_dropped is True
    agg = aggregate(
        [pq]
        + [
            per_question_from_parts(
                question_id=f"Q{i:02d}",
                faith=1.0,
                citp=1.0,
                judge_dropped=False,
                evidence_locators=[{"evidence_id": "e1", "quote": "supported text"}],
                context_chunk_ids=["c1"],
                context_chunks=[{"chunk_id": "c1", "content": "supported text"}],
                unresolved_refs=[],
                resolved_refs=[],
            )
            for i in range(2, 17)
        ]
    )
    # Dropped Q01 excluded from faith mean n.
    assert agg.effective_n_faith == 15
    assert abs((agg.faith_mean or 0) - 1.0) < 1e-9
    assert agg.judge_drop_rate > 0


def test_retrieval_gap_ids_populated():
    pq = per_question_from_parts(
        question_id="Q01",
        faith=1.0,
        citp=1.0,
        judge_dropped=False,
        evidence_locators=[
            {"evidence_id": "e1", "quote": "first exact evidence"},
            {"evidence_id": "e2", "quote": "second exact evidence"},
            {"evidence_id": "e3", "quote": "third exact evidence"},
        ],
        context_chunk_ids=["chunk-any-id"],
        context_chunks=[
            {
                "chunk_id": "chunk-any-id",
                "content": "prefix first exact evidence suffix",
            }
        ],
        unresolved_refs=["Table 3.1"],
        resolved_refs=[],
    )
    assert pq.retrieval_gap_ids == ["e2", "e3"]
    assert pq.crec_eligible is True
    assert abs((pq.crec or 0) - 1 / 3) < 1e-9


def test_cache_key_changes_with_model_and_order():
    k1 = make_cache_key(
        family="codex",
        model_id="gpt-5.3-codex",
        question="q",
        answer="a",
        context_chunks=[
            {"chunk_id": "a", "content": "x"},
            {"chunk_id": "b", "content": "y"},
        ],
        citations=[],
    )
    k2 = make_cache_key(
        family="codex",
        model_id="gpt-5.3-codex",
        question="q",
        answer="a",
        context_chunks=[
            {"chunk_id": "b", "content": "y"},
            {"chunk_id": "a", "content": "x"},
        ],
        citations=[],
    )
    k3 = make_cache_key(
        family="codex",
        model_id="other-model",
        question="q",
        answer="a",
        context_chunks=[
            {"chunk_id": "a", "content": "x"},
            {"chunk_id": "b", "content": "y"},
        ],
        citations=[],
    )
    assert k1 != k2  # ordered context content hash differs by order of list
    assert k1 != k3  # model id in key


def test_model_pin_closes_unresolved_cache_gap(tmp_path, monkeypatch):
    """After pin, resolve returns real id so second lookup hits same key (D4)."""
    from eval_methodology.mvp.metrics.judges import cli_backend as cb
    from eval_methodology.mvp.metrics.judges.cache import JudgeCache

    monkeypatch.setattr(cb, "_PINNED_MODELS", {})
    monkeypatch.setattr(cb, "_pins_path", lambda: tmp_path / "resolved_models.json")

    assert cb.resolve_codex_model_id() == "codex-unresolved"
    cb.pin_resolved_model("codex", "gpt-5.3-codex")
    assert cb.resolve_codex_model_id() == "gpt-5.3-codex"

    cache = JudgeCache(root=tmp_path / "jcache")
    chunks = [{"chunk_id": "a", "content": "x"}]
    key = make_cache_key(
        family="codex",
        model_id=cb.resolve_codex_model_id(),
        question="q",
        answer="a",
        context_chunks=chunks,
        citations=[],
    )
    cache.set(
        key,
        {
            "output": {"claim_verdicts": [], "citation_verdicts": []},
            "model_id": "gpt-5.3-codex",
        },
    )
    # New process simulation: clear memory pin, reload from disk
    monkeypatch.setattr(cb, "_PINNED_MODELS", {})
    key2 = make_cache_key(
        family="codex",
        model_id=cb.resolve_codex_model_id(),
        question="q",
        answer="a",
        context_chunks=chunks,
        citations=[],
    )
    assert key2 == key
    assert cache.get(key2) is not None


def test_gold_review_packet_covers_all(tmp_path, monkeypatch):
    from eval_methodology.mvp.dataset import build_gold as bg

    results = [
        {
            "id": "Q01",
            "question": "q1",
            "status": "needs_human_review",
            "gold": {
                "reference_answer": "ans",
                "claims": [
                    {
                        "claim_id": "c1",
                        "status": "supported",
                        "text": "t",
                        "evidence_ids": ["e1"],
                    }
                ],
                "evidence": [
                    {
                        "evidence_id": "e1",
                        "document_path": "standard/standard.md",
                        "section": "Clause 1",
                        "quote": "The exact evidence quote from the standard.",
                    }
                ],
                "E_plus": ["e1"],
                "gold_claim_status": "supported",
            },
            "disputes": [],
        },
        {
            "id": "Q02",
            "question": "q2",
            "status": "review_not_converged",
            "gold": {
                "reference_answer": "",
                "claims": [],
                "E_plus": [],
                "gold_claim_status": "none",
            },
            "disputes": [{"claim_id": "c1", "note": "nope"}],
        },
    ]
    path = bg.write_human_review_packet(results, review_dir=tmp_path)
    text = path.read_text(encoding="utf-8")
    assert "Q01" in text and "Q02" in text
    assert "最小充分证据集" in text
    assert "[DISPUTED]" in text
    assert "standard/standard.md" in text
    assert "The exact evidence quote from the standard." in text
